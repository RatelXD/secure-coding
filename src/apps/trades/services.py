from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Now
from django.utils import timezone

from apps.catalog.models import Product
from apps.moderation.models import ModerationAction

from .models import Review, ReviewVisibilityAction, Trade, TradeStatusHistory


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
        release__isnull=True,
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
        release__isnull=True,
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


class ReviewAuthorityError(ValueError):
    """A review command failed without disclosing trade-party state."""


@dataclass(frozen=True)
class ReviewCreation:
    review: Review
    created: bool


def _normalize_review_body(body: str) -> str:
    if not isinstance(body, str):
        raise ReviewAuthorityError("review cannot be accepted")
    normalized = unicodedata.normalize("NFC", body.strip())
    if not 1 <= len(normalized) <= 1_000:
        raise ReviewAuthorityError("review cannot be accepted")
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in normalized):
        raise ReviewAuthorityError("review cannot be accepted")
    return normalized


def create_review(*, actor, trade_id: int, rating: int, body: str) -> ReviewCreation:
    """Create one immutable directional review from authoritative completed-trade facts."""
    if (
        isinstance(trade_id, bool)
        or not isinstance(trade_id, int)
        or trade_id <= 0
        or isinstance(rating, bool)
        or not isinstance(rating, int)
        or not 1 <= rating <= 5
        or not getattr(actor, "is_authenticated", False)
        or not actor.is_active
    ):
        raise ReviewAuthorityError("review cannot be accepted")
    normalized_body = _normalize_review_body(body)

    with transaction.atomic():
        try:
            trade = Trade.objects.select_for_update().get(pk=trade_id)
        except Trade.DoesNotExist as exc:
            raise ReviewAuthorityError("review cannot be accepted") from exc
        if (
            trade.kind != Trade.Kind.STANDARD
            or trade.status != Trade.Status.COMPLETED
            or trade.buyer_id is None
            or actor.pk not in {trade.seller_id, trade.buyer_id}
        ):
            raise ReviewAuthorityError("review cannot be accepted")
        subject_id = trade.buyer_id if actor.pk == trade.seller_id else trade.seller_id
        try:
            review, created = Review.objects.get_or_create(
                trade=trade,
                author_id=actor.pk,
                defaults={
                    "subject_id": subject_id,
                    "rating": rating,
                    "body": normalized_body,
                },
            )
        except IntegrityError as exc:
            raise ReviewAuthorityError("review cannot be accepted") from exc
        if not created and (
            review.subject_id != subject_id
            or review.rating != rating
            or review.body != normalized_body
        ):
            raise ReviewAuthorityError("review replay does not match")
        return ReviewCreation(review=review, created=created)


def public_reviews(queryset: QuerySet[Review] | None = None) -> QuerySet[Review]:
    """Exclude reviews whose latest append-only visibility decision is HIDE."""
    queryset = queryset if queryset is not None else Review.objects.all()
    latest_kind = (
        ReviewVisibilityAction.objects.filter(review_id=OuterRef("pk"))
        .order_by("-created_at", "-pk")
        .values("kind")[:1]
    )
    return queryset.annotate(_latest_visibility=Subquery(latest_kind)).filter(
        Q(_latest_visibility__isnull=True)
        | ~Q(_latest_visibility=ReviewVisibilityAction.Kind.HIDE)
    )
