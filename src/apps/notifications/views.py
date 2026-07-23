from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .services import (
    NotificationAuthorizationError,
    mark_notification_read,
    notifications_for_user,
)
from .presentation import inbox_notifications


@login_required
@require_GET
def inbox(request: HttpRequest) -> HttpResponse:
    try:
        notifications = inbox_notifications(
            notifications_for_user(user_id=request.user.pk)[:100]
        )
    except NotificationAuthorizationError as exc:
        raise Http404 from exc
    return render(request, "notifications/inbox.html", {"notifications": notifications})


@login_required
@require_POST
def mark_read(request: HttpRequest, notification_id: int) -> HttpResponse:
    try:
        mark_notification_read(
            notification_id=notification_id,
            recipient_id=request.user.pk,
        )
    except NotificationAuthorizationError as exc:
        raise Http404 from exc
    return redirect("notifications:inbox")
