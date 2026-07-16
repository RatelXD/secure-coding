from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, Sequence
from uuid import UUID


class DeliveryState(StrEnum):
    LIVE = "live"
    DEGRADED = "degraded"


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
    body: str
    accepted_at: datetime


class ChatAcceptanceService(Protocol):
    """Transaction boundary for POL-CHAT-002/003.

    Implementations must re-check participant and canonical account status plus
    DB-authoritative rate limits inside the transaction, persist before ACK,
    and publish only after commit. A Redis failure returns DEGRADED without
    rolling back acceptance. A matching retry returns the original server ID
    without publishing again; a mismatched retry is a conflict.
    """

    def accept(
        self,
        *,
        room_id: int,
        sender_id: int,
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
