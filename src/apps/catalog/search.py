from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery
from django.http import QueryDict

from apps.moderation.services import visible_products
from apps.trades.models import Trade

from .models import Category, Product, ProductImage, Region

_ALLOWED_KEYS = frozenset(
    {"q", "status", "min_price", "max_price", "sort", "page", "category", "region"}
)
_SORTS = {
    "newest": ("-created_at", "-pk"),
    "price_asc": ("price", "-pk"),
    "price_desc": ("-price", "-pk"),
}


class InvalidProductSearch(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProductSearch:
    q: str
    status: str
    min_price: int | None
    max_price: int | None
    sort: str
    page: int
    category: str
    region: str


def parse_product_search(params: QueryDict) -> ProductSearch:
    unknown = set(params) - _ALLOWED_KEYS
    if unknown or any(len(params.getlist(key)) != 1 for key in params):
        raise InvalidProductSearch("허용되지 않거나 중복된 검색 조건입니다.")

    q = unicodedata.normalize("NFC", params.get("q", "").strip())
    if len(q) > 100 or any(unicodedata.category(char) in {"Cc", "Cf"} for char in q):
        raise InvalidProductSearch("검색어는 제어문자 없이 100자 이하여야 합니다.")

    status = params.get("status", "")
    if status not in {"", "available", "sold"}:
        raise InvalidProductSearch("판매 상태가 올바르지 않습니다.")
    sort = params.get("sort", "newest") or "newest"
    if sort not in _SORTS:
        raise InvalidProductSearch("정렬 조건이 올바르지 않습니다.")
    page = _bounded_integer(params.get("page", "1") or "1", minimum=1, maximum=500)
    minimum = _optional_price(params.get("min_price", ""))
    maximum = _optional_price(params.get("max_price", ""))
    if minimum is not None and maximum is not None and minimum > maximum:
        raise InvalidProductSearch("최소 가격은 최대 가격보다 클 수 없습니다.")

    category = params.get("category", "")
    region = params.get("region", "")
    if category and not Category.objects.filter(code=category).exists():
        raise InvalidProductSearch("카테고리가 올바르지 않습니다.")
    if region and not Region.objects.filter(code=region).exists():
        raise InvalidProductSearch("지역이 올바르지 않습니다.")
    return ProductSearch(q, status, minimum, maximum, sort, page, category, region)


def search_products(search: ProductSearch) -> tuple[list[Product], int]:
    completed = Trade.objects.filter(
        product_id=OuterRef("pk"),
        status=Trade.Status.COMPLETED,
    )
    lifecycle_status = (
        Trade.objects.filter(
            product_id=OuterRef("pk"),
            status__in=(Trade.Status.RESERVED, Trade.Status.COMPLETED),
        )
        .values("status")[:1]
    )
    primary_image = (
        ProductImage.objects.filter(
            product_id=OuterRef("pk"),
            promotion_state="PROMOTED",
        )
        .order_by("position", "pk")
        .values("image")[:1]
    )
    queryset: QuerySet[Product] = visible_products(
        Product.objects.filter(archived_at__isnull=True)
    ).annotate(
        has_completed_trade=Exists(completed),
        lifecycle_status=Subquery(lifecycle_status),
        primary_image_key=Subquery(primary_image),
    )
    if search.q:
        queryset = queryset.filter(Q(title__icontains=search.q) | Q(description__icontains=search.q))
    if search.status == "available":
        queryset = queryset.filter(has_completed_trade=False)
    elif search.status == "sold":
        queryset = queryset.filter(has_completed_trade=True)
    if search.min_price is not None:
        queryset = queryset.filter(price__gte=search.min_price)
    if search.max_price is not None:
        queryset = queryset.filter(price__lte=search.max_price)
    if search.category:
        queryset = queryset.filter(category_id=search.category)
    if search.region:
        queryset = queryset.filter(region_id=search.region)
    queryset = queryset.select_related("owner", "category", "region")
    total = queryset.count()
    start = (search.page - 1) * 20
    products = list(queryset.order_by(*_SORTS[search.sort])[start : start + 20])
    storage = ProductImage._meta.get_field("image").storage
    for product in products:
        product.search_image_url = (
            storage.url(product.primary_image_key) if product.primary_image_key else ""
        )
    return products, total


def _optional_price(raw: str) -> int | None:
    if raw == "":
        return None
    return _bounded_integer(raw, minimum=1, maximum=999_999_999_999)


def _bounded_integer(raw: str, *, minimum: int, maximum: int) -> int:
    if not raw.isascii() or not raw.isdecimal():
        raise InvalidProductSearch("숫자 검색 조건이 올바르지 않습니다.")
    try:
        value = int(Decimal(raw))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidProductSearch("숫자 검색 조건이 올바르지 않습니다.") from exc
    if not minimum <= value <= maximum:
        raise InvalidProductSearch("숫자 검색 조건이 허용 범위를 벗어났습니다.")
    return value
