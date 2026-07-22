from __future__ import annotations

import unicodedata

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def normalize_products(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    pending = []
    for product in Product.objects.only("pk", "title", "description").iterator(chunk_size=500):
        title = unicodedata.normalize("NFC", product.title)
        description = unicodedata.normalize("NFC", product.description)
        if title != product.title or description != product.description:
            product.title = title
            product.description = description
            pending.append(product)
        if len(pending) == 500:
            Product.objects.bulk_update(pending, ("title", "description"))
            pending.clear()
    if pending:
        Product.objects.bulk_update(pending, ("title", "description"))


def install_postgres_nfc_constraint(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            'ALTER TABLE "catalog_product" ADD CONSTRAINT "catalog_product_text_nfc" '
            "CHECK (title = normalize(title, NFC) AND description = normalize(description, NFC))"
        )


def remove_postgres_nfc_constraint(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            'ALTER TABLE "catalog_product" DROP CONSTRAINT IF EXISTS "catalog_product_text_nfc"'
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0006_reject_product_image_legacy_key_alias"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="demo_key",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="Favorite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorites", to="catalog.product")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorite_products", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.CreateModel(
            name="ProductMetric",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("favorite_count", models.PositiveBigIntegerField(default=0)),
                ("view_count", models.PositiveBigIntegerField(default=0)),
                ("product_chat_count", models.PositiveBigIntegerField(default=0)),
                ("completed_trade_count", models.PositiveBigIntegerField(default=0)),
                ("recomputed_at", models.DateTimeField(auto_now=True)),
                ("product", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="metric", to="catalog.product")),
            ],
        ),
        migrations.CreateModel(
            name="ProductView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("viewed_on", models.DateField()),
                ("viewer_digest", models.CharField(max_length=64)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="views", to="catalog.product")),
            ],
        ),
        migrations.AddConstraint(
            model_name="favorite",
            constraint=models.UniqueConstraint(fields=("user", "product"), name="catalog_favorite_user_product_unique"),
        ),
        migrations.AddConstraint(
            model_name="productview",
            constraint=models.UniqueConstraint(fields=("product", "viewed_on", "viewer_digest"), name="catalog_view_product_day_digest_unique"),
        ),
        migrations.AddIndex(
            model_name="productview",
            index=models.Index(fields=["product", "viewed_on"], name="catalog_view_product_day_idx"),
        ),
        migrations.RunPython(normalize_products, migrations.RunPython.noop),
        migrations.RunPython(install_postgres_nfc_constraint, remove_postgres_nfc_constraint),
    ]
