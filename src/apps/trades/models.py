from django.conf import settings
from django.db import models

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models.functions import Now


class Trade(models.Model):
    """Typed product lifecycle authority.

    Phase 7A only creates LEGACY_SOLD rows. Interactive lifecycle commands belong
    to Phase 7B's TradeService and must not write Product.sale_state.
    """

    class Kind(models.TextChoices):
        STANDARD = "STANDARD", "일반 거래"
        LEGACY_SOLD = "LEGACY_SOLD", "레거시 판매 완료"

    class Status(models.TextChoices):
        RESERVED = "RESERVED", "예약 중"
        CANCELLED = "CANCELLED", "예약 취소"
        COMPLETED = "COMPLETED", "거래 완료"

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="trades",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchases",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.STANDARD)
    status = models.CharField(max_length=16, choices=Status.choices)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="LEGACY_SOLD",
                        status="COMPLETED",
                        buyer__isnull=True,
                        completed_at__isnull=False,
                    )
                    | models.Q(
                        kind="STANDARD",
                        buyer__isnull=False,
                    )
                ),
                name="trades_buyer_kind_typed",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="COMPLETED", completed_at__isnull=False)
                    | models.Q(status__in=("RESERVED", "CANCELLED"), completed_at__isnull=True)
                ),
                name="trades_completed_at_typed",
            ),
            models.UniqueConstraint(
                fields=("product",),
                condition=models.Q(status__in=("RESERVED", "COMPLETED")),
                name="trades_one_noncancelled_per_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id}:{self.kind}:{self.status}"


class TradeStatusHistory(models.Model):
    """Append-only evidence of every server-authoritative lifecycle transition."""

    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="status_history")
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16, choices=Trade.Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("trade_id", "version")
        constraints = [
            models.UniqueConstraint(
                fields=("trade", "version"),
                name="trades_history_trade_version_unique",
            )
        ]


class Review(models.Model):
    """An immutable review authored by one party to a completed standard trade."""

    trade = models.ForeignKey(Trade, on_delete=models.PROTECT, related_name="reviews")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authored_reviews",
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1), MaxValueValidator(5))
    )
    body = models.TextField(max_length=1_000)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("trade", "author"),
                name="trades_review_direction_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(author=models.F("subject")),
                name="trades_review_distinct_parties",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="trades_review_rating_1_5",
            ),
            models.CheckConstraint(
                condition=~models.Q(body=""),
                name="trades_review_body_required",
            ),
        ]


class ReviewVisibilityAction(models.Model):
    """Append-only moderation decision; effective visibility is the latest decision."""

    class Kind(models.TextChoices):
        HIDE = "HIDE", "Hide"
        RESTORE = "RESTORE", "Restore"

    review = models.ForeignKey(
        Review,
        on_delete=models.PROTECT,
        related_name="visibility_actions",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="review_visibility_actions",
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    reason = models.TextField(max_length=500)
    idempotency_key = models.UUIDField(unique=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        ordering = ("created_at", "pk")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(reason=""),
                name="trades_review_visibility_reason_required",
            )
        ]
