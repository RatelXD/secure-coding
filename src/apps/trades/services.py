from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.functions import Now
from django.utils import timezone

from apps.catalog.models import Product
from apps.moderation.models import ModerationAction

from .models import Trade, TradeStatusHistory


class TradeError(Exception):
    """A generalized lifecycle rejection safe to expose at an HTTP boundary."""


class TradeConflict(TradeError):
    pass


@dataclass(frozen=True)
class TradeResult:
    trade: Trade
    created: bool = False


def _lock_active_users(*user_ids: int):
    User = get_user_model()
    users = {
        user.pk: user
        for user in User.objects.select_for_update().filter(pk__in=sorted(set(user_ids)))
    }
    if len(users) != len(set(user_ids)):
        raise TradeError("TRADE_NOT_ALLOWED")
    if any(not user.is_active or user.withdrawn_at is not None for user in users.values()):
        raise TradeError("TRADE_NOT_ALLOWED")
    dormant = ModerationAction.objects.filter(
        kind=ModerationAction.Kind.USER_DORMANCY,
        target_user_id__in=users,
        starts_at__lte=Now(),
        expires_at__gt=Now(),
    ).exists()
    if dormant:
        raise TradeError("TRADE_NOT_ALLOWED")
    return users


def _product_is_hidden(product_id: int) -> bool:
    return ModerationAction.objects.filter(
        kind=ModerationAction.Kind.PRODUCT_HIDE,
        target_product_id=product_id,
        starts_at__lte=Now(),
        expires_at__gt=Now(),
    ).exists()


def _record(trade: Trade, *, old_status: str, actor_id: int) -> None:
    TradeStatusHistory.objects.create(
        trade=trade,
        from_status=old_status,
        to_status=trade.status,
        actor_id=actor_id,
        version=trade.version,
    )


class TradeService:
    """The sole write authority for product lifecycle state."""

    @staticmethod
    @transaction.atomic
    def reserve(*, actor, product_id: int) -> TradeResult:
        product_ref = Product.objects.only("pk", "owner_id").filter(pk=product_id).first()
        if (
            product_ref is None
            or actor.pk == product_ref.owner_id
            or _product_is_hidden(product_ref.pk)
        ):
            raise TradeError("TRADE_NOT_ALLOWED")
        _lock_active_users(actor.pk, product_ref.owner_id)
        product = Product.objects.select_for_update().get(pk=product_id)
        existing = Trade.objects.select_for_update().filter(
            product=product,
            status__in=(Trade.Status.RESERVED, Trade.Status.COMPLETED),
        ).first()
        if existing:
            if existing.status == Trade.Status.RESERVED and existing.buyer_id == actor.pk:
                return TradeResult(existing, created=False)
            raise TradeConflict("TRADE_CONFLICT")
        try:
            trade = Trade.objects.create(
                product=product,
                seller_id=product.owner_id,
                buyer_id=actor.pk,
                kind=Trade.Kind.STANDARD,
                status=Trade.Status.RESERVED,
                version=1,
            )
            _record(trade, old_status="", actor_id=actor.pk)
        except IntegrityError as exc:
            raise TradeConflict("TRADE_CONFLICT") from exc
        return TradeResult(trade, created=True)

    @staticmethod
    @transaction.atomic
    def cancel(*, actor, trade_id: int, expected_version: int | None = None) -> TradeResult:
        trade_ref = Trade.objects.only("pk", "seller_id", "buyer_id", "product_id").filter(pk=trade_id).first()
        if trade_ref is None or actor.pk not in (trade_ref.seller_id, trade_ref.buyer_id):
            raise TradeError("TRADE_NOT_ALLOWED")
        _lock_active_users(trade_ref.seller_id, trade_ref.buyer_id)
        Product.objects.select_for_update().get(pk=trade_ref.product_id)
        trade = Trade.objects.select_for_update().get(pk=trade_id)
        if trade.status == Trade.Status.CANCELLED:
            return TradeResult(trade)
        if trade.status != Trade.Status.RESERVED:
            raise TradeConflict("TRADE_CONFLICT")
        if expected_version is not None and trade.version != expected_version:
            raise TradeConflict("TRADE_CONFLICT")
        old_status = trade.status
        trade.status = Trade.Status.CANCELLED
        trade.version += 1
        trade.save(update_fields=("status", "version", "updated_at"))
        _record(trade, old_status=old_status, actor_id=actor.pk)
        return TradeResult(trade)

    @staticmethod
    @transaction.atomic
    def complete(*, actor, trade_id: int, expected_version: int | None = None) -> TradeResult:
        trade_ref = Trade.objects.only("pk", "seller_id", "buyer_id", "product_id").filter(pk=trade_id).first()
        if trade_ref is None or actor.pk != trade_ref.seller_id:
            raise TradeError("TRADE_NOT_ALLOWED")
        _lock_active_users(trade_ref.seller_id, trade_ref.buyer_id)
        Product.objects.select_for_update().get(pk=trade_ref.product_id)
        trade = Trade.objects.select_for_update().get(pk=trade_id)
        if trade.status == Trade.Status.COMPLETED:
            return TradeResult(trade)
        if trade.status != Trade.Status.RESERVED:
            raise TradeConflict("TRADE_CONFLICT")
        if expected_version is not None and trade.version != expected_version:
            raise TradeConflict("TRADE_CONFLICT")
        old_status = trade.status
        trade.status = Trade.Status.COMPLETED
        trade.completed_at = timezone.now()
        trade.version += 1
        trade.save(update_fields=("status", "completed_at", "version", "updated_at"))
        _record(trade, old_status=old_status, actor_id=actor.pk)
        return TradeResult(trade)
