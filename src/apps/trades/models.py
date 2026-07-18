from django.conf import settings
from django.db import models


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
