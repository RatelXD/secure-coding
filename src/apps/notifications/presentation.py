from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .models import Notification

_AMOUNT = re.compile(r"[1-9][0-9]{0,9}\.[0-9]{2}")


@dataclass(frozen=True, slots=True)
class InboxNotification:
    """Safe, display-only projection of a recipient-owned notification."""

    id: int
    title: str
    detail: str
    created_at: datetime
    is_unread: bool


def inbox_notifications(notifications: Iterable[Notification]) -> list[InboxNotification]:
    """Map server-owned events to a small allowlisted inbox view model."""
    return [_inbox_notification(notification) for notification in notifications]


def _inbox_notification(notification: Notification) -> InboxNotification:
    if notification.kind == "TRANSFER_SENT":
        title = "송금 완료"
        detail = _transfer_detail(notification.payload, "보냈습니다")
    elif notification.kind == "TRANSFER_RECEIVED":
        title = "송금 수신"
        detail = _transfer_detail(notification.payload, "받았습니다")
    else:
        title = "새 알림"
        detail = "알림함에서 내용을 확인하세요."
    return InboxNotification(
        id=notification.pk,
        title=title,
        detail=detail,
        created_at=notification.created_at,
        is_unread=notification.read_at is None,
    )


def _transfer_detail(payload, action: str) -> str:
    if not isinstance(payload, dict):
        return "송금 알림이 도착했습니다."
    amount = payload.get("amount")
    counterparty_name = payload.get("counterparty_name")
    if not isinstance(amount, str) or _AMOUNT.fullmatch(amount) is None:
        return "송금 알림이 도착했습니다."
    if not isinstance(counterparty_name, str) or not counterparty_name.strip():
        return f"{amount}원을 {action}"
    return f"{counterparty_name.strip()}님에게 {amount}원을 {action}"
