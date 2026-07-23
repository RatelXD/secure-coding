from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models.functions import Now
from django.utils import timezone

from apps.accounts.services import EffectiveAccountStatus, effective_account_status

from .models import Notification, NotificationPurgeState

PURGE_ADVISORY_LOCK_ID = 0x4E4F5449
PURGE_BATCH_SIZE = 500


class NotificationAuthorizationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PurgeResult:
    deleted_count: int
    lock_acquired: bool


@dataclass(frozen=True, slots=True)
class TransferNotification:
    sender_id: int
    recipient_id: int
    transfer_id: UUID
    amount: Decimal


@transaction.atomic
def create_notification(
    *, recipient_id: int, event_key: str, kind: str, payload: dict[str, Any]
) -> tuple[Notification, bool]:
    """Create an inbox event once for a currently active server-derived recipient."""
    if not event_key or len(event_key) > 160:
        raise ValueError("event_key is invalid")
    try:
        recipient = (
            get_user_model()
            .objects.select_for_update()
            .get(pk=recipient_id, is_active=True, withdrawn_at__isnull=True)
        )
    except get_user_model().DoesNotExist as exc:
        raise NotificationAuthorizationError("Notifications are unavailable.") from exc
    return Notification.objects.get_or_create(
        recipient=recipient,
        event_key=event_key,
        defaults={"kind": kind, "payload": payload},
    )


def create_transfer_notifications(
    *, transfer_notification: TransferNotification
) -> tuple[Notification, Notification]:
    """Create the durable sender and recipient events for one completed transfer."""
    transfer_id = str(transfer_notification.transfer_id)
    amount = f"{transfer_notification.amount:.2f}"
    counterparty_names = {
        user_id: username
        for user_id, username in get_user_model()
        .objects.filter(
            pk__in=(transfer_notification.sender_id, transfer_notification.recipient_id)
        )
        .values_list("pk", "username")
    }
    sender_notice, _ = create_notification(
        recipient_id=transfer_notification.sender_id,
        event_key=f"transfer.sender:{transfer_id}",
        kind="TRANSFER_SENT",
        payload={
            "transfer_id": transfer_id,
            "amount": amount,
            "counterparty_name": counterparty_names.get(transfer_notification.recipient_id, ""),
        },
    )
    recipient_notice, _ = create_notification(
        recipient_id=transfer_notification.recipient_id,
        event_key=f"transfer.recipient:{transfer_id}",
        kind="TRANSFER_RECEIVED",
        payload={
            "transfer_id": transfer_id,
            "amount": amount,
            "counterparty_name": counterparty_names.get(transfer_notification.sender_id, ""),
        },
    )
    return sender_notice, recipient_notice


def notifications_for_user(*, user_id: int):
    try:
        user = get_user_model().objects.get(pk=user_id, is_active=True)
    except get_user_model().DoesNotExist as exc:
        raise NotificationAuthorizationError("Notifications are unavailable.") from exc
    if effective_account_status(user=user) is not EffectiveAccountStatus.ACTIVE:
        raise NotificationAuthorizationError("Notifications are unavailable.")
    return Notification.objects.filter(recipient_id=user_id, expires_at__gte=Now())


@transaction.atomic
def mark_notification_read(*, notification_id: int, recipient_id: int) -> Notification:
    try:
        notification = Notification.objects.select_for_update().get(
            pk=notification_id,
            recipient_id=recipient_id,
            expires_at__gte=Now(),
        )
    except Notification.DoesNotExist as exc:
        raise NotificationAuthorizationError("Notification is unavailable.") from exc
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=("read_at",))
    return notification


def purge_expired_notifications() -> PurgeResult:
    """Delete strictly expired rows in bounded batches under one PostgreSQL singleton lock."""
    deleted = 0
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [PURGE_ADVISORY_LOCK_ID])
            if not cursor.fetchone()[0]:
                return PurgeResult(deleted_count=0, lock_acquired=False)
        while True:
            ids = list(
                Notification.objects.filter(expires_at__lt=Now())
                .order_by("pk")
                .values_list("pk", flat=True)[:PURGE_BATCH_SIZE]
            )
            if not ids:
                break
            count, _ = Notification.objects.filter(pk__in=ids).delete()
            deleted += count
        NotificationPurgeState.objects.update_or_create(
            singleton=1,
            defaults={"last_success_at": Now(), "last_deleted_count": deleted},
        )
    return PurgeResult(deleted_count=deleted, lock_acquired=True)
