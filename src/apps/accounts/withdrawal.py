from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import DatabaseError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.catalog.engagement import recompute_product_metric
from apps.catalog.models import Favorite, Product
from apps.chat.models import ChatMessage, ProductConversation
from apps.chat.services import user_close_group_name
from apps.moderation.models import (
    AbuseReport,
    AdminAudit,
    AdminScopeGrant,
    AuditEvent,
    ModerationAction,
)
from apps.notifications.models import Notification
from apps.trades.models import Review, Trade
from apps.transfers.models import LedgerAccount, MockAccount, TransferAudit

from .models import RevocationTask, User, UserSessionIndex
from .services import withdrawal_event_key


class WithdrawalBlocked(ValueError):
    """A safe business denial that does not reveal another party's state."""


class WithdrawalUnavailable(RuntimeError):
    """An authority or revocation dependency is unavailable; fail closed."""


@dataclass(frozen=True, slots=True)
class WithdrawalResult:
    task: RevocationTask
    created: bool


def withdraw_account(*, user_id: int, password: str) -> WithdrawalResult:
    """Commit withdrawal only after every durable authority is locked and rechecked."""
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user_id)
            if user.withdrawn_at is not None:
                task = RevocationTask.objects.get(user=user, auth_epoch=user.auth_epoch)
                return WithdrawalResult(task=task, created=False)
            if not user.is_active or not password or not user.check_password(password):
                raise WithdrawalBlocked("현재 비밀번호를 확인해 주세요.")

            trade_scope = Trade.objects.filter(Q(seller=user) | Q(buyer=user))
            product_ids = set(
                Product.objects.filter(owner=user).values_list("pk", flat=True)
            )
            product_ids.update(trade_scope.values_list("product_id", flat=True))
            favorite_product_ids = set(
                Favorite.objects.filter(user=user).values_list("product_id", flat=True)
            )
            product_ids.update(favorite_product_ids)
            products = list(
                Product.objects.select_for_update()
                .filter(pk__in=sorted(product_ids))
                .order_by("pk")
            )
            trades = list(
                Trade.objects.select_for_update()
                .filter(Q(seller=user) | Q(buyer=user))
                .order_by("pk")
            )
            if any(trade.status == Trade.Status.RESERVED for trade in trades):
                raise WithdrawalBlocked("진행 중인 거래를 먼저 종료해 주세요.")

            try:
                account = MockAccount.objects.select_for_update().get(user=user)
                LedgerAccount.objects.select_for_update().get(mock_account=account)
            except (MockAccount.DoesNotExist, LedgerAccount.DoesNotExist) as exc:
                raise WithdrawalUnavailable("모의 계좌 권위를 확인할 수 없습니다.") from exc
            if account.balance != Decimal("0.00"):
                raise WithdrawalBlocked("모의 잔액을 0원으로 만든 뒤 다시 시도해 주세요.")

            # These locks serialize deletion with concurrent engagement/event writers.
            list(Favorite.objects.select_for_update().filter(user=user).order_by("pk"))
            list(Notification.objects.select_for_update().filter(recipient=user).order_by("pk"))
            _assert_retention_authorities_available()

            now = _database_now()
            completed_product_ids = {
                trade.product_id
                for trade in trades
                if trade.status == Trade.Status.COMPLETED
            }
            available_product_ids = [
                product.pk
                for product in products
                if (
                    product.owner_id == user.pk
                    and product.archived_at is None
                    and product.pk not in completed_product_ids
                )
            ]
            if available_product_ids:
                Product.objects.filter(pk__in=available_product_ids).update(
                    archived_at=now,
                    version=F("version") + 1,
                    updated_at=now,
                )

            Favorite.objects.filter(user=user).delete()
            for product_id in sorted(favorite_product_ids):
                recompute_product_metric(product_id=product_id)
            Notification.objects.filter(recipient=user).delete()
            if account.is_open:
                account.is_open = False
                account.closed_at = now
                account.save(update_fields=("is_open", "closed_at"))
                TransferAudit.objects.create(actor=user, event_type="ACCOUNT_CLOSED")

            user.is_active = False
            user.withdrawn_at = now
            user.auth_epoch += 1
            user.set_unusable_password()
            user.save(
                update_fields=(
                    "is_active",
                    "withdrawn_at",
                    "auth_epoch",
                    "password",
                )
            )
            task, created = RevocationTask.objects.get_or_create(
                user=user,
                auth_epoch=user.auth_epoch,
                defaults={
                    "event_key": withdrawal_event_key(
                        user_id=user.pk,
                        auth_epoch=user.auth_epoch,
                    )
                },
            )
            return WithdrawalResult(task=task, created=created)
    except WithdrawalBlocked:
        raise
    except WithdrawalUnavailable:
        raise
    except (DatabaseError, User.DoesNotExist, RevocationTask.DoesNotExist) as exc:
        raise WithdrawalUnavailable("회원 탈퇴 권위를 확인할 수 없습니다.") from exc


def process_revocation_task(*, task_id: int) -> bool:
    """Idempotently delete sessions, close sockets, and clear Redis presence."""
    now = timezone.now()
    with transaction.atomic():
        task = RevocationTask.objects.select_for_update().get(pk=task_id)
        if task.status == RevocationTask.Status.COMPLETED:
            return True
        if (
            task.status == RevocationTask.Status.PROCESSING
            and task.lease_expires_at is not None
            and task.lease_expires_at >= now
        ):
            return False
        task.status = RevocationTask.Status.PROCESSING
        task.attempt_count += 1
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(minutes=2)
        task.completed_at = None
        task.last_error = ""
        task.save(
            update_fields=(
                "status",
                "attempt_count",
                "heartbeat_at",
                "lease_expires_at",
                "completed_at",
                "last_error",
                "updated_at",
            )
        )
        user_id = task.user_id

    try:
        with transaction.atomic():
            indexes = list(
                UserSessionIndex.objects.select_for_update()
                .filter(user_id=user_id)
                .order_by("pk")
            )
            session_keys = [index.session_key for index in indexes]
            if session_keys:
                Session.objects.filter(session_key__in=session_keys).delete()
                UserSessionIndex.objects.filter(pk__in=[index.pk for index in indexes]).update(
                    revoked_at=timezone.now()
                )
        channel_layer = get_channel_layer()
        if channel_layer is None:
            raise RuntimeError("channel layer unavailable")
        async_to_sync(channel_layer.group_send)(
            user_close_group_name(user_id),
            {"type": "user.close"},
        )
        _clear_presence(user_id=user_id)
    except Exception as exc:
        with transaction.atomic():
            task = RevocationTask.objects.select_for_update().get(pk=task_id)
            task.status = RevocationTask.Status.RETRY
            task.available_at = timezone.now() + timedelta(minutes=1)
            task.heartbeat_at = None
            task.lease_expires_at = None
            task.completed_at = None
            task.last_error = type(exc).__name__[:200]
            task.save(
                update_fields=(
                    "status",
                    "available_at",
                    "heartbeat_at",
                    "lease_expires_at",
                    "completed_at",
                    "last_error",
                    "updated_at",
                )
            )
        return False

    with transaction.atomic():
        task = RevocationTask.objects.select_for_update().get(pk=task_id)
        task.status = RevocationTask.Status.COMPLETED
        task.heartbeat_at = None
        task.lease_expires_at = None
        task.completed_at = timezone.now()
        task.last_error = ""
        task.save(
            update_fields=(
                "status",
                "heartbeat_at",
                "lease_expires_at",
                "completed_at",
                "last_error",
                "updated_at",
            )
        )
    return True




def _clear_presence(*, user_id: int) -> None:
    from redis import Redis

    client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    try:
        keys = list(client.scan_iter(match=f"marketplace:presence:*:{user_id}", count=100))
        if keys:
            client.delete(*keys)
    finally:
        client.close()


def _assert_retention_authorities_available() -> None:
    """Touch every retained authority so a partial rollout rolls withdrawal back."""
    for model in (
        ProductConversation,
        ChatMessage,
        Review,
        AbuseReport,
        ModerationAction,
        AuditEvent,
        AdminScopeGrant,
        AdminAudit,
    ):
        model.objects.exists()

def _database_now():
    with connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_TIMESTAMP")
        return cursor.fetchone()[0]
