from __future__ import annotations

from django.db.models.functions import Now
from django.http import HttpRequest

from .models import Notification


def unread_notification_count(request: HttpRequest) -> dict[str, int]:
    """Expose the current user's visible unread count to the shared header."""
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    return {
        "unread_notification_count": Notification.objects.filter(
            recipient_id=request.user.pk,
            read_at__isnull=True,
            expires_at__gte=Now(),
        ).count()
    }
