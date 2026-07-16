from __future__ import annotations

import hashlib
import json
from uuid import RFC_4122, UUID

CHAT_MAX_BYTES = 2_000
CHAT_BURST_MESSAGES = 10
CHAT_BURST_SECONDS = 10
CHAT_SUSTAINED_MESSAGES = 60
CHAT_SUSTAINED_SECONDS = 60


class ChatPolicyError(ValueError):
    """A stable policy rejection safe to map to a generic client error."""


def normalize_chat_text(value: str) -> str:
    """Return policy-valid text without changing its internal content."""
    if not isinstance(value, str):
        raise ChatPolicyError("message must be text")

    normalized = value.strip()
    if not normalized:
        raise ChatPolicyError("message must not be empty")
    if "\x00" in normalized:
        raise ChatPolicyError("message contains a forbidden control character")
    if any(ord(character) < 0x20 and character != "\n" for character in normalized):
        raise ChatPolicyError("message contains a forbidden control character")
    if len(normalized.encode("utf-8")) > CHAT_MAX_BYTES:
        raise ChatPolicyError("message exceeds the UTF-8 byte limit")
    return normalized


def require_uuid4(value: UUID) -> UUID:
    if not isinstance(value, UUID) or value.version != 4 or value.variant != RFC_4122:
        raise ChatPolicyError("client_message_id must be a UUIDv4")
    return value


def canonical_payload_sha256(*, room_id: int, sender_id: int, body: str) -> str:
    """Bind replay identity to the canonical accepted payload."""
    canonical = json.dumps(
        {"body": normalize_chat_text(body), "room_id": room_id, "sender_id": sender_id},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
