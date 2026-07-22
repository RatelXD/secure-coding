from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


def create_notification(
    *, recipient_id: int, event_key: str, kind: str, payload: dict[str, Any]
) -> tuple[Notification, bool]:
    """Create an inbox event once; callers provide only a server-derived recipient."""
    if not event_key or len(event_key) > 160:
        raise ValueError("event_key is invalid")
    return Notification.objects.get_or_create(
        recipient_id=recipient_id,
        event_key=event_key,
        defaults={"kind": kind, "payload": payload},
    )


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
