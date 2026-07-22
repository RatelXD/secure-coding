from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID, uuid4

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .presence import PresenceService
from .policies import ChatPolicyError
from .services import (
    ChatAuthorizationError,
    ChatRateLimited,
    ChatReplayConflict,
    DefaultChatService,
    _require_active_user,
    _require_room_access,
    room_group_name,
    user_close_group_name,
)

DORMANT_CLOSE_CODE = 4403
POLICY_CLOSE_CODE = 4400


def has_exact_origin(scope: dict[str, object]) -> bool:
    headers = [
        (name.lower(), value)
        for name, value in scope.get("headers", [])  # type: ignore[union-attr]
    ]
    origins = [value for name, value in headers if name == b"origin"]
    hosts = [value for name, value in headers if name == b"host"]
    if len(origins) != 1 or len(hosts) != 1:
        return False
    try:
        origin = urlsplit(origins[0].decode("ascii"))
        host = urlsplit(f"//{hosts[0].decode('ascii')}")
    except (UnicodeDecodeError, ValueError):
        return False

    websocket_scheme = scope.get("scheme")
    expected_scheme = "https" if websocket_scheme == "wss" else "http"
    if (
        origin.scheme != expected_scheme
        or origin.username is not None
        or origin.password is not None
        or origin.path not in ("", "/")
        or origin.query
        or origin.fragment
        or origin.hostname is None
        or host.username is not None
        or host.password is not None
        or host.path not in ("", "/")
        or host.query
        or host.fragment
        or host.hostname is None
    ):
        return False
    default_port = 443 if expected_scheme == "https" else 80
    try:
        origin_port = origin.port or default_port
        host_port = host.port or default_port
    except ValueError:
        return False
    return origin.hostname.casefold() == host.hostname.casefold() and origin_port == host_port


@database_sync_to_async
def _authorize(room_id: int, user_id: int) -> None:
    _require_active_user(user_id=user_id, lock=False)
    _require_room_access(room_id=room_id, user_id=user_id)


@database_sync_to_async
def _accept_message(
    *,
    room_id: int,
    user_id: int,
    connection_id: UUID,
    client_message_id: UUID,
    body: str,
):
    return DefaultChatService().accept(
        room_id=room_id,
        sender_id=user_id,
        connection_id=connection_id,
        client_message_id=client_message_id,
        body=body,
    )


@database_sync_to_async
def _history(*, room_id: int, user_id: int, cursor: int):
    return DefaultChatService().history_after(
        room_id=room_id,
        requesting_user_id=user_id,
        cursor=cursor,
        limit=100,
    )


class ChatConsumer(AsyncJsonWebsocketConsumer):
    room_id: int
    room_group: str
    user_close_group: str
    connection_id: UUID
    group_joined: bool
    user_close_group_joined: bool

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not has_exact_origin(self.scope):
            await self.close(code=DORMANT_CLOSE_CODE)
            return
        self.room_id = int(self.scope["url_route"]["kwargs"]["room_id"])
        try:
            await _authorize(self.room_id, user.pk)
        except ChatAuthorizationError:
            await self.close(code=DORMANT_CLOSE_CODE)
            return

        self.connection_id = uuid4()
        self.room_group = room_group_name(self.room_id)
        self.user_close_group = user_close_group_name(user.pk)
        self.group_joined = False
        self.user_close_group_joined = False
        self.presence = PresenceService()
        self.presence_online = False
        try:
            await self.channel_layer.group_add(self.room_group, self.channel_name)
            self.group_joined = True
        except Exception:
            pass
        try:
            await self.channel_layer.group_add(self.user_close_group, self.channel_name)
            self.user_close_group_joined = True
        except Exception:
            pass
        await self.accept()
        try:
            await self.presence.online(
                room_id=self.room_id,
                user_id=user.pk,
                connection_id=self.connection_id,
            )
            self.presence_online = True
        except Exception:
            pass
        if not self.group_joined or not self.user_close_group_joined:
            await self.send_json({"type": "delivery_status", "delivery": "degraded"})

    async def disconnect(self, close_code: int) -> None:
        if getattr(self, "presence_online", False):
            try:
                await self.presence.offline(
                    room_id=self.room_id,
                    user_id=self.scope["user"].pk,
                    connection_id=self.connection_id,
                )
            except Exception:
                pass
        for group, joined in (
            (getattr(self, "room_group", ""), getattr(self, "group_joined", False)),
            (
                getattr(self, "user_close_group", ""),
                getattr(self, "user_close_group_joined", False),
            ),
        ):
            if joined:
                try:
                    await self.channel_layer.group_discard(group, self.channel_name)
                except Exception:
                    pass

    async def receive_json(self, content: object, **kwargs: object) -> None:
        user = self.scope["user"]
        try:
            await _authorize(self.room_id, user.pk)
        except ChatAuthorizationError:
            await self.send_json({"type": "account_status", "status": "dormant"})
            await self.close(code=DORMANT_CLOSE_CODE)
            return

        if not isinstance(content, dict):
            await self._send_error("invalid_request")
            return
        operation = content.get("type")
        if operation == "history":
            await self._send_history(content)
        elif operation == "send":
            await self._send_message(content)
        elif operation == "presence":
            await self._send_presence()
        else:
            await self._send_error("invalid_request")

    async def _send_presence(self) -> None:
        try:
            await self.presence.online(
                room_id=self.room_id,
                user_id=self.scope["user"].pk,
                connection_id=self.connection_id,
            )
            states = await self.presence.peer_states(
                room_id=self.room_id,
                user_id=self.scope["user"].pk,
            )
        except Exception:
            await self._send_error("presence_unavailable")
            return
        await self.send_json(
            {
                "type": "presence",
                "users": [
                    {"user_id": user_id, "online": online}
                    for user_id, online in states.items()
                ],
            }
        )

    async def _send_message(self, content: dict[str, object]) -> None:
        try:
            client_message_id = UUID(str(content.get("client_message_id", "")))
            body = content.get("body")
            if not isinstance(body, str):
                raise ChatPolicyError("message must be text")
            accepted = await _accept_message(
                room_id=self.room_id,
                user_id=self.scope["user"].pk,
                connection_id=self.connection_id,
                client_message_id=client_message_id,
                body=body,
            )
        except ChatRateLimited as exc:
            await self.send_json(
                {"type": "error", "code": exc.code, "retry_after": exc.retry_after}
            )
            return
        except ChatReplayConflict as exc:
            await self._send_error(exc.code)
            return
        except ChatAuthorizationError:
            await self.close(code=DORMANT_CLOSE_CODE)
            return
        except (ChatPolicyError, ValueError):
            await self._send_error("invalid_message")
            return

        await self.send_json(
            {
                "type": "ack",
                "accepted": True,
                "server_message_id": accepted.server_message_id,
                "client_message_id": str(accepted.client_message_id),
                "accepted_at": accepted.accepted_at.isoformat(),
                "delivery": accepted.delivery.value,
                "replayed": accepted.replayed,
            }
        )

    async def _send_history(self, content: dict[str, object]) -> None:
        try:
            cursor = int(content.get("cursor", 0))
            history = await _history(
                room_id=self.room_id,
                user_id=self.scope["user"].pk,
                cursor=cursor,
            )
        except ChatAuthorizationError:
            await self.send_json({"type": "account_status", "status": "dormant"})
            await self.close(code=DORMANT_CLOSE_CODE)
            return
        except (TypeError, ValueError):
            await self._send_error("invalid_cursor")
            return
        await self.send_json(
            {
                "type": "history",
                "messages": [
                    {
                        "server_message_id": item.server_message_id,
                        "sender_id": item.sender_id,
                        "sender_username": item.sender_username,
                        "body": item.body,
                        "accepted_at": item.accepted_at.isoformat(),
                    }
                    for item in history
                ],
            }
        )

    async def chat_message(self, event: dict[str, object]) -> None:
        user = self.scope["user"]
        try:
            await _authorize(self.room_id, user.pk)
        except ChatAuthorizationError:
            await self.send_json({"type": "account_status", "status": "dormant"})
            await self.close(code=DORMANT_CLOSE_CODE)
            return
        await self.send_json(
            {
                "type": "message",
                "server_message_id": event["server_message_id"],
                "sender_id": event["sender_id"],
                "sender_username": event["sender_username"],
                "body": event["body"],
                "accepted_at": event["accepted_at"],
            }
        )

    async def user_close(self, event: dict[str, object]) -> None:
        await self.close(code=DORMANT_CLOSE_CODE)


    async def _send_error(self, code: str) -> None:
        await self.send_json({"type": "error", "code": code})
