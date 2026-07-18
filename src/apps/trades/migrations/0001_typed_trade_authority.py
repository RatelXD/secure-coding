from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _lock_cutover_tables(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "LOCK TABLE catalog_product, trades_trade IN SHARE ROW EXCLUSIVE MODE"
        )


def _legacy_trade_matches(trade, product):
    return (
        trade["seller_id"] == product.owner_id
        and trade["buyer_id"] is None
        and trade["kind"] == "LEGACY_SOLD"
        and trade["status"] == "COMPLETED"
        and trade["completed_at"] == product.updated_at
    )


def backfill_legacy_sold(apps, schema_editor):
    alias = schema_editor.connection.alias
    Product = apps.get_model("catalog", "Product")
    Trade = apps.get_model("trades", "Trade")
    _lock_cutover_tables(schema_editor)

    sold = Product.objects.using(alias).filter(sale_state="SOLD").select_for_update()
    sold_products = list(sold.iterator())
    sold_ids = {product.pk for product in sold_products}
    legacy_trades = {
        trade["product_id"]: trade
        for trade in Trade.objects.using(alias)
        .filter(kind="LEGACY_SOLD")
        .values("product_id", "seller_id", "buyer_id", "kind", "status", "completed_at")
    }
    unexpected_legacy_ids = set(legacy_trades) - sold_ids
    if unexpected_legacy_ids:
        raise RuntimeError("legacy Trade rows do not match legacy SOLD products")

    existing_trades = {
        trade["product_id"]: trade
        for trade in Trade.objects.using(alias)
        .filter(product_id__in=sold_ids)
        .values("product_id", "seller_id", "buyer_id", "kind", "status", "completed_at")
    }
    for product in sold_products:
        existing = existing_trades.get(product.pk)
        if existing and not _legacy_trade_matches(existing, product):
            raise RuntimeError(
                f"legacy SOLD provenance mismatch: product={product.pk}"
            )
        if existing is None:
            Trade.objects.using(alias).create(
                product_id=product.pk,
                seller_id=product.owner_id,
                buyer_id=None,
                kind="LEGACY_SOLD",
                status="COMPLETED",
                completed_at=product.updated_at,
            )

    actual_ids = set(
        Trade.objects.using(alias)
        .filter(kind="LEGACY_SOLD", status="COMPLETED")
        .values_list("product_id", flat=True)
    )
    if actual_ids != sold_ids:
        raise RuntimeError("legacy SOLD product ID mismatch after backfill")


def reverse_legacy_sold(apps, schema_editor):
    alias = schema_editor.connection.alias
    Product = apps.get_model("catalog", "Product")
    Trade = apps.get_model("trades", "Trade")
    _lock_cutover_tables(schema_editor)

    if Trade.objects.using(alias).exclude(kind="LEGACY_SOLD").exists():
        raise RuntimeError("cannot reverse typed Trade authority after lifecycle writes")

    sold_products = list(
        Product.objects.using(alias)
        .filter(sale_state="SOLD")
        .select_for_update()
        .iterator()
    )
    sold_ids = {product.pk for product in sold_products}
    legacy_trades = list(
        Trade.objects.using(alias)
        .filter(kind="LEGACY_SOLD")
        .values("product_id", "seller_id", "buyer_id", "kind", "status", "completed_at")
    )
    legacy_ids = {trade["product_id"] for trade in legacy_trades}
    if legacy_ids != sold_ids:
        raise RuntimeError("cannot reverse typed Trade authority after SOLD set changed")

    products_by_id = {product.pk: product for product in sold_products}
    for trade in legacy_trades:
        if not _legacy_trade_matches(trade, products_by_id[trade["product_id"]]):
            raise RuntimeError("cannot reverse typed Trade authority after provenance changed")

    Trade.objects.using(alias).filter(kind="LEGACY_SOLD").delete()


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0003_catalog_authority_expand"),
    ]

    operations = [
        migrations.CreateModel(
            name="Trade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("STANDARD", "일반 거래"), ("LEGACY_SOLD", "레거시 판매 완료")], default="STANDARD", max_length=16)),
                ("status", models.CharField(choices=[("RESERVED", "예약 중"), ("CANCELLED", "예약 취소"), ("COMPLETED", "거래 완료")], max_length=16)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("buyer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchases", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="trades", to="catalog.product")),
                ("seller", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sales", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at", "-pk"),
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(kind="LEGACY_SOLD", status="COMPLETED", buyer__isnull=True, completed_at__isnull=False)
                            | models.Q(kind="STANDARD", buyer__isnull=False)
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
                ],
            },
        ),
        migrations.RunPython(backfill_legacy_sold, reverse_legacy_sold),
    ]
