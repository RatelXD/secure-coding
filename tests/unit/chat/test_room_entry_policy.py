from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.catalog.models import Product
from apps.chat.models import ProductConversation, Room
from apps.chat.services import get_or_create_direct_room, get_or_create_global_room


User = get_user_model()


def force_login_with_epoch(client: Client, user) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


@pytest.fixture
def chat_users(db):
    return (
        User.objects.create_user(username="inbox_owner", password="test-password-123"),
        User.objects.create_user(username="inbox_peer", password="test-password-123"),
        User.objects.create_user(username="inbox_outsider", password="test-password-123"),
    )


@pytest.mark.django_db
def test_inbox_get_does_not_create_rooms_when_none_exist(client: Client, chat_users) -> None:
    owner, _, _ = chat_users
    force_login_with_epoch(client, owner)

    room_count_before = Room.objects.count()
    response = client.get(reverse("chat:room-list"))

    assert response.status_code == 200
    assert Room.objects.count() == room_count_before


@pytest.mark.django_db
def test_inbox_post_rejects_direct_and_global_creation(client: Client, chat_users) -> None:
    owner, peer, _ = chat_users
    force_login_with_epoch(client, owner)

    direct_response = client.post(reverse("chat:room-list"), {"username": peer.username})
    global_response = client.post(reverse("chat:room-list"))

    assert direct_response.status_code == 405
    assert global_response.status_code == 405
    assert not Room.objects.exists()


@pytest.mark.django_db
def test_public_profile_has_no_direct_chat_action(client: Client, chat_users) -> None:
    owner, peer, _ = chat_users
    force_login_with_epoch(client, owner)

    response = client.get(
        reverse("accounts:user_detail", kwargs={"username": peer.username})
    )

    assert response.status_code == 200
    assert 'action="/chat/"' not in response.content.decode()
    assert f'value="{peer.username}"' not in response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_product_post_creates_then_reuses_authorized_conversation(
    client: Client, chat_users
) -> None:
    seller, buyer, _ = chat_users
    product = Product.objects.create(
        owner=seller,
        title="Policy-safe product chat",
        description="The product route is the only conversation creation path.",
        price=10_000,
    )
    force_login_with_epoch(client, buyer)
    route = reverse("chat:product-room", kwargs={"product_id": product.pk})

    created = client.post(route)
    replayed = client.post(route)

    conversation = ProductConversation.objects.get(product=product, buyer=buyer)
    assert created.status_code == 302
    assert replayed.status_code == 302
    assert created["Location"] == replayed["Location"]
    assert conversation.seller_id == seller.pk
    assert conversation.room.kind == Room.Kind.PRODUCT
    assert ProductConversation.objects.filter(product=product, buyer=buyer).count() == 1


@pytest.mark.django_db(transaction=True)
def test_authorized_legacy_rooms_remain_readable_and_outsider_is_denied(
    client: Client, chat_users
) -> None:
    owner, peer, outsider = chat_users
    global_room = get_or_create_global_room()
    direct_room = get_or_create_direct_room(user_a_id=owner.pk, user_b_id=peer.pk)
    force_login_with_epoch(client, owner)

    inbox = client.get(reverse("chat:room-list"))
    direct_detail = client.get(
        reverse("chat:room-detail", kwargs={"room_id": direct_room.pk})
    )
    global_detail = client.get(
        reverse("chat:room-detail", kwargs={"room_id": global_room.pk})
    )
    force_login_with_epoch(client, outsider)
    outsider_detail = client.get(
        reverse("chat:room-detail", kwargs={"room_id": direct_room.pk})
    )
    outsider_history = client.get(
        reverse("chat:room-history", kwargs={"room_id": direct_room.pk})
    )

    assert inbox.status_code == 200
    assert str(global_room.pk) in inbox.content.decode()
    assert str(direct_room.pk) in inbox.content.decode()
    assert direct_detail.status_code == 200
    assert global_detail.status_code == 200
    assert outsider_detail.status_code == 404
    assert outsider_history.status_code == 404
