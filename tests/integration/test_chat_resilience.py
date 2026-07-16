from __future__ import annotations

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.chat.models import ChatMessage
from apps.chat.services import (
    ChatAuthorizationError,
    ChatRateLimited,
    ChatReplayConflict,
    DefaultChatService,
    DeliveryState,
    get_or_create_direct_room,
    get_or_create_global_room,
)


User = get_user_model()


class ChatResilienceIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.sender = User.objects.create_user(username="chat_sender")
        self.peer = User.objects.create_user(username="chat_peer")
        self.outsider = User.objects.create_user(username="chat_outsider")
        self.global_room = get_or_create_global_room()

    def test_replay_returns_original_without_duplicate_store_or_publish(self) -> None:
        published: list[tuple[int, dict[str, object]]] = []
        service = DefaultChatService(
            publisher=lambda room_id, event: published.append((room_id, event))
        )
        connection_id = uuid4()
        client_message_id = uuid4()

        accepted = service.accept(
            room_id=self.global_room.pk,
            sender_id=self.sender.pk,
            connection_id=connection_id,
            client_message_id=client_message_id,
            body="  저장할 메시지  ",
        )
        replayed = service.accept(
            room_id=self.global_room.pk,
            sender_id=self.sender.pk,
            connection_id=uuid4(),
            client_message_id=client_message_id,
            body="저장할 메시지",
        )

        self.assertFalse(accepted.replayed)
        self.assertTrue(replayed.replayed)
        self.assertEqual(replayed.server_message_id, accepted.server_message_id)
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(len(published), 1)

        with self.assertRaises(ChatReplayConflict):
            service.accept(
                room_id=self.global_room.pk,
                sender_id=self.sender.pk,
                connection_id=connection_id,
                client_message_id=client_message_id,
                body="다른 내용",
            )
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(len(published), 1)

    def test_publish_failure_is_persisted_as_degraded_and_history_converges(self) -> None:
        def unavailable_publisher(room_id: int, event: dict[str, object]) -> None:
            raise RuntimeError("simulated fan-out outage")

        service = DefaultChatService(publisher=unavailable_publisher)
        accepted = service.accept(
            room_id=self.global_room.pk,
            sender_id=self.sender.pk,
            connection_id=uuid4(),
            client_message_id=uuid4(),
            body="Redis 장애에도 저장",
        )

        self.assertEqual(accepted.delivery, DeliveryState.DEGRADED)
        message = ChatMessage.objects.get(pk=accepted.server_message_id)
        self.assertEqual(message.delivery, ChatMessage.Delivery.DEGRADED)
        history = service.history_after(
            room_id=self.global_room.pk,
            requesting_user_id=self.sender.pk,
            cursor=0,
            limit=100,
        )
        self.assertEqual([item.server_message_id for item in history], [message.pk])
        self.assertEqual(history[0].body, "Redis 장애에도 저장")

    def test_direct_room_outsider_is_denied_and_rate_rejection_is_not_stored(self) -> None:
        direct_room = get_or_create_direct_room(
            user_a_id=self.sender.pk,
            user_b_id=self.peer.pk,
        )
        service = DefaultChatService(publisher=lambda room_id, event: None)
        with self.assertRaises(ChatAuthorizationError):
            service.accept(
                room_id=direct_room.pk,
                sender_id=self.outsider.pk,
                connection_id=uuid4(),
                client_message_id=uuid4(),
                body="권한 없는 메시지",
            )

        connection_id = uuid4()
        for index in range(10):
            service.accept(
                room_id=self.global_room.pk,
                sender_id=self.sender.pk,
                connection_id=connection_id,
                client_message_id=uuid4(),
                body=f"rate-{index}",
            )
        with self.assertRaises(ChatRateLimited) as raised:
            service.accept(
                room_id=self.global_room.pk,
                sender_id=self.sender.pk,
                connection_id=connection_id,
                client_message_id=uuid4(),
                body="rate-rejected",
            )

        self.assertGreaterEqual(raised.exception.retry_after, 1)
        self.assertEqual(
            ChatMessage.objects.filter(sender=self.sender, room=self.global_room).count(),
            10,
        )
