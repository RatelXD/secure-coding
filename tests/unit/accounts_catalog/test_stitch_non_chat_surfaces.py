from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import Product, ProductImage


pytestmark = pytest.mark.django_db


def _login(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def _product(owner: User, **changes: str | int) -> Product:
    values: dict[str, str | int | User] = {
        "owner": owner,
        "title": "Stitch product",
        "description": "A safely rendered product description.",
        "price": 12_000,
    }
    values.update(changes)
    return Product.objects.create(**values)


def _image(product: Product, *, position: int, state: str, name: str) -> ProductImage:
    return ProductImage.objects.create(
        product=product,
        position=position,
        promotion_state=state,
        image=f"product-images/owned/{product.pk}/{name}.png",
        owned_key=f"product-images/owned/{product.pk}/{name}.png",
        sha256="0" * 64,
        byte_size=64,
        width=8,
        height=8,
    )


def test_home_renders_the_first_promoted_gallery_image() -> None:
    """Given a product with pending and promoted images, home shows only its promoted gallery asset."""
    owner = User.objects.create_user(username="home_owner", password="long-password-123")
    product = _product(owner)
    pending = _image(product, position=0, state="PENDING", name="pending")
    promoted = _image(product, position=1, state="PROMOTED", name="promoted")

    response = Client().get(reverse("home"))

    content = response.content.decode()
    assert response.status_code == 200
    assert promoted.image.url in content
    assert pending.image.url not in content


def test_catalog_list_renders_only_the_first_promoted_image() -> None:
    """Given a gallery with a pending first row, search keeps the promoted image public."""
    owner = User.objects.create_user(username="list_owner", password="long-password-123")
    product = _product(owner, title="Searchable surface")
    pending = _image(product, position=0, state="PENDING", name="pending")
    promoted = _image(product, position=1, state="PROMOTED", name="promoted")

    response = Client().get(reverse("catalog:list"), {"q": "Searchable"})

    content = response.content.decode()
    assert response.status_code == 200
    assert promoted.image.url in content
    assert pending.image.url not in content


def test_detail_gallery_keeps_promoted_images_in_position_order() -> None:
    """Given out-of-order creation, detail exposes the promoted gallery in explicit position order."""
    owner = User.objects.create_user(username="gallery_owner", password="long-password-123")
    product = _product(owner)
    first = _image(product, position=0, state="PROMOTED", name="first")
    pending = _image(product, position=1, state="PENDING", name="pending")
    last = _image(product, position=2, state="PROMOTED", name="last")

    response = Client().get(reverse("catalog:detail", args=(product.pk,)))

    content = response.content.decode()
    assert response.status_code == 200
    assert content.index(first.image.url) < content.index(last.image.url)
    assert pending.image.url not in content
    assert "12,000원" in content


def test_detail_gallery_exposes_neighbor_controls_for_multiple_images() -> None:
    """Given a multi-image gallery, detail provides semantic previous and next controls."""
    owner = User.objects.create_user(username="gallery_controls", password="long-password-123")
    product = _product(owner)
    _image(product, position=0, state="PROMOTED", name="first")
    _image(product, position=1, state="PROMOTED", name="last")

    response = Client().get(reverse("catalog:detail", args=(product.pk,)))

    content = response.content.decode()
    assert response.status_code == 200
    assert "data-gallery-previous" in content
    assert "data-gallery-next" in content


def test_catalog_form_keeps_native_validation_and_empty_state() -> None:
    """Given an invalid owner submission, the server returns the form and field error state."""
    owner = User.objects.create_user(username="form_owner", password="long-password-123")
    client = Client()
    _login(client, owner)

    response = client.post(reverse("catalog:create"), {"title": "", "description": "", "price": ""})

    assert response.status_code == 200
    assert 'class="form-field form-field--upload' in response.content.decode()
    assert 'class="form-field form-field--error' in response.content.decode()


def test_detail_keeps_owner_and_buyer_controls_separate() -> None:
    """Given owner and buyer sessions, edit controls and product chat remain server-authorized."""
    owner = User.objects.create_user(username="detail_owner", password="long-password-123")
    buyer = User.objects.create_user(username="detail_buyer", password="long-password-123")
    product = _product(owner)

    owner_client = Client()
    _login(owner_client, owner)
    owner_response = owner_client.get(reverse("catalog:detail", args=(product.pk,)))

    buyer_client = Client()
    _login(buyer_client, buyer)
    buyer_response = buyer_client.get(reverse("catalog:detail", args=(product.pk,)))

    assert reverse("catalog:update", args=(product.pk,)) in owner_response.content.decode()
    assert reverse("chat:product-room", args=(product.pk,)) not in owner_response.content.decode()
    assert reverse("catalog:update", args=(product.pk,)) not in buyer_response.content.decode()
    assert reverse("chat:product-room", args=(product.pk,)) in buyer_response.content.decode()
