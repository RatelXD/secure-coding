from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from asgiref.sync import sync_to_async
from django.conf import settings

from .models import ProductConversation, Room
from .services import ChatAuthorizationError, _require_active_user, _require_room_access

PRESENCE_TTL_SECONDS = 90


class PresenceBackend(Protocol):
    async def touch(self, key: str, member: str, expires_at: float) -> None: ...
    async def remove(self, key: str, member: str) -> None: ...
    async def count_live(self, key: str, now: float) -> int: ...


class RedisPresenceBackend:
    def __init__(self) -> None:
        from redis.asyncio import from_url

        self._redis = from_url(settings.REDIS_URL, decode_responses=True)

    async def touch(self, key: str, member: str, expires_at: float) -> None:
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.zremrangebyscore(key, "-inf", time.time())
            pipeline.zadd(key, {member: expires_at})
            pipeline.expire(key, PRESENCE_TTL_SECONDS * 2)
            await pipeline.execute()

    async def remove(self, key: str, member: str) -> None:
        await self._redis.zrem(key, member)

    async def count_live(self, key: str, now: float) -> int:
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.zremrangebyscore(key, "-inf", now)
            pipeline.zcount(key, now, "+inf")
            result = await pipeline.execute()
        return int(result[1])


def _presence_key(room_id: int, user_id: int) -> str:
    return f"marketplace:presence:{room_id}:{user_id}"


def authorized_presence_peers(
    *,
    room_id: int,
    user_id: int,
    require_active_peers: bool = True,
) -> tuple[int, ...]:
    """Return only server-authorized one-to-one peers; global presence is never exposed."""
    _require_active_user(user_id=user_id, lock=False)
    room = _require_room_access(
        room_id=room_id,
        user_id=user_id,
        require_active_participants=require_active_peers,
    )
    if room.kind == Room.Kind.GLOBAL:
        raise ChatAuthorizationError("Presence is unavailable.")
    if room.kind == Room.Kind.DIRECT:
        peers: Iterable[int] = (
            room.direct_user_high_id
            if room.direct_user_low_id == user_id
            else room.direct_user_low_id,
        )
    else:
        conversation = ProductConversation.objects.get(room=room)
        peers = (
            conversation.buyer_id
            if conversation.seller_id == user_id
            else conversation.seller_id,
        )
    peer_ids = tuple(int(peer_id) for peer_id in peers if peer_id is not None)
    if require_active_peers:
        for peer_id in peer_ids:
            _require_active_user(user_id=peer_id, lock=False)
    return peer_ids


def _active_presence_peer(*, user_id: int) -> bool:
    try:
        _require_active_user(user_id=user_id, lock=False)
    except ChatAuthorizationError:
        return False
    return True


class PresenceService:
    def __init__(self, backend: PresenceBackend | None = None) -> None:
        self.backend = backend or RedisPresenceBackend()

    async def online(self, *, room_id: int, user_id: int, connection_id: UUID) -> None:
        await sync_to_async(authorized_presence_peers)(room_id=room_id, user_id=user_id)
        now = time.time()
        await self.backend.touch(
            _presence_key(room_id, user_id),
            str(connection_id),
            now + PRESENCE_TTL_SECONDS,
        )

    async def offline(self, *, room_id: int, user_id: int, connection_id: UUID) -> None:
        await self.backend.remove(_presence_key(room_id, user_id), str(connection_id))

    async def peer_states(self, *, room_id: int, user_id: int) -> dict[int, bool]:
        peer_ids = await sync_to_async(authorized_presence_peers)(
            room_id=room_id,
            user_id=user_id,
            require_active_peers=False,
        )
        now = time.time()
        states: dict[int, bool] = {}
        for peer_id in peer_ids:
            if not await sync_to_async(_active_presence_peer)(user_id=peer_id):
                states[peer_id] = False
                continue
            states[peer_id] = bool(
                await self.backend.count_live(_presence_key(room_id, peer_id), now)
            )
        return states
