from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models


class Product(models.Model):
    """Owner-controlled product content; moderation visibility is derived elsewhere."""
    class SaleState(models.TextChoices):
        AVAILABLE = "AVAILABLE", "판매 중"
        SOLD = "SOLD", "판매 완료"


    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="products",
    )
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=2_000)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(1)],
    )
    sale_state = models.CharField(
        max_length=16,
        choices=SaleState.choices,
        default=SaleState.AVAILABLE,
    )
    image = models.ImageField(
        upload_to="product-images/",
        blank=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=("owner", "-created_at"), name="catalog_owner_created_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=1),
                name="catalog_product_price_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(sale_state__in=("AVAILABLE", "SOLD")),
                name="catalog_product_sale_state_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.title
