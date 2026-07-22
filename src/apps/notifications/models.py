from __future__ import annotations
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models.functions import Now


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    event_key = models.CharField(max_length=160)
    kind = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    expires_at = models.DateTimeField(db_default=Now() + timedelta(days=90), editable=False)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "event_key"),
                name="notifications_unique_recipient_event",
            ),
        ]
        indexes = [
            models.Index(fields=("recipient", "read_at", "-created_at"), name="notif_inbox_idx"),
            models.Index(fields=("expires_at", "id"), name="notif_expiry_idx"),
        ]


class NotificationPurgeState(models.Model):
    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_success_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_deleted_count = models.PositiveIntegerField(default=0, editable=False)
