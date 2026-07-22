from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import RevocationTask, User, UserSessionIndex
from apps.accounts.services import project_account_identity
from apps.accounts.withdrawal import (
    WithdrawalBlocked,
    WithdrawalUnavailable,
    process_revocation_task,
    withdraw_account,
)
from apps.catalog.models import Favorite, Product, ProductMetric
from apps.notifications.models import Notification
from apps.trades.models import Review, Trade
from apps.transfers.models import MockAccount
from apps.transfers.services import ensure_account

pytestmark = pytest.mark.django_db


class FakeChannelLayer:
    def __init__(self):
        self.events = []

    async def group_send(self, group, event):
        self.events.append((group, event))


def make_user(username):
    return User.objects.create_user(username=username, password="Correct-Horse-Battery-47!")


def make_zero_account(user):
    account = ensure_account(user)
    MockAccount.objects.filter(pk=account.pk).update(balance=Decimal("0.00"))
    account.refresh_from_db()
    return account


def make_product(owner, title="탈퇴 대상 상품"):
    return Product.objects.create(
        owner=owner,
        title=title,
        description="보존 경계를 확인하는 상품",
        price=10000,
        category_id="OTHER",
    )


def login(client, user):
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def test_withdrawal_rechecks_password_reservation_and_balance():
    user = make_user("withdraw_guard")
    buyer = make_user("withdraw_buyer")
    item = make_product(user)

    with pytest.raises(WithdrawalBlocked, match="잔액"):
        withdraw_account(user_id=user.pk, password="Correct-Horse-Battery-47!")
    user.refresh_from_db()
    assert user.is_active

    account = MockAccount.objects.get(user=user)
    with pytest.raises(WithdrawalBlocked, match="비밀번호"):
        withdraw_account(user_id=user.pk, password="wrong-password")

    MockAccount.objects.filter(pk=account.pk).update(balance=Decimal("0.00"))
    Trade.objects.create(
        product=item,
        seller=user,
        buyer=buyer,
        status=Trade.Status.RESERVED,
    )
    with pytest.raises(WithdrawalBlocked, match="진행 중"):
        withdraw_account(user_id=user.pk, password="Correct-Horse-Battery-47!")
    user.refresh_from_db()
    assert user.is_active and user.withdrawn_at is None
    assert RevocationTask.objects.count() == 0


def test_missing_retention_authority_rolls_back_without_partial_cleanup(monkeypatch):
    user = make_user("withdraw_missing_authority")
    make_zero_account(user)
    favorite_product = make_product(make_user("withdraw_other_owner"))
    favorite = Favorite.objects.create(user=user, product=favorite_product)

    def unavailable():
        raise DatabaseError("missing authority table")

    monkeypatch.setattr(
        "apps.accounts.withdrawal._assert_retention_authorities_available",
        unavailable,
    )
    with pytest.raises(WithdrawalUnavailable):
        withdraw_account(
            user_id=user.pk,
            password="Correct-Horse-Battery-47!",
        )

    user.refresh_from_db()
    assert user.is_active and user.withdrawn_at is None and user.auth_epoch == 0
    assert Favorite.objects.filter(pk=favorite.pk).exists()
    assert MockAccount.objects.get(user=user).is_open
    assert not RevocationTask.objects.filter(user=user).exists()


def test_withdrawal_commits_privacy_cleanup_and_retains_authoritative_history():
    user = make_user("withdraw_success")
    buyer = make_user("withdraw_counterparty")
    make_zero_account(user)
    available = make_product(user, "판매 중 상품")
    completed_product = make_product(user, "완료 상품")
    trade = Trade.objects.create(
        product=completed_product,
        seller=user,
        buyer=buyer,
        status=Trade.Status.COMPLETED,
        completed_at=timezone.now(),
    )
    review = Review.objects.create(
        trade=trade,
        author=buyer,
        subject=user,
        rating=5,
        body="안전하게 완료된 거래 후기",
    )
    Favorite.objects.create(user=user, product=completed_product)
    Notification.objects.create(
        recipient=user,
        event_key="withdrawal-test-notification",
        kind="TEST",
        payload={"safe": True},
    )

    result = withdraw_account(
        user_id=user.pk,
        password="Correct-Horse-Battery-47!",
    )
    user.refresh_from_db()
    available.refresh_from_db()
    completed_product.refresh_from_db()
    account = MockAccount.objects.get(user=user)

    assert result.created
    assert not user.is_active and user.withdrawn_at is not None
    assert not user.has_usable_password() and user.auth_epoch == 1
    assert available.archived_at is not None
    assert completed_product.archived_at is None
    assert account.balance == 0 and not account.is_open and account.closed_at is not None
    assert not Favorite.objects.filter(user=user).exists()
    assert ProductMetric.objects.get(product=completed_product).favorite_count == 0
    assert not Notification.objects.filter(recipient=user).exists()
    assert Trade.objects.filter(pk=trade.pk).exists()
    assert Review.objects.filter(pk=review.pk).exists()
    assert project_account_identity(user=user).display_name == "탈퇴한 회원"

    replay = withdraw_account(user_id=user.pk, password="ignored-after-commit")
    assert replay.task.pk == result.task.pk and not replay.created
    assert RevocationTask.objects.filter(user=user).count() == 1


def test_revocation_processor_deletes_all_sessions_closes_socket_and_clears_presence(monkeypatch):
    user = make_user("revoke_sessions")
    user.withdrawn_at = timezone.now()
    user.is_active = False
    user.auth_epoch = 1
    user.set_unusable_password()
    user.save(update_fields=("withdrawn_at", "is_active", "auth_epoch", "password"))
    task = RevocationTask.objects.create(
        user=user,
        auth_epoch=1,
        event_key=f"withdrawal:{user.pk}:auth-epoch:1",
    )
    keys = []
    for _ in range(2):
        session = SessionStore()
        session["opaque"] = "value"
        session.save()
        keys.append(session.session_key)
        UserSessionIndex.objects.create(
            user=user,
            session_key=session.session_key,
            auth_epoch=0,
        )

    layer = FakeChannelLayer()
    cleared = []
    monkeypatch.setattr("apps.accounts.withdrawal.get_channel_layer", lambda: layer)
    monkeypatch.setattr(
        "apps.accounts.withdrawal._clear_presence",
        lambda *, user_id: cleared.append(user_id),
    )

    assert process_revocation_task(task_id=task.pk)
    task.refresh_from_db()
    assert task.status == RevocationTask.Status.COMPLETED
    assert not Session.objects.filter(session_key__in=keys).exists()
    assert not UserSessionIndex.objects.filter(user=user, revoked_at__isnull=True).exists()
    assert layer.events == [(f"chat.user-close.{user.pk}", {"type": "user.close"})]
    assert cleared == [user.pk]
    assert process_revocation_task(task_id=task.pk)
    assert len(layer.events) == 1


def test_revocation_failure_is_durable_and_idempotently_repairable(monkeypatch):
    user = make_user("revoke_retry")
    user.withdrawn_at = timezone.now()
    user.is_active = False
    user.auth_epoch = 1
    user.set_unusable_password()
    user.save(update_fields=("withdrawn_at", "is_active", "auth_epoch", "password"))
    task = RevocationTask.objects.create(
        user=user,
        auth_epoch=1,
        event_key=f"withdrawal:{user.pk}:auth-epoch:1",
    )

    class FailingLayer:
        async def group_send(self, group, event):
            raise ConnectionError("secret transport detail")

    monkeypatch.setattr("apps.accounts.withdrawal.get_channel_layer", lambda: FailingLayer())
    assert not process_revocation_task(task_id=task.pk)
    task.refresh_from_db()
    assert task.status == RevocationTask.Status.RETRY
    assert task.last_error == "ConnectionError"
    assert "secret" not in task.last_error

    layer = FakeChannelLayer()
    monkeypatch.setattr("apps.accounts.withdrawal.get_channel_layer", lambda: layer)
    monkeypatch.setattr("apps.accounts.withdrawal._clear_presence", lambda *, user_id: None)
    assert process_revocation_task(task_id=task.pk)
    task.refresh_from_db()
    assert task.status == RevocationTask.Status.COMPLETED


def test_withdrawal_http_requires_authentication_csrf_and_current_password():
    user = make_user("withdraw_http")
    make_zero_account(user)
    url = reverse("accounts:withdraw")
    assert Client().get(url).status_code == 302

    csrf_client = Client(enforce_csrf_checks=True)
    login(csrf_client, user)
    assert csrf_client.post(url, {"password": "Correct-Horse-Battery-47!"}).status_code == 403

    client = Client()
    login(client, user)
    wrong = client.post(url, {"password": "wrong-password"})
    assert wrong.status_code == 200
    user.refresh_from_db()
    assert user.is_active
    assert client.post(
        url,
        {"password": "Correct-Horse-Battery-47!", "is_staff": "1"},
    ).status_code == 200
    user.refresh_from_db()
    assert user.is_active

    success = client.post(url, {"password": "Correct-Horse-Battery-47!"})
    assert success.status_code == 302
    user.refresh_from_db()
    assert not user.is_active
    assert client.get(reverse("accounts:profile")).status_code in {302, 403}
