from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model

from apps.chat.consumers import ChatConsumer, DORMANT_CLOSE_CODE, has_exact_origin
from apps.chat.models import ChatMessage, RoomParticipant
from apps.chat.services import (
    ChatAuthorizationError,
    ChatRateLimited,
    ChatReplayConflict,
    DefaultChatService,
    DeliveryState,
    get_or_create_direct_room,
    get_or_create_global_room,
)


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (
            {
                "scheme": "ws",
                "headers": [(b"host", b"example.test"), (b"origin", b"http://example.test")],
            },
            True,
        ),
        (
            {
                "scheme": "wss",
                "headers": [(b"host", b"example.test:443"), (b"origin", b"https://example.test")],
            },
            True,
        ),
        (
            {
                "scheme": "ws",
                "headers": [(b"host", b"example.test"), (b"origin", b"https://example.test")],
            },
            False,
        ),
        (
            {
                "scheme": "ws",
                "headers": [(b"host", b"example.test"), (b"origin", b"http://evil.test")],
            },
            False,
        ),
        ({"scheme": "ws", "headers": [(b"host", b"example.test")]}, False),
    ],
)
def test_exact_websocket_origin(scope: dict[str, object], expected: bool) -> None:
    assert has_exact_origin(scope) is expected


@pytest.fixture
def users(db):
    model = get_user_model()
    return (
        model.objects.create_user(username="alpha_user", password="long-test-password-1"),
        model.objects.create_user(username="bravo_user", password="long-test-password-2"),
        model.objects.create_user(username="charlie_user", password="long-test-password-3"),
    )


@pytest.mark.django_db(transaction=True)
def test_direct_room_is_unique_and_has_exactly_two_service_participants(users) -> None:
    alpha, bravo, _ = users
    room = get_or_create_direct_room(user_a_id=alpha.pk, user_b_id=bravo.pk)
    replay = get_or_create_direct_room(user_a_id=bravo.pk, user_b_id=alpha.pk)

    assert replay.pk == room.pk
    assert room.direct_user_low_id == min(alpha.pk, bravo.pk)
    assert room.direct_user_high_id == max(alpha.pk, bravo.pk)
    assert set(RoomParticipant.objects.filter(room=room).values_list("user_id", flat=True)) == {
        alpha.pk,
        bravo.pk,
    }


@pytest.mark.django_db(transaction=True)
def test_accept_replay_conflict_authorization_and_history(users) -> None:
    alpha, bravo, charlie = users
    room = get_or_create_direct_room(user_a_id=alpha.pk, user_b_id=bravo.pk)
    published: list[dict[str, object]] = []
    service = DefaultChatService(publisher=lambda _room_id, event: published.append(event))
    client_id = uuid4()

    accepted = service.accept(
        room_id=room.pk,
        sender_id=alpha.pk,
        connection_id=uuid4(),
        client_message_id=client_id,
        body="  안녕하세요  ",
    )
    replay = service.accept(
        room_id=room.pk,
        sender_id=alpha.pk,
        connection_id=uuid4(),
        client_message_id=client_id,
        body="안녕하세요",
    )

    assert accepted.replayed is False
    assert replay.replayed is True
    assert replay.server_message_id == accepted.server_message_id
    assert len(published) == 1
    assert ChatMessage.objects.get().body == "안녕하세요"
    assert [message.body for message in service.history_after(
        room_id=room.pk,
        requesting_user_id=bravo.pk,
        cursor=0,
        limit=100,
    )] == ["안녕하세요"]

    with pytest.raises(ChatReplayConflict):
        service.accept(
            room_id=room.pk,
            sender_id=alpha.pk,
            connection_id=uuid4(),
            client_message_id=client_id,
            body="다른 내용",
        )
    with pytest.raises(ChatAuthorizationError):
        service.history_after(
            room_id=room.pk,
            requesting_user_id=charlie.pk,
            cursor=0,
            limit=100,
        )


@pytest.mark.django_db(transaction=True)
def test_publish_failure_is_degraded_but_committed_and_replay_does_not_publish(users) -> None:
    alpha, _, _ = users
    room = get_or_create_global_room()
    publish_calls = 0

    def broken_publish(_room_id, _event) -> None:
        nonlocal publish_calls
        publish_calls += 1
        raise ConnectionError("redis unavailable")

    service = DefaultChatService(publisher=broken_publish)
    client_id = uuid4()
    connection_id = uuid4()
    accepted = service.accept(
        room_id=room.pk,
        sender_id=alpha.pk,
        connection_id=connection_id,
        client_message_id=client_id,
        body="저장되는 메시지",
    )
    replay = service.accept(
        room_id=room.pk,
        sender_id=alpha.pk,
        connection_id=connection_id,
        client_message_id=client_id,
        body="저장되는 메시지",
    )

    assert accepted.delivery is DeliveryState.DEGRADED
    assert replay.delivery is DeliveryState.DEGRADED
    assert replay.replayed is True
    assert publish_calls == 1
    assert ChatMessage.objects.filter(pk=accepted.server_message_id).exists()


@pytest.mark.django_db(transaction=True)
def test_database_authoritative_burst_limit_rejects_eleventh_without_storage(users) -> None:
    alpha, _, _ = users
    room = get_or_create_global_room()
    service = DefaultChatService(publisher=lambda _room_id, _event: None)
    connection_id = uuid4()
    for number in range(10):
        service.accept(
            room_id=room.pk,
            sender_id=alpha.pk,
            connection_id=connection_id,
            client_message_id=uuid4(),
            body=f"message {number}",
        )

    with pytest.raises(ChatRateLimited) as rejected:
        service.accept(
            room_id=room.pk,
            sender_id=alpha.pk,
            connection_id=connection_id,
            client_message_id=uuid4(),
            body="message 11",
        )
    assert rejected.value.retry_after >= 1
    assert ChatMessage.objects.filter(room=room, sender=alpha).count() == 10

def test_live_fanout_rechecks_user_status_before_delivery() -> None:
    consumer = ChatConsumer()
    consumer.scope = {"user": SimpleNamespace(pk=1)}
    consumer.room_id = 42
    consumer.send_json = AsyncMock()
    consumer.close = AsyncMock()

    authorization = AsyncMock(side_effect=ChatAuthorizationError("Chat is unavailable."))
    with patch("apps.chat.consumers._authorize", new=authorization):
        async_to_sync(consumer.chat_message)(
            {
                "server_message_id": 1,
                "sender_id": 2,
                "sender_username": "sender",
                "body": "message",
                "accepted_at": "2026-07-16T00:00:00+00:00",
            }
        )

    consumer.send_json.assert_awaited_once_with(
        {"type": "account_status", "status": "dormant"}
    )
    consumer.close.assert_awaited_once_with(code=DORMANT_CLOSE_CODE)
