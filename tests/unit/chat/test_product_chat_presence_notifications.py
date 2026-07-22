from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.catalog.models import Product
from apps.chat.models import ChatMessage, RoomParticipant
from apps.chat.presence import PresenceService, authorized_presence_peers
from apps.chat.services import (
    ChatAuthorizationError,
    DefaultChatService,
    get_or_create_product_conversation,
)
from apps.notifications.models import Notification
from apps.notifications.services import (
    NotificationAuthorizationError,
    mark_notification_read,
)


class MemoryPresenceBackend:
    def __init__(self) -> None:
        self.members: dict[str, dict[str, float]] = {}

    async def touch(self, key: str, member: str, expires_at: float) -> None:
        self.members.setdefault(key, {})[member] = expires_at

    async def remove(self, key: str, member: str) -> None:
        self.members.get(key, {}).pop(member, None)

    async def count_live(self, key: str, now: float) -> int:
        values = self.members.get(key, {})
        self.members[key] = {member: expiry for member, expiry in values.items() if expiry >= now}
        return len(self.members[key])


@pytest.fixture
def product_parties(db):
    users = get_user_model()
    seller = users.objects.create_user(username="seller", password="long-test-password-1")
    buyer = users.objects.create_user(username="buyer", password="long-test-password-2")
    outsider = users.objects.create_user(username="outsider", password="long-test-password-3")
    product = Product.objects.create(
        owner=seller,
        title="권위 상품",
        description="설명",
        price=10000,
    )
    return seller, buyer, outsider, product


@pytest.mark.django_db(transaction=True)
def test_product_conversation_reuses_message_pipeline_and_rejects_outsider(product_parties):
    seller, buyer, outsider, product = product_parties
    conversation = get_or_create_product_conversation(product_id=product.pk, actor_id=buyer.pk)
    replay = get_or_create_product_conversation(product_id=product.pk, actor_id=buyer.pk)

    assert replay.pk == conversation.pk
    assert set(RoomParticipant.objects.filter(room=conversation.room).values_list("user_id", flat=True)) == {
        seller.pk,
        buyer.pk,
    }
    assert authorized_presence_peers(room_id=conversation.room_id, user_id=buyer.pk) == (seller.pk,)

    service = DefaultChatService(publisher=lambda _room, _event: None)
    accepted = service.accept(
        room_id=conversation.room_id,
        sender_id=buyer.pk,
        connection_id=uuid4(),
        client_message_id=uuid4(),
        body="상품 문의입니다",
    )
    notification = Notification.objects.get()
    assert notification.recipient_id == seller.pk
    assert notification.event_key == f"chat.message:{accepted.server_message_id}"
    assert notification.payload["product_id"] == product.pk

    with pytest.raises(ChatAuthorizationError):
        service.history_after(
            room_id=conversation.room_id,
            requesting_user_id=outsider.pk,
            cursor=0,
            limit=100,
        )


@pytest.mark.django_db(transaction=True)
def test_product_chat_rechecks_visibility_and_server_identity(product_parties):
    seller, buyer, _, product = product_parties
    conversation = get_or_create_product_conversation(product_id=product.pk, actor_id=buyer.pk)
    product.archived_at = timezone.now()
    product.save(update_fields=("archived_at",))

    with pytest.raises(ChatAuthorizationError):
        DefaultChatService(publisher=lambda _room, _event: None).accept(
            room_id=conversation.room_id,
            sender_id=buyer.pk,
            connection_id=uuid4(),
            client_message_id=uuid4(),
            body="늦은 메시지",
        )
    assert not ChatMessage.objects.exists()
    assert not Notification.objects.exists()
    with pytest.raises(ChatAuthorizationError):
        get_or_create_product_conversation(product_id=product.pk, actor_id=seller.pk)


@pytest.mark.django_db(transaction=True)
def test_presence_is_relationship_scoped_and_multitab_safe(product_parties):
    seller, buyer, outsider, product = product_parties
    conversation = get_or_create_product_conversation(product_id=product.pk, actor_id=buyer.pk)
    backend = MemoryPresenceBackend()
    service = PresenceService(backend)
    first, second = uuid4(), uuid4()

    async_to_sync(service.online)(room_id=conversation.room_id, user_id=seller.pk, connection_id=first)
    async_to_sync(service.online)(room_id=conversation.room_id, user_id=seller.pk, connection_id=second)
    assert async_to_sync(service.peer_states)(room_id=conversation.room_id, user_id=buyer.pk) == {
        seller.pk: True
    }
    async_to_sync(service.offline)(room_id=conversation.room_id, user_id=seller.pk, connection_id=first)
    assert async_to_sync(service.peer_states)(room_id=conversation.room_id, user_id=buyer.pk)[seller.pk]
    async_to_sync(service.offline)(room_id=conversation.room_id, user_id=seller.pk, connection_id=second)
    assert not async_to_sync(service.peer_states)(room_id=conversation.room_id, user_id=buyer.pk)[seller.pk]
    with pytest.raises(ChatAuthorizationError):
        authorized_presence_peers(room_id=conversation.room_id, user_id=outsider.pk)


@pytest.mark.django_db(transaction=True)
def test_notification_expiry_and_read_are_database_and_recipient_authoritative(product_parties):
    seller, buyer, _, _ = product_parties
    notification = Notification.objects.create(
        recipient=seller,
        event_key="test:event",
        kind="TEST",
        payload={},
        created_at=timezone.now() - timedelta(days=300),
        expires_at=timezone.now() - timedelta(days=1),
    )
    notification.refresh_from_db()
    assert notification.expires_at - notification.created_at == timedelta(days=90)

    with pytest.raises(NotificationAuthorizationError):
        mark_notification_read(notification_id=notification.pk, recipient_id=buyer.pk)
    notification.refresh_from_db()
    assert notification.read_at is None
    mark_notification_read(notification_id=notification.pk, recipient_id=seller.pk)
    notification.refresh_from_db()
    assert notification.read_at is not None


def test_notification_scheduler_refuses_test_environment() -> None:
    with pytest.raises(CommandError, match="must not start in tests"):
        call_command("run_notification_purge_scheduler")
