from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models.functions import Now


class Room(models.Model):
    class Kind(models.TextChoices):
        GLOBAL = "GLOBAL", "Global"
        DIRECT = "DIRECT", "Direct"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    created_at = models.DateTimeField(db_default=Now(), editable=False)


class RoomParticipant(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("room", "user"), name="chat_unique_room_participant"),
        ]


class ChatMessage(models.Model):
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    client_message_id = models.UUIDField()
    body = models.TextField()
    payload_sha256 = models.CharField(max_length=64, editable=False)
    accepted_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("room", "sender", "client_message_id"),
                name="chat_unique_client_message",
            ),
        ]
        indexes = [models.Index(fields=("room", "id"), name="chat_room_cursor_idx")]
