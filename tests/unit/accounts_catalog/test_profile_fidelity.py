from __future__ import annotations

from uuid import uuid4

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Favorite, Product, ProductImage
from apps.trades.models import Review, ReviewVisibilityAction, Trade


pytestmark = pytest.mark.django_db


def _login(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def _product(owner: User, title: str) -> Product:
    return Product.objects.create(
        owner=owner,
        title=title,
        description=f"{title} 설명",
        price=12_000,
    )


def _completed_trade(product: Product, seller: User, buyer: User) -> Trade:
    return Trade.objects.create(
        product=product,
        seller=seller,
        buyer=buyer,
        status=Trade.Status.COMPLETED,
        completed_at=timezone.now(),
    )


def test_own_profile_uses_authoritative_stats_and_sold_filter() -> None:
    """Given owned products and account activity, the sold profile filter uses persisted relations."""
    owner = User.objects.create_user(
        username="profile_owner",
        password="long-password-123",
        bio="동네 거래를 소중히 여깁니다.",
    )
    buyer = User.objects.create_user(username="profile_buyer", password="long-password-123")
    available = _product(owner, "판매 중 상품")
    sold = _product(owner, "판매 완료 상품")
    _completed_trade(sold, owner, buyer)
    Favorite.objects.create(user=owner, product=available)
    pending = ProductImage.objects.create(
        product=sold,
        position=0,
        promotion_state="PENDING",
        image=f"product-images/owned/{sold.pk}/pending.png",
        owned_key=f"product-images/owned/{sold.pk}/pending.png",
        sha256="0" * 64,
        byte_size=64,
        width=8,
        height=8,
    )
    promoted = ProductImage.objects.create(
        product=sold,
        position=1,
        promotion_state="PROMOTED",
        image=f"product-images/owned/{sold.pk}/promoted.png",
        owned_key=f"product-images/owned/{sold.pk}/promoted.png",
        sha256="1" * 64,
        byte_size=64,
        width=8,
        height=8,
    )
    client = Client()
    _login(client, owner)

    response = client.get(reverse("accounts:profile"), {"status": "sold"})

    assert response.status_code == 200
    assert response.context["transaction_count"] == 1
    assert response.context["favorite_count"] == 1
    assert response.context["profile_filter"] == "sold"
    assert list(response.context["product_page"].object_list) == [sold]
    content = response.content.decode()
    assert promoted.image.url in content
    assert pending.image.url not in content
    assert 'data-profile-product-grid="own"' in content


def test_public_profile_filters_products_and_hides_moderated_reviews() -> None:
    """Given public activity, the profile exposes only visible aggregate data and no direct-chat entry."""
    seller = User.objects.create_user(
        username="public_seller",
        password="long-password-123",
        email="private@example.test",
        bio="깨끗하게 사용한 물건을 나눕니다.",
    )
    buyer = User.objects.create_user(username="public_buyer", password="long-password-123")
    moderator = User.objects.create_user(username="review_moderator", password="long-password-123")
    available = _product(seller, "공개 판매 중")
    sold_visible = _product(seller, "후기 공개 판매 완료")
    sold_hidden = _product(seller, "후기 숨김 판매 완료")
    visible_trade = _completed_trade(sold_visible, seller, buyer)
    hidden_trade = _completed_trade(sold_hidden, seller, buyer)
    Review.objects.create(
        trade=visible_trade,
        author=buyer,
        subject=seller,
        rating=5,
        body="공개 후기",
    )
    hidden_review = Review.objects.create(
        trade=hidden_trade,
        author=buyer,
        subject=seller,
        rating=4,
        body="숨김 후기",
    )
    ReviewVisibilityAction.objects.create(
        review=hidden_review,
        actor=moderator,
        kind=ReviewVisibilityAction.Kind.HIDE,
        reason="공개 제외 검증",
        idempotency_key=uuid4(),
    )
    client = Client()
    _login(client, buyer)

    response = client.get(
        reverse("accounts:user_detail", args=(seller.username,)),
        {"status": "available"},
    )

    assert response.status_code == 200
    assert response.context["activity_trade_count"] == 2
    assert response.context["activity_review_count"] == 1
    assert response.context["profile_filter"] == "available"
    assert list(response.context["product_page"].object_list) == [available]
    content = response.content.decode()
    assert "private@example.test" not in content
    assert reverse("moderation:report-user", args=(seller.pk,)) in content
    assert 'action="/chat/"' not in content
    assert f'value="{seller.username}"' not in content
    assert 'data-profile-product-grid="public"' in content


def test_public_profile_paginates_the_complete_visible_gallery() -> None:
    """Given more than one card row, the public profile exposes stable server-side pagination."""
    seller = User.objects.create_user(username="paged_seller", password="long-password-123")
    products = [_product(seller, f"페이지 상품 {index}") for index in range(9)]

    response = Client().get(
        reverse("accounts:user_detail", args=(seller.username,)),
        {"page": "2"},
    )

    assert response.status_code == 200
    assert response.context["product_page"].number == 2
    assert response.context["product_page"].paginator.count == len(products)
    assert len(response.context["product_page"].object_list) == 1
    assert "data-profile-pagination" in response.content.decode()
