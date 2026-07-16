from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


class Product(models.Model):
    """Owner-controlled product content; moderation visibility is derived elsewhere."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="products",
    )
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=2_000)
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

    def __str__(self) -> str:
        return self.title
