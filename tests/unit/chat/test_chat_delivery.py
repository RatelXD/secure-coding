from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

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
    user_close_group_name,
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


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [(1, "chat.user-close.1"), (987654321, "chat.user-close.987654321")],
)
def test_user_close_group_name_is_deterministic_and_safe(
    user_id: int, expected: str
) -> None:
    assert user_close_group_name(user_id) == expected


@pytest.mark.parametrize("user_id", (0, -1, True, "1"))
def test_user_close_group_name_rejects_non_positive_ids(user_id: object) -> None:
    with pytest.raises(ValueError):
        user_close_group_name(user_id)  # type: ignore[arg-type]


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
    assert published[0]["sender_username"] == "alpha_user"
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


def test_consumer_joins_and_discards_room_and_user_close_groups() -> None:
    consumer = ChatConsumer()
    channel_layer = SimpleNamespace(group_add=AsyncMock(), group_discard=AsyncMock())
    consumer.scope = {
        "user": SimpleNamespace(pk=7, is_authenticated=True),
        "scheme": "ws",
        "headers": [(b"host", b"example.test"), (b"origin", b"http://example.test")],
        "url_route": {"kwargs": {"room_id": 42}},
    }
    consumer.channel_layer = channel_layer
    consumer.channel_name = "specific.channel"
    consumer.accept = AsyncMock()
    consumer.send_json = AsyncMock()

    with patch("apps.chat.consumers._authorize", new=AsyncMock()):
        async_to_sync(consumer.connect)()
    async_to_sync(consumer.disconnect)(1000)

    assert [args for args, _ in channel_layer.group_add.await_args_list] == [
        ("chat.room.42", "specific.channel"),
        ("chat.user-close.7", "specific.channel"),
    ]
    assert [args for args, _ in channel_layer.group_discard.await_args_list] == [
        ("chat.room.42", "specific.channel"),
        ("chat.user-close.7", "specific.channel"),
    ]


def test_user_close_event_closes_socket() -> None:
    consumer = ChatConsumer()
    consumer.close = AsyncMock()

    async_to_sync(consumer.user_close)({"type": "user.close"})

    consumer.close.assert_awaited_once_with(code=DORMANT_CLOSE_CODE)


@pytest.mark.django_db(transaction=True)
def test_room_list_projects_withdrawn_direct_participant_identity(client, users) -> None:
    alpha, bravo, _ = users
    get_or_create_direct_room(user_a_id=alpha.pk, user_b_id=bravo.pk)
    get_user_model().objects.filter(pk=bravo.pk).update(withdrawn_at=timezone.now())

    client.force_login(alpha)
    session = client.session
    session["account_auth_epoch"] = alpha.auth_epoch
    session.save()

    response = client.get(reverse("chat:room-list"))

    assert response.status_code == 200
    room_row = response.context["direct_rooms"][0]
    assert room_row["other_identity"].display_name == "탈퇴한 회원"
    assert "bravo_user" not in response.content.decode()

@pytest.mark.django_db(transaction=True)
def test_room_detail_projects_withdrawn_sender_identity(client, users) -> None:
    alpha, bravo, _ = users
    room = get_or_create_direct_room(user_a_id=alpha.pk, user_b_id=bravo.pk)
    service = DefaultChatService(publisher=lambda _room_id, _event: None)
    service.accept(
        room_id=room.pk,
        sender_id=alpha.pk,
        connection_id=uuid4(),
        client_message_id=uuid4(),
        body="withdrawal-safe initial history",
    )
    get_user_model().objects.filter(pk=alpha.pk).update(withdrawn_at=timezone.now())

    client.force_login(bravo)
    session = client.session
    session["account_auth_epoch"] = bravo.auth_epoch
    session.save()

    response = client.get(reverse("chat:room-detail", kwargs={"room_id": room.pk}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "탈퇴한 회원" in content
    assert "alpha_user" not in content



@pytest.mark.django_db(transaction=True)
def test_report_user_projects_withdrawn_target_identity(client, users) -> None:
    alpha, bravo, _ = users
    get_user_model().objects.filter(pk=bravo.pk).update(withdrawn_at=timezone.now())

    client.force_login(alpha)
    session = client.session
    session["account_auth_epoch"] = alpha.auth_epoch
    session.save()
    response = client.get(reverse("moderation:report-user", kwargs={"target_id": bravo.pk}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "탈퇴한 회원" in content
    assert "bravo_user" not in content

@pytest.mark.django_db(transaction=True)
def test_direct_room_rejects_withdrawn_participant(users) -> None:
    alpha, bravo, _ = users
    get_user_model().objects.filter(pk=bravo.pk).update(withdrawn_at=timezone.now())

    with pytest.raises(ChatAuthorizationError):
        get_or_create_direct_room(user_a_id=alpha.pk, user_b_id=bravo.pk)


@pytest.mark.django_db(transaction=True)
def test_withdrawn_user_is_rejected_and_history_uses_tombstone(users) -> None:
    alpha, bravo, _ = users
    room = get_or_create_direct_room(user_a_id=alpha.pk, user_b_id=bravo.pk)
    service = DefaultChatService(publisher=lambda _room_id, _event: None)
    service.accept(
        room_id=room.pk,
        sender_id=alpha.pk,
        connection_id=uuid4(),
        client_message_id=uuid4(),
        body="withdrawal-safe history",
    )
    get_user_model().objects.filter(pk=alpha.pk).update(withdrawn_at=timezone.now())

    with pytest.raises(ChatAuthorizationError):
        service.accept(
            room_id=room.pk,
            sender_id=alpha.pk,
            connection_id=uuid4(),
            client_message_id=uuid4(),
            body="withdrawn users cannot send",
        )


    history = service.history_after(
        room_id=room.pk,
        requesting_user_id=bravo.pk,
        cursor=0,
    )
    assert [message.sender_username for message in history] == ["탈퇴한 회원"]
    assert "alpha_user" not in history[0].sender_username

    with pytest.raises(ChatAuthorizationError):
        service.history_after(
            room_id=room.pk,
            requesting_user_id=alpha.pk,
            cursor=0,
        )
