from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import RevocationTask, UserSessionIndex
from apps.accounts.services import (
    AccountSessionService,
    EffectiveAccountStatus,
    IDENTITY_IMMUTABLE_FIELDS,
    RevocationPreparationError,
    SESSION_AUTH_EPOCH_KEY,
    WITHDRAWAL_ACTIVATION_ENABLED,
    WITHDRAWN_ACCOUNT_LABEL,
    effective_account_status,
    prepare_withdrawal_revocation,
    project_account_identity,
    withdrawal_event_key,
)


@pytest.mark.django_db
def test_identity_projector_tombstones_withdrawn_and_missing_accounts() -> None:
    user = get_user_model().objects.create_user(
        username="project_user",
        password="long-test-password-1",
    )

    active = project_account_identity(user=user)
    assert active.status is EffectiveAccountStatus.ACTIVE
    assert active.display_name == "project_user"
    assert active.is_tombstone is False
    assert "withdrawn_at" in IDENTITY_IMMUTABLE_FIELDS

    user.withdrawn_at = timezone.now()
    withdrawn = project_account_identity(user=user)
    assert effective_account_status(user=user) is EffectiveAccountStatus.WITHDRAWN
    assert withdrawn.display_name == WITHDRAWN_ACCOUNT_LABEL
    assert withdrawn.is_tombstone is True
    assert "project_user" not in withdrawn.display_name

    missing = project_account_identity(user=None)
    assert missing.status is EffectiveAccountStatus.WITHDRAWN
    assert missing.display_name == WITHDRAWN_ACCOUNT_LABEL


@pytest.mark.django_db(transaction=True)
def test_revocation_preparation_is_idempotent_and_non_destructive() -> None:
    user = get_user_model().objects.create_user(
        username="revocation_user",
        password="long-test-password-1",
    )
    withdrawn_at = timezone.now()
    user.set_unusable_password()
    user.save(update_fields=("password",))
    get_user_model().objects.filter(pk=user.pk).update(
        withdrawn_at=withdrawn_at,
        auth_epoch=1,
        is_active=False,
    )

    first = prepare_withdrawal_revocation(user_id=user.pk, auth_epoch=1)
    replay = prepare_withdrawal_revocation(user_id=user.pk, auth_epoch=1)

    assert first.created is True
    assert replay.created is False
    assert replay.task.pk == first.task.pk
    assert RevocationTask.objects.count() == 1
    assert first.task.status == RevocationTask.Status.PENDING
    assert first.task.event_key == withdrawal_event_key(user_id=user.pk, auth_epoch=1)

    user.refresh_from_db()
    assert user.withdrawn_at == withdrawn_at
    assert user.auth_epoch == 1
    assert get_user_model().objects.filter(pk=user.pk).exists()
    assert user.is_active is False
    assert user.has_usable_password() is False


@pytest.mark.django_db
@pytest.mark.parametrize("prepared_epoch", [0, 1, 3, True])
def test_revocation_preparation_rejects_active_or_stale_state(prepared_epoch: object) -> None:
    user = get_user_model().objects.create_user(
        username=f"reject_{str(prepared_epoch).lower()}",
        password="long-test-password-1",
    )
    user.auth_epoch = 2
    user.save(update_fields=("auth_epoch",))

    with pytest.raises(RevocationPreparationError, match="revocation state is invalid"):
        prepare_withdrawal_revocation(user_id=user.pk, auth_epoch=prepared_epoch)  # type: ignore[arg-type]

    assert RevocationTask.objects.count() == 0


@pytest.mark.django_db
def test_withdrawn_account_is_fail_closed_at_http_boundary() -> None:
    user = get_user_model().objects.create_user(
        username="withdrawn_http",
        password="long-test-password-1",
    )
    client = Client()
    client.force_login(user)
    session = client.session
    session[SESSION_AUTH_EPOCH_KEY] = user.auth_epoch
    session.save()
    get_user_model().objects.filter(pk=user.pk).update(withdrawn_at=timezone.now())

    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 403
    assert response.content == b"Account unavailable."
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_session_index_creation_rotation_and_revocation() -> None:
    user = get_user_model().objects.create_user(
        username="session_index_user",
        password="long-test-password-1",
    )
    client = Client()
    client.force_login(user)
    request = client.request().wsgi_request
    request.user = user
    request.session = client.session

    first = AccountSessionService.start(request=request, user=user)
    first_key = first.session_key
    assert first.auth_epoch == 0
    assert first.revoked_at is None

    user.set_password("long-test-password-2")
    user.save(update_fields=("password",))
    rotated = AccountSessionService.rotate_after_password_change(request=request, user=user)
    user.refresh_from_db()
    first.refresh_from_db()

    assert rotated.session_key != first_key
    assert rotated.auth_epoch == user.auth_epoch == 1
    assert first.revoked_at is not None

    AccountSessionService.end(request=request)
    rotated.refresh_from_db()
    assert rotated.revoked_at is not None


@pytest.mark.django_db
def test_authenticated_request_backfills_missing_session_index_without_eager_touch() -> None:
    user = get_user_model().objects.create_user(
        username="rolling_session_user",
        password="long-test-password-1",
    )
    client = Client()
    client.force_login(user)
    session = client.session
    session[SESSION_AUTH_EPOCH_KEY] = user.auth_epoch
    session.save()
    request = client.request().wsgi_request
    request.user = user
    request.session = client.session

    assert AccountSessionService.validate_request(request=request, user=user) is True
    indexed = UserSessionIndex.objects.get(session_key=request.session.session_key)
    original_last_seen = indexed.last_seen_at

    assert AccountSessionService.validate_request(request=request, user=user) is True
    indexed.refresh_from_db()
    assert indexed.last_seen_at == original_last_seen


@pytest.mark.django_db
def test_revocation_preparation_rejects_incomplete_withdrawn_invariant_and_bad_replay() -> None:
    user = get_user_model().objects.create_user(
        username="invariant_user",
        password="long-test-password-1",
    )
    get_user_model().objects.filter(pk=user.pk).update(
        withdrawn_at=timezone.now(),
        auth_epoch=1,
        is_active=False,
    )
    with pytest.raises(RevocationPreparationError, match="revocation state is invalid"):
        prepare_withdrawal_revocation(user_id=user.pk, auth_epoch=1)

    user.set_unusable_password()
    user.save(update_fields=("password",))
    RevocationTask.objects.create(
        user=user,
        auth_epoch=1,
        event_key="wrong-event-key",
    )
    with pytest.raises(RevocationPreparationError, match="revocation replay is invalid"):
        prepare_withdrawal_revocation(user_id=user.pk, auth_epoch=1)


@pytest.mark.django_db
def test_withdrawn_account_public_list_and_detail_render_tombstone_only() -> None:
    withdrawn = get_user_model().objects.create_user(
        username="withdrawn_public_identity",
        password="long-test-password-1",
        bio="withdrawn biography must not render",
    )
    reporter = get_user_model().objects.create_user(
        username="active_reporter",
        password="long-test-password-1",
    )
    get_user_model().objects.filter(pk=withdrawn.pk).update(withdrawn_at=timezone.now())

    client = Client()
    client.force_login(reporter)
    session = client.session
    session[SESSION_AUTH_EPOCH_KEY] = reporter.auth_epoch
    session.save()

    list_response = client.get(reverse("accounts:user_list"))
    detail_response = client.get(reverse("accounts:user_detail", args=(withdrawn.username,)))

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    for response in (list_response, detail_response):
        content = response.content.decode()
        assert WITHDRAWN_ACCOUNT_LABEL in content
        assert withdrawn.username not in content
        assert withdrawn.bio not in content
    assert "사용자 신고" not in detail_response.content.decode()

def test_withdrawal_activation_is_enabled_after_authorities_exist() -> None:
    assert WITHDRAWAL_ACTIVATION_ENABLED is True
