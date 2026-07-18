from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from django.utils import timezone

from apps.trades.models import Trade

from .models import Product


class ProductState(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    SOLD = "SOLD"


def effective_product_state(*, product: Product, db_now: datetime) -> ProductState:
    """Project lifecycle state exclusively from typed Trade authority.

    ``db_now`` is mandatory so later time-bound lifecycle rules cannot silently use
    an application clock. Phase 7A states are not time-dependent, but invalid or
    naive values are rejected at this single read boundary.
    """

    if timezone.is_naive(db_now):
        raise ValueError("db_now must be timezone-aware")
    status = (
        Trade.objects.filter(
            product_id=product.pk,
            status__in=(Trade.Status.RESERVED, Trade.Status.COMPLETED),
        )
        .values_list("status", flat=True)
        .first()
    )
    if status == Trade.Status.COMPLETED:
        return ProductState.SOLD
    if status == Trade.Status.RESERVED:
        return ProductState.RESERVED
    return ProductState.AVAILABLE


def legacy_trade_is_review_eligible(*, trade: Trade) -> bool:
    """Legacy SOLD rows never fabricate a buyer or review eligibility."""

    return trade.kind != Trade.Kind.LEGACY_SOLD and trade.buyer_id is not None
