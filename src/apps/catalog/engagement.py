from __future__ import annotations

import hashlib
import hmac
from datetime import UTC

from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.trades.models import Trade

from .models import Favorite, Product, ProductMetric, ProductView

def recompute_product_metric(*, product_id: int) -> ProductMetric:
    """Replace the rebuildable projection from authoritative relation rows."""
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        counts = {
            "favorite_count": Favorite.objects.filter(product=product).count(),
            "view_count": ProductView.objects.filter(product=product).count(),
            "product_chat_count": _product_chat_count(product_id=product_id),
            "completed_trade_count": Trade.objects.filter(
                product_id=product_id,
                status=Trade.Status.COMPLETED,
            ).count(),
        }
        metric, _ = ProductMetric.objects.update_or_create(product=product, defaults=counts)
        return metric


def metric_recompute_delta(*, product_id: int) -> dict[str, int]:
    """Return field deltas before repairing the projection for release checks."""
    existing = ProductMetric.objects.filter(product_id=product_id).first()
    old = {
        field: getattr(existing, field, 0)
        for field in (
            "favorite_count",
            "view_count",
            "product_chat_count",
            "completed_trade_count",
        )
    }
    current = recompute_product_metric(product_id=product_id)
    return {field: getattr(current, field) - value for field, value in old.items()}


def set_favorite(*, user_id: int, product_id: int, active: bool) -> ProductMetric:
    """Apply an idempotent owner-scoped favorite command and repair its projection."""
    with transaction.atomic():
        try:
            User.objects.select_for_update().get(
                pk=user_id,
                is_active=True,
                withdrawn_at__isnull=True,
            )
        except User.DoesNotExist as exc:
            raise PermissionDenied("관심 상품을 변경할 수 없습니다.") from exc
        Product.objects.select_for_update().get(pk=product_id)
        if active:
            Favorite.objects.get_or_create(user_id=user_id, product_id=product_id)
        else:
            Favorite.objects.filter(user_id=user_id, product_id=product_id).delete()
        return recompute_product_metric(product_id=product_id)


def record_product_view(*, request: HttpRequest, product: Product) -> ProductMetric:
    """Count at most one non-owner browser view per product and UTC date."""
    if request.user.is_authenticated and request.user.pk == product.owner_id:
        return recompute_product_metric(product_id=product.pk)
    if request.session.session_key is None:
        request.session.create()
    viewed_on = timezone.now().astimezone(UTC).date()
    digest_key = hmac.new(
        settings.SECRET_KEY.encode(),
        f"catalog-view:{product.pk}:{viewed_on.isoformat()}".encode(),
        hashlib.sha256,
    ).digest()
    viewer_digest = hmac.new(
        digest_key,
        request.session.session_key.encode(),
        hashlib.sha256,
    ).hexdigest()
    ProductView.objects.get_or_create(
        product=product,
        viewed_on=viewed_on,
        viewer_digest=viewer_digest,
    )
    return recompute_product_metric(product_id=product.pk)


def _product_chat_count(*, product_id: int) -> int:
    """Count unique buyers when the product-chat authority is installed."""
    try:
        conversation_model = apps.get_model("chat", "ProductConversation")
    except LookupError:
        return 0
    field_names = {field.name for field in conversation_model._meta.fields}
    queryset = conversation_model.objects.filter(product_id=product_id)
    if "buyer" in field_names:
        return queryset.values("buyer_id").distinct().count()
    return queryset.count()
