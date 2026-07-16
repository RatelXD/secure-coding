from __future__ import annotations
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now


class Room(models.Model):
    class Kind(models.TextChoices):
        GLOBAL = "GLOBAL", "Global"
        DIRECT = "DIRECT", "Direct"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    direct_user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="direct_rooms_as_low",
    )
    direct_user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="direct_rooms_as_high",
    )
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("kind",),
                condition=Q(kind="GLOBAL"),
                name="chat_single_global_room",
            ),
            models.UniqueConstraint(
                fields=("direct_user_low", "direct_user_high"),
                condition=Q(kind="DIRECT"),
                name="chat_unique_direct_pair",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        kind="GLOBAL",
                        direct_user_low__isnull=True,
                        direct_user_high__isnull=True,
                    )
                    | Q(
                        kind="DIRECT",
                        direct_user_low__isnull=False,
                        direct_user_high__isnull=False,
                        direct_user_low__lt=F("direct_user_high"),
                    )
                ),
                name="chat_room_participant_shape",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.kind == self.Kind.GLOBAL:
            if self.direct_user_low_id is not None or self.direct_user_high_id is not None:
                raise ValidationError("A global room cannot have direct participants.")
        elif (
            self.direct_user_low_id is None
            or self.direct_user_high_id is None
            or self.direct_user_low_id >= self.direct_user_high_id
        ):
            raise ValidationError("A direct room requires two distinct ordered participants.")

    def contains_user(self, user_id: int) -> bool:
        return self.kind == self.Kind.GLOBAL or user_id in {
            self.direct_user_low_id,
            self.direct_user_high_id,
        }


class RoomParticipant(models.Model):
    """Read-compatible participant rows maintained only by room services."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("room", "user"), name="chat_unique_room_participant"),
        ]


class ChatMessage(models.Model):
    class Delivery(models.TextChoices):
        LIVE = "live", "Live"
        DEGRADED = "degraded", "Degraded"

    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    connection_id = models.UUIDField(default=uuid4, editable=False)
    client_message_id = models.UUIDField()
    body = models.TextField()
    payload_sha256 = models.CharField(max_length=64, editable=False)
    delivery = models.CharField(
        max_length=16,
        choices=Delivery.choices,
        default=Delivery.LIVE,
        editable=False,
    )
    accepted_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("room", "sender", "client_message_id"),
                name="chat_unique_client_message",
            ),
        ]
        indexes = [
            models.Index(fields=("room", "id"), name="chat_room_cursor_idx"),
            models.Index(fields=("sender", "accepted_at"), name="chat_sender_rate_idx"),
            models.Index(
                fields=("sender", "connection_id", "accepted_at"),
                name="chat_connection_rate_idx",
            ),
        ]