from __future__ import annotations

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.services import (
    EffectiveAccountStatus,
    effective_account_status,
    project_account_identity,
)
from apps.moderation.services import EffectiveUserStatus, effective_user_status

from .models import ChatMessage, Room, RoomParticipant
from .policies import (
    CHAT_BURST_MESSAGES,
    CHAT_BURST_SECONDS,
    CHAT_SUSTAINED_MESSAGES,
    CHAT_SUSTAINED_SECONDS,
    canonical_payload_sha256,
    normalize_chat_text,
    require_uuid4,
)

logger = logging.getLogger(__name__)
CONNECTION_BURST_MESSAGES = 10
CONNECTION_BURST_SECONDS = 10
HISTORY_MAX_LIMIT = 100


class DeliveryState(StrEnum):
    LIVE = "live"
    DEGRADED = "degraded"


class ChatServiceError(Exception):
    code = "chat_error"


class ChatAuthorizationError(ChatServiceError):
    code = "forbidden"


class ChatReplayConflict(ChatServiceError):
    code = "replay_conflict"


class ChatRateLimited(ChatServiceError):
    code = "rate_limited"

    def __init__(self, retry_after: int) -> None:
        super().__init__("Message rate limit exceeded.")
        self.retry_after = max(1, retry_after)


@dataclass(frozen=True, slots=True)
class AcceptedMessage:
    server_message_id: int
    client_message_id: UUID
    accepted_at: datetime
    delivery: DeliveryState
    replayed: bool


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    server_message_id: int
    sender_id: int
    sender_username: str
    body: str
    accepted_at: datetime


class ChatAcceptanceService(Protocol):
    """Provide the POL-CHAT-002/003 transaction boundary.

    Implementations re-check authorization and DB-authoritative limits, then
    persist before ACK. A Redis failure returns DEGRADED without rolling back
    acceptance. Matching retries return the original result without publishing again.
    """

    def accept(
        self,
        *,
        room_id: int,
        sender_id: int,
        connection_id: UUID,
        client_message_id: UUID,
        body: str,
    ) -> AcceptedMessage: ...

    def history_after(
        self,
        *,
        room_id: int,
        requesting_user_id: int,
        cursor: int,
        limit: int,
    ) -> Sequence[HistoryMessage]: ...


Publisher = Callable[[int, dict[str, Any]], None]


def _database_now() -> datetime:
    with connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_TIMESTAMP")
        value = cursor.fetchone()[0]
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is None:
            raise RuntimeError("Database returned an invalid timestamp.")
        value = parsed
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _require_active_user(*, user_id: int, lock: bool) -> Any:
    users = get_user_model().objects
    if lock:
        users = users.select_for_update()
    try:
        user = users.get(pk=user_id, is_active=True)
    except get_user_model().DoesNotExist as exc:
        raise ChatAuthorizationError("Chat is unavailable.") from exc
    if (
        effective_account_status(user=user) is not EffectiveAccountStatus.ACTIVE
        or effective_user_status(user_id=user_id) is not EffectiveUserStatus.ACTIVE
    ):
        raise ChatAuthorizationError("Chat is unavailable.")
    return user


def _require_room_access(*, room_id: int, user_id: int, lock: bool = False) -> Room:
    rooms = Room.objects.select_related("direct_user_low", "direct_user_high")
    if lock:
        rooms = rooms.select_for_update(of=("self",))
    try:
        room = rooms.get(pk=room_id)
    except Room.DoesNotExist as exc:
        raise ChatAuthorizationError("Chat is unavailable.") from exc
    if not room.contains_user(user_id):
        raise ChatAuthorizationError("Chat is unavailable.")
    return room


def _default_publish(room_id: int, event: dict[str, Any]) -> None:
    layer = get_channel_layer()
    if layer is None:
        raise RuntimeError("Channel layer is unavailable.")
    async_to_sync(layer.group_send)(room_group_name(room_id), event)


def room_group_name(room_id: int) -> str:
    return f"chat.room.{room_id}"


def user_close_group_name(user_id: int) -> str:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("User ID must be a positive integer.")
    return f"chat.user-close.{user_id}"


def get_or_create_global_room() -> Room:
    try:
        room, _ = Room.objects.get_or_create(kind=Room.Kind.GLOBAL)
        return room
    except IntegrityError:
        return Room.objects.get(kind=Room.Kind.GLOBAL)


@transaction.atomic
def get_or_create_direct_room(*, user_a_id: int, user_b_id: int) -> Room:
    if user_a_id == user_b_id:
        raise ChatAuthorizationError("A direct room requires another user.")
    low_id, high_id = sorted((user_a_id, user_b_id))
    users = list(
        get_user_model()
        .objects.select_for_update()
        .filter(pk__in=(low_id, high_id), is_active=True)
        .order_by("pk")
    )
    if len(users) != 2:
        raise ChatAuthorizationError("Chat is unavailable.")
    for user in users:
        if (
            effective_account_status(user=user) is not EffectiveAccountStatus.ACTIVE
            or effective_user_status(user_id=user.pk) is not EffectiveUserStatus.ACTIVE
        ):
            raise ChatAuthorizationError("Chat is unavailable.")

    room, created = Room.objects.get_or_create(
        kind=Room.Kind.DIRECT,
        direct_user_low_id=low_id,
        direct_user_high_id=high_id,
    )
    if created:
        RoomParticipant.objects.bulk_create(
            [
                RoomParticipant(room=room, user_id=low_id),
                RoomParticipant(room=room, user_id=high_id),
            ]
        )
    return room


class DefaultChatService:
    def __init__(self, *, publisher: Publisher | None = None) -> None:
        self._publisher = publisher or _default_publish

    def accept(
        self,
        *,
        room_id: int,
        sender_id: int,
        connection_id: UUID,
        client_message_id: UUID,
        body: str,
    ) -> AcceptedMessage:
        require_uuid4(connection_id)
        require_uuid4(client_message_id)
        normalized_body = normalize_chat_text(body)
        payload_hash = canonical_payload_sha256(
            room_id=room_id,
            sender_id=sender_id,
            body=normalized_body,
        )

        with transaction.atomic():
            sender = _require_active_user(user_id=sender_id, lock=True)
            room = _require_room_access(room_id=room_id, user_id=sender_id, lock=True)
            replay = ChatMessage.objects.filter(
                room=room,
                sender=sender,
                client_message_id=client_message_id,
            ).first()
            if replay is not None:
                if replay.payload_sha256 != payload_hash:
                    raise ChatReplayConflict("The client message ID has different content.")
                return AcceptedMessage(
                    server_message_id=replay.pk,
                    client_message_id=replay.client_message_id,
                    accepted_at=replay.accepted_at,
                    delivery=DeliveryState(replay.delivery),
                    replayed=True,
                )

            now = _database_now()
            self._enforce_rate_limits(
                sender_id=sender_id,
                connection_id=connection_id,
                now=now,
            )
            message = ChatMessage.objects.create(
                room=room,
                sender=sender,
                connection_id=connection_id,
                client_message_id=client_message_id,
                body=normalized_body,
                payload_sha256=payload_hash,
                delivery=ChatMessage.Delivery.DEGRADED,
            )

        event = {
            "type": "chat.message",
            "server_message_id": message.pk,
            "sender_id": sender.pk,
            "sender_username": project_account_identity(user=sender).display_name,
            "body": message.body,
            "accepted_at": message.accepted_at.isoformat(),
        }
        delivery = DeliveryState.DEGRADED
        try:
            self._publisher(room.pk, event)
        except Exception:
            logger.warning("Chat live delivery degraded for message_id=%s", message.pk)
        else:
            ChatMessage.objects.filter(pk=message.pk).update(delivery=ChatMessage.Delivery.LIVE)
            delivery = DeliveryState.LIVE

        return AcceptedMessage(
            server_message_id=message.pk,
            client_message_id=message.client_message_id,
            accepted_at=message.accepted_at,
            delivery=delivery,
            replayed=False,
        )

    def _enforce_rate_limits(
        self,
        *,
        sender_id: int,
        connection_id: UUID,
        now: datetime,
    ) -> None:
        checks = (
            (
                ChatMessage.objects.filter(sender_id=sender_id),
                CHAT_BURST_MESSAGES,
                CHAT_BURST_SECONDS,
            ),
            (
                ChatMessage.objects.filter(sender_id=sender_id),
                CHAT_SUSTAINED_MESSAGES,
                CHAT_SUSTAINED_SECONDS,
            ),
            (
                ChatMessage.objects.filter(
                    sender_id=sender_id,
                    connection_id=connection_id,
                ),
                CONNECTION_BURST_MESSAGES,
                CONNECTION_BURST_SECONDS,
            ),
        )
        retry_after = 0
        for queryset, limit, seconds in checks:
            window_start = now - timedelta(seconds=seconds)
            timestamps = list(
                queryset.filter(accepted_at__gt=window_start)
                .order_by("accepted_at")
                .values_list("accepted_at", flat=True)[:limit]
            )
            if len(timestamps) >= limit:
                remaining = (timestamps[0] + timedelta(seconds=seconds) - now).total_seconds()
                retry_after = max(retry_after, math.ceil(remaining))
        if retry_after:
            raise ChatRateLimited(retry_after)

    def history_after(
        self,
        *,
        room_id: int,
        requesting_user_id: int,
        cursor: int,
        limit: int = HISTORY_MAX_LIMIT,
    ) -> Sequence[HistoryMessage]:
        if cursor < 0:
            raise ValueError("Cursor must not be negative.")
        if not 1 <= limit <= HISTORY_MAX_LIMIT:
            raise ValueError(f"History limit must be between 1 and {HISTORY_MAX_LIMIT}.")
        _require_active_user(user_id=requesting_user_id, lock=False)
        room = _require_room_access(room_id=room_id, user_id=requesting_user_id)
        messages = (
            ChatMessage.objects.filter(room=room, pk__gt=cursor)
            .select_related("sender")
            .order_by("pk")[:limit]
        )
        history: list[HistoryMessage] = []
        for message in messages:
            identity = project_account_identity(user=message.sender)
            history.append(
                HistoryMessage(
                    server_message_id=message.pk,
                    sender_id=message.sender_id,
                    sender_username=identity.display_name,
                    body=message.body,
                    accepted_at=message.accepted_at,
                )
            )
        return history