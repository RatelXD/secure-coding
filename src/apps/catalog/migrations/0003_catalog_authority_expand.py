import hashlib
from io import BytesIO

import apps.catalog.models
from django.core.files.base import ContentFile
from django.db import migrations, models
import django.db.models.deletion
from PIL import Image


CATEGORIES = (
    ("DIGITAL_APPLIANCES", "디지털·가전", 0),
    ("LIVING_KITCHEN", "생활·주방", 1),
    ("FURNITURE_INTERIOR", "가구·인테리어", 2),
    ("FASHION_GOODS", "의류·잡화", 3),
    ("SPORTS_HOBBIES", "스포츠·취미", 4),
    ("BOOKS", "도서", 5),
    ("OTHER", "기타", 6),
)

# Versioned, deliberately coarse city/county/district examples. Exact addresses
# and coordinates are not part of this authority.
REGIONS = (
    ("KR-11-680", "서울특별시 강남구", "2026-07"),
    ("KR-41-110", "경기도 수원시", "2026-07"),
    ("KR-41-830", "경기도 양평군", "2026-07"),
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def _read_bounded(storage, name):
    with storage.open(name, "rb") as source:
        raw = source.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise RuntimeError("image exceeds byte limit")
    return raw


def seed_and_copy_legacy(apps, schema_editor):
    alias = schema_editor.connection.alias
    Category = apps.get_model("catalog", "Category")
    Region = apps.get_model("catalog", "Region")
    Product = apps.get_model("catalog", "Product")
    ProductImage = apps.get_model("catalog", "ProductImage")

    for code, label, display_order in CATEGORIES:
        Category.objects.using(alias).update_or_create(
            code=code,
            defaults={"label": label, "display_order": display_order},
        )
    for code, label, fixture_version in REGIONS:
        Region.objects.using(alias).update_or_create(
            code=code,
            defaults={"label": label, "fixture_version": fixture_version},
        )

    Product.objects.using(alias).filter(category__isnull=True).update(
        category_id="OTHER",
        region_source="LEGACY_UNSET",
        region_id=None,
    )

    image_field = ProductImage._meta.get_field("image")
    storage = image_field.storage
    for product in Product.objects.using(alias).exclude(image="").iterator():
        source_name = product.image.name
        if not source_name or not storage.exists(source_name):
            raise RuntimeError(f"legacy product image is missing: product={product.pk}")
        try:
            raw = _read_bounded(storage, source_name)
        except RuntimeError as exc:
            raise RuntimeError(
                f"legacy image exceeds byte limit: product={product.pk}"
            ) from exc
        checksum = hashlib.sha256(raw).hexdigest()
        try:
            with Image.open(BytesIO(raw)) as image:
                image_format = (image.format or "").upper()
                if image_format not in FORMATS or getattr(image, "n_frames", 1) != 1:
                    raise RuntimeError("unsupported legacy image")
                width, height = image.size
                if not 0 < width <= 4096 or not 0 < height <= 4096:
                    raise RuntimeError("legacy image dimensions out of bounds")
                image.verify()
        except Exception as exc:
            raise RuntimeError(f"invalid legacy image: product={product.pk}") from exc

        destination = (
            f"product-images/migrated/{product.pk}/{checksum}.{FORMATS[image_format]}"
        )
        if destination == source_name:
            raise RuntimeError(f"legacy and gallery keys alias: product={product.pk}")
        if storage.exists(destination):
            try:
                existing = _read_bounded(storage, destination)
            except RuntimeError as exc:
                raise RuntimeError(
                    f"migrated image exceeds byte limit: product={product.pk}"
                ) from exc
            if hashlib.sha256(existing).hexdigest() != checksum:
                raise RuntimeError(f"migrated image checksum conflict: product={product.pk}")
        else:
            saved_name = storage.save(destination, ContentFile(raw))
            if saved_name != destination:
                raise RuntimeError(f"storage refused deterministic image key: product={product.pk}")
        try:
            copied = _read_bounded(storage, destination)
        except RuntimeError as exc:
            raise RuntimeError(
                f"migrated image exceeds byte limit: product={product.pk}"
            ) from exc
        if hashlib.sha256(copied).hexdigest() != checksum:
            raise RuntimeError(f"migrated image checksum mismatch: product={product.pk}")
        ProductImage.objects.using(alias).update_or_create(
            product_id=product.pk,
            position=0,
            defaults={
                "image": destination,
                "sha256": checksum,
                "byte_size": len(raw),
                "width": width,
                "height": height,
            },
        )


def reverse_seed_and_copy(apps, schema_editor):
    alias = schema_editor.connection.alias
    ProductImage = apps.get_model("catalog", "ProductImage")
    migrated_images = list(
        ProductImage.objects.using(alias).values("pk", "product_id", "image", "sha256")
    )
    for image in migrated_images:
        name = image["image"]
        expected_names = {
            f"product-images/migrated/{image['product_id']}/{image['sha256']}.{extension}"
            for extension in FORMATS.values()
        }
        if name not in expected_names:
            raise RuntimeError(
                "cannot reverse catalog authority after a new gallery image write"
            )

    # External storage is not transactionally coupled to this migration. Retain
    # copied blobs; schema rollback removes only the migration-owned rows.
    ProductImage.objects.using(alias).filter(
        pk__in=[image["pk"] for image in migrated_images]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_product_price_sale_state")]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("code", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("label", models.CharField(max_length=40, unique=True)),
                ("display_order", models.PositiveSmallIntegerField(unique=True)),
            ],
            options={"ordering": ("display_order", "code")},
        ),
        migrations.CreateModel(
            name="Region",
            fields=[
                ("code", models.CharField(max_length=16, primary_key=True, serialize=False)),
                ("label", models.CharField(max_length=80)),
                ("fixture_version", models.CharField(default="2026-07", max_length=16)),
            ],
            options={"ordering": ("label", "code")},
        ),
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="catalog.category",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="region",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="catalog.region",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="region_source",
            field=models.CharField(
                choices=[
                    ("LEGACY_UNSET", "지역 미설정"),
                    ("SELECTED", "상품 지역 선택"),
                    ("INHERITED", "사용자 기본 지역 상속"),
                ],
                default="LEGACY_UNSET",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="archived_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.CreateModel(
            name="ProductImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(max_length=255, upload_to=apps.catalog.models.product_image_upload_to)),
                ("position", models.PositiveSmallIntegerField()),
                ("sha256", models.CharField(editable=False, max_length=64)),
                ("byte_size", models.PositiveIntegerField()),
                ("width", models.PositiveIntegerField()),
                ("height", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="images", to="catalog.product")),
            ],
            options={
                "ordering": ("position", "pk"),
                "constraints": [
                    models.UniqueConstraint(fields=("product", "position"), name="catalog_product_image_position_unique"),
                    models.CheckConstraint(condition=models.Q(position__gte=0, position__lte=3), name="catalog_product_image_position_0_3"),
                    models.CheckConstraint(condition=models.Q(byte_size__gt=0, byte_size__lte=5242880), name="catalog_product_image_bytes_bounded"),
                    models.CheckConstraint(condition=models.Q(width__gt=0, width__lte=4096, height__gt=0, height__lte=4096), name="catalog_product_image_dimensions_bounded"),
                ],
            },
        ),
        migrations.RunPython(seed_and_copy_legacy, reverse_seed_and_copy),
        migrations.AlterField(
            model_name="product",
            name="category",
            field=models.ForeignKey(
                default="OTHER",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="catalog.category",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(region_source="LEGACY_UNSET", region__isnull=True)
                    | models.Q(region_source__in=("SELECTED", "INHERITED"), region__isnull=False)
                ),
                name="catalog_product_region_source_valid",
            ),
        ),
    ]
