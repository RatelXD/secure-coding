from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils import timezone


CATEGORY_CHOICES = (
    ("DIGITAL_APPLIANCES", "디지털·가전"),
    ("LIVING_KITCHEN", "생활·주방"),
    ("FURNITURE_INTERIOR", "가구·인테리어"),
    ("FASHION_GOODS", "의류·잡화"),
    ("SPORTS_HOBBIES", "스포츠·취미"),
    ("BOOKS", "도서"),
    ("OTHER", "기타"),
)


class Category(models.Model):
    code = models.CharField(primary_key=True, max_length=32)
    label = models.CharField(max_length=40, unique=True)
    display_order = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ("display_order", "code")

    def __str__(self) -> str:
        return self.label


class Region(models.Model):
    """Versioned city/county/district allowlist; never stores exact addresses."""

    code = models.CharField(primary_key=True, max_length=16)
    label = models.CharField(max_length=80)
    fixture_version = models.CharField(max_length=16, default="2026-07")

    class Meta:
        ordering = ("label", "code")

    def __str__(self) -> str:
        return self.label


class Product(models.Model):
    """Owner-controlled product content; lifecycle state is projected from Trade."""

    class SaleState(models.TextChoices):
        AVAILABLE = "AVAILABLE", "판매 중"
        SOLD = "SOLD", "판매 완료"

    class RegionSource(models.TextChoices):
        LEGACY_UNSET = "LEGACY_UNSET", "지역 미설정"
        SELECTED = "SELECTED", "상품 지역 선택"
        INHERITED = "INHERITED", "사용자 기본 지역 상속"

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
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        default="OTHER",
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    region_source = models.CharField(
        max_length=16,
        choices=RegionSource.choices,
        default=RegionSource.LEGACY_UNSET,
    )
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)
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
            models.CheckConstraint(
                condition=(
                    models.Q(region_source="LEGACY_UNSET", region__isnull=True)
                    | models.Q(region_source__in=("SELECTED", "INHERITED"), region__isnull=False)
                ),
                name="catalog_product_region_source_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.title


def product_image_upload_to(instance: ProductImage, filename: str) -> str:
    extension = PurePosixPath(filename).suffix.lower().lstrip(".")
    extension = "jpg" if extension == "jpeg" else extension
    if extension not in {"jpg", "png", "webp"}:
        raise ValidationError("지원하지 않는 상품 이미지 확장자입니다.")
    return f"product-images/owned/{instance.product_id}/{uuid4()}.{extension}"


class ProductImage(models.Model):
    """An independently owned, ordered gallery image (never a legacy key alias)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=product_image_upload_to, max_length=255)
    position = models.PositiveSmallIntegerField()
    sha256 = models.CharField(max_length=64, editable=False)
    byte_size = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    owned_key = models.CharField(max_length=255, editable=False, default="")
    promotion_state = models.CharField(
        max_length=16,
        choices=(("PENDING", "Pending"), ("PROMOTED", "Promoted")),
        default="PROMOTED",
        editable=False,
    )

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "position"),
                name="catalog_product_image_position_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=0, position__lte=3),
                name="catalog_product_image_position_0_3",
            ),
            models.CheckConstraint(
                condition=models.Q(byte_size__gt=0, byte_size__lte=5 * 1024 * 1024),
                name="catalog_product_image_bytes_bounded",
            ),
            models.CheckConstraint(
                condition=models.Q(width__gt=0, width__lte=4096, height__gt=0, height__lte=4096),
                name="catalog_product_image_dimensions_bounded",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.image and self.product_id and self.image.name == self.product.image.name:
            raise ValidationError({"image": "레거시 이미지와 별도 소유 key를 사용해야 합니다."})
        if self.image and self.image.name and self.image.storage.exists(self.image.name):
            with self.image.storage.open(self.image.name, "rb") as stored:
                digest = hashlib.sha256(stored.read()).hexdigest()
            if self.sha256 and digest != self.sha256:
                raise ValidationError({"sha256": "저장 이미지 checksum이 일치하지 않습니다."})

    def __str__(self) -> str:
        return f"{self.product_id}:{self.position}"


class ProductImageDeletionIntent(models.Model):
    """Durable outbox entry for an owned gallery key awaiting storage deletion."""

    storage_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("pk",)

    def record_attempt(self) -> None:
        self.attempts += 1
        self.last_attempt_at = timezone.now()
        self.save(update_fields=("attempts", "last_attempt_at"))

    def __str__(self) -> str:
        return self.storage_key
