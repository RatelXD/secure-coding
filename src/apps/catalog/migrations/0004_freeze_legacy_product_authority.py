import hashlib
from io import BytesIO

from django.db import migrations
from PIL import Image


MAX_IMAGE_BYTES = 5 * 1024 * 1024
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

POSTGRES_FORWARD = (
    """
CREATE OR REPLACE FUNCTION catalog_reject_legacy_product_mutation()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Product rows are archived, not deleted after catalog authority cutover';
    END IF;
    IF NEW.sale_state IS DISTINCT FROM OLD.sale_state THEN
        RAISE EXCEPTION 'Product.sale_state is frozen; Trade is lifecycle authority';
    END IF;
    IF NEW.image IS DISTINCT FROM OLD.image THEN
        RAISE EXCEPTION 'Product.image is frozen legacy media';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER catalog_product_legacy_frozen
BEFORE UPDATE OR DELETE ON catalog_product
FOR EACH ROW EXECUTE FUNCTION catalog_reject_legacy_product_mutation();
""",
)

POSTGRES_REVERSE = (
    "DROP TRIGGER IF EXISTS catalog_product_legacy_frozen ON catalog_product;",
    "DROP FUNCTION IF EXISTS catalog_reject_legacy_product_mutation();",
)

SQLITE_FORWARD = (
    """
CREATE TRIGGER catalog_product_sale_state_frozen
BEFORE UPDATE OF sale_state ON catalog_product
WHEN NEW.sale_state IS NOT OLD.sale_state
BEGIN
    SELECT RAISE(ABORT, 'Product.sale_state is frozen; Trade is lifecycle authority');
END;
""",
    """
CREATE TRIGGER catalog_product_legacy_image_frozen
BEFORE UPDATE OF image ON catalog_product
WHEN NEW.image IS NOT OLD.image
BEGIN
    SELECT RAISE(ABORT, 'Product.image is frozen legacy media');
END;
""",
    """
CREATE TRIGGER catalog_product_delete_frozen
BEFORE DELETE ON catalog_product
BEGIN
    SELECT RAISE(ABORT, 'Product rows are archived, not deleted after catalog authority cutover');
END;
""",
)

SQLITE_REVERSE = (
    "DROP TRIGGER IF EXISTS catalog_product_sale_state_frozen;",
    "DROP TRIGGER IF EXISTS catalog_product_legacy_image_frozen;",
    "DROP TRIGGER IF EXISTS catalog_product_delete_frozen;",
)


def _execute(schema_editor, *, postgres_sql, sqlite_sql):
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        statements = postgres_sql
    elif connection.vendor == "sqlite":
        statements = sqlite_sql
    else:
        raise RuntimeError(
            f"unsupported database for catalog authority trigger: {connection.vendor}"
        )
    for statement in statements:
        schema_editor.execute(statement)


def _lock_cutover_tables(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "LOCK TABLE catalog_product, catalog_productimage, trades_trade "
            "IN ACCESS EXCLUSIVE MODE"
        )


def _read_bounded(storage, name):
    with storage.open(name, "rb") as source:
        raw = source.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise RuntimeError("image exceeds byte limit")
    return raw


def _legacy_trade_matches(trade, product):
    return (
        trade["seller_id"] == product.owner_id
        and trade["buyer_id"] is None
        and trade["kind"] == "LEGACY_SOLD"
        and trade["status"] == "COMPLETED"
        and trade["completed_at"] == product.updated_at
    )


def _revalidate_legacy_sold(apps, alias):
    Product = apps.get_model("catalog", "Product")
    Trade = apps.get_model("trades", "Trade")
    sold_products = list(
        Product.objects.using(alias).filter(sale_state="SOLD").select_for_update()
    )
    sold_ids = {product.pk for product in sold_products}
    legacy_trades = list(
        Trade.objects.using(alias)
        .filter(kind="LEGACY_SOLD")
        .values("product_id", "seller_id", "buyer_id", "kind", "status", "completed_at")
    )
    if (
        len(legacy_trades) != len(sold_ids)
        or {trade["product_id"] for trade in legacy_trades} != sold_ids
    ):
        raise RuntimeError("legacy SOLD product ID mismatch at catalog authority cutover")

    products_by_id = {product.pk: product for product in sold_products}
    for trade in legacy_trades:
        if not _legacy_trade_matches(trade, products_by_id[trade["product_id"]]):
            raise RuntimeError(
                f"legacy SOLD provenance mismatch at catalog authority cutover: "
                f"product={trade['product_id']}"
            )


def _revalidate_legacy_images(apps, alias):
    Product = apps.get_model("catalog", "Product")
    ProductImage = apps.get_model("catalog", "ProductImage")
    storage = ProductImage._meta.get_field("image").storage

    for product in Product.objects.using(alias).exclude(image="").select_for_update():
        source_name = product.image.name
        if not source_name or not storage.exists(source_name):
            raise RuntimeError(f"legacy product image is missing: product={product.pk}")
        try:
            raw = _read_bounded(storage, source_name)
            with Image.open(BytesIO(raw)) as image:
                image_format = (image.format or "").upper()
                extension = FORMATS[image_format]
                image.verify()
        except Exception as exc:
            raise RuntimeError(
                f"legacy product image mismatch at catalog authority cutover: "
                f"product={product.pk}"
            ) from exc

        checksum = hashlib.sha256(raw).hexdigest()
        expected_name = f"product-images/migrated/{product.pk}/{checksum}.{extension}"
        try:
            copied = ProductImage.objects.using(alias).get(
                product_id=product.pk, position=0
            )
            copied_raw = _read_bounded(storage, copied.image.name)
        except Exception as exc:
            raise RuntimeError(
                f"legacy product image copy missing at catalog authority cutover: "
                f"product={product.pk}"
            ) from exc

        if (
            copied.image.name != expected_name
            or copied.sha256 != checksum
            or copied.byte_size != len(raw)
            or copied_raw != raw
            or hashlib.sha256(copied_raw).hexdigest() != checksum
        ):
            raise RuntimeError(
                f"legacy product image copy mismatch at catalog authority cutover: "
                f"product={product.pk}"
            )


def freeze_legacy_fields(apps, schema_editor):
    _lock_cutover_tables(schema_editor)
    _execute(
        schema_editor,
        postgres_sql=POSTGRES_FORWARD,
        sqlite_sql=SQLITE_FORWARD,
    )
    alias = schema_editor.connection.alias
    _revalidate_legacy_sold(apps, alias)
    _revalidate_legacy_images(apps, alias)


def unfreeze_legacy_fields(apps, schema_editor):
    _execute(
        schema_editor,
        postgres_sql=POSTGRES_REVERSE,
        sqlite_sql=SQLITE_REVERSE,
    )


class Migration(migrations.Migration):
    atomic = True
    dependencies = [
        ("catalog", "0003_catalog_authority_expand"),
        ("trades", "0001_typed_trade_authority"),
    ]

    operations = [migrations.RunPython(freeze_legacy_fields, unfreeze_legacy_fields)]
