from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.http import QueryDict
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.engagement import metric_recompute_delta
from apps.catalog.models import Favorite, Product, ProductImage, ProductMetric, ProductView, Region
from apps.catalog.search import parse_product_search, search_products
from apps.trades.models import Trade

pytestmark = pytest.mark.django_db


def product(owner, *, title="검색 상품", region=None, price=10000):
    return Product.objects.create(
        owner=owner,
        title=title,
        description="안전한 상품 설명",
        price=price,
        category_id="OTHER",
        region=region,
        region_source=(
            Product.RegionSource.SELECTED if region else Product.RegionSource.LEGACY_UNSET
        ),
    )


def login(client, user):
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def test_favorite_commands_are_idempotent_and_lists_are_private():
    owner = User.objects.create_user(username="metric_owner", password="long-password-123")
    member = User.objects.create_user(username="metric_member", password="long-password-123")
    other = User.objects.create_user(username="metric_other", password="long-password-123")
    item = product(owner)
    client = Client()
    login(client, member)

    url = reverse("catalog:favorite", args=(item.pk,))
    assert client.post(url, {"action": "add"}).status_code == 302
    assert client.post(url, {"action": "add"}).status_code == 302
    assert Favorite.objects.filter(user=member, product=item).count() == 1
    assert ProductMetric.objects.get(product=item).favorite_count == 1
    assert item in client.get(reverse("catalog:favorites")).context["products"]

    other_client = Client()
    login(other_client, other)
    assert item not in other_client.get(reverse("catalog:favorites")).context["products"]
    assert client.post(url, {"action": "remove"}).status_code == 302
    assert client.post(url, {"action": "remove"}).status_code == 302
    assert ProductMetric.objects.get(product=item).favorite_count == 0


def test_view_is_once_per_session_product_utc_date_and_owner_is_excluded(monkeypatch):
    owner = User.objects.create_user(username="view_owner", password="long-password-123")
    item = product(owner)
    client = Client()
    detail = reverse("catalog:detail", args=(item.pk,))

    assert client.get(detail).status_code == 200
    assert client.get(detail).status_code == 200
    assert ProductView.objects.filter(product=item).count() == 1
    assert not any(field.name in {"ip", "session_key", "created_at"} for field in ProductView._meta.fields)

    monkeypatch.setattr(
        "apps.catalog.engagement.timezone.now",
        lambda: datetime(2099, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert client.get(detail).status_code == 200
    assert ProductView.objects.filter(product=item).count() == 2

    owner_client = Client()
    login(owner_client, owner)
    assert owner_client.get(detail).status_code == 200
    assert ProductView.objects.filter(product=item).count() == 2
    assert metric_recompute_delta(product_id=item.pk) == {
        "favorite_count": 0,
        "view_count": 0,
        "product_chat_count": 0,
        "completed_trade_count": 0,
    }


def test_search_combines_category_region_state_and_excludes_legacy_region():
    seller = User.objects.create_user(username="search_owner", password="long-password-123")
    buyer = User.objects.create_user(username="search_buyer", password="long-password-123")
    region = Region.objects.get(pk="KR-11-680")
    available = product(seller, title="같은 검색어 판매", region=region, price=10000)
    reserved = product(seller, title="같은 검색어 예약", region=region, price=20000)
    sold = product(seller, title="같은 검색어 완료", region=region, price=30000)
    legacy_region = product(seller, title="같은 검색어 지역없음", price=15000)
    Trade.objects.create(product=reserved, seller=seller, buyer=buyer, status=Trade.Status.RESERVED)
    Trade.objects.create(
        product=sold,
        seller=seller,
        buyer=buyer,
        status=Trade.Status.COMPLETED,
        completed_at=datetime.now(UTC),
    )

    response = Client().get(
        reverse("catalog:list"),
        {
            "q": "같은 검색어",
            "category": "OTHER",
            "region": region.pk,
            "status": "available",
            "min_price": "10000",
            "max_price": "20000",
            "sort": "price_asc",
        },
    )
    assert response.status_code == 200
    assert [row.pk for row in response.context["products"]] == [available.pk, reserved.pk]
    assert response.context["products"][1].effective_state == "RESERVED"
    assert legacy_region.pk not in [row.pk for row in response.context["products"]]

    sold_response = Client().get(reverse("catalog:list"), {"status": "sold"})
    assert [row.pk for row in sold_response.context["products"]] == [sold.pk]


def test_invalid_duplicate_and_extra_search_never_queries_products():
    client = Client()
    cases = [
        [("region", "KR-11-680"), ("region", "KR-11-680")],
        {"page": "501"},
        {"q": "bad\x00query"},
        {"owner__username": "admin"},
    ]
    for params in cases:
        with CaptureQueriesContext(connection) as captured:
            response = client.get(reverse("catalog:list"), params)
        assert response.status_code == 400
        assert not any('FROM "catalog_product"' in query["sql"] for query in captured.captured_queries)


def test_product_text_is_normalized_before_storage():
    owner = User.objects.create_user(username="nfc_owner", password="long-password-123")
    item = product(owner, title="한글")
    item.refresh_from_db()
    assert item.title == "한글"


def test_search_service_uses_only_count_and_bounded_slice_queries():
    owner = User.objects.create_user(username="query_owner", password="long-password-123")
    for index in range(21):
        product(owner, title=f"검색 {index:02d}")
    search = parse_product_search(QueryDict("q=%EA%B2%80%EC%83%89&page=1"))
    with CaptureQueriesContext(connection) as captured:
        products, total = search_products(search)
    assert total == 21
    assert len(products) == 20
    assert len(captured.captured_queries) == 2


def test_demo_bootstrap_is_guarded_exact_and_repairable(tmp_path: Path):
    with override_settings(
        APP_ENV="development",
        DEMO_CATALOG_BOOTSTRAP_ENABLED=True,
        MEDIA_ROOT=tmp_path,
    ):
        call_command("bootstrap_demo_catalog")
        call_command("bootstrap_demo_catalog")
    owner = User.objects.get(username="demo_catalog_owner")
    assert not owner.has_usable_password()
    assert Product.objects.filter(owner=owner).count() == 17
    assert Product.objects.filter(owner=owner, demo_key__isnull=False).count() == 17
    assert sum(item.images.count() for item in Product.objects.filter(owner=owner)) == 50
    for item in Product.objects.filter(owner=owner):
        images = list(ProductImage.objects.filter(product=item).order_by("position"))
        assert 2 <= len(images) <= 4
        assert [image.position for image in images] == list(range(len(images)))
        assert all(
            image.image.name == image.owned_key
            and image.promotion_state == "PROMOTED"
            and image.byte_size > 0
            and image.width > 0
            and image.height > 0
            for image in images
        )

    with override_settings(APP_ENV="production", DEMO_CATALOG_BOOTSTRAP_ENABLED=False):
        with pytest.raises(CommandError):
            call_command("bootstrap_demo_catalog")
