from django.db import migrations


POSTGRES_FORWARD = (
    """
CREATE OR REPLACE FUNCTION catalog_reject_product_image_legacy_key_alias()
RETURNS trigger AS $$
BEGIN
    IF NEW.image <> '' AND EXISTS (
        SELECT 1
        FROM catalog_product
        WHERE id = NEW.product_id AND image = NEW.image
    ) THEN
        RAISE EXCEPTION 'catalog_product_image_legacy_key_alias';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER catalog_productimage_legacy_key_alias
BEFORE INSERT OR UPDATE OF product_id, image ON catalog_productimage
FOR EACH ROW EXECUTE FUNCTION catalog_reject_product_image_legacy_key_alias();
""",
)

POSTGRES_REVERSE = (
    "DROP TRIGGER IF EXISTS catalog_productimage_legacy_key_alias ON catalog_productimage;",
    "DROP FUNCTION IF EXISTS catalog_reject_product_image_legacy_key_alias();",
)

SQLITE_FORWARD = (
    """
CREATE TRIGGER catalog_productimage_legacy_key_alias_insert
BEFORE INSERT ON catalog_productimage
WHEN NEW.image <> '' AND EXISTS (
    SELECT 1
    FROM catalog_product
    WHERE id = NEW.product_id AND image = NEW.image
)
BEGIN
    SELECT RAISE(ABORT, 'catalog_product_image_legacy_key_alias');
END;
""",
    """
CREATE TRIGGER catalog_productimage_legacy_key_alias_update
BEFORE UPDATE OF product_id, image ON catalog_productimage
WHEN NEW.image <> '' AND EXISTS (
    SELECT 1
    FROM catalog_product
    WHERE id = NEW.product_id AND image = NEW.image
)
BEGIN
    SELECT RAISE(ABORT, 'catalog_product_image_legacy_key_alias');
END;
""",
)

SQLITE_REVERSE = (
    "DROP TRIGGER IF EXISTS catalog_productimage_legacy_key_alias_insert;",
    "DROP TRIGGER IF EXISTS catalog_productimage_legacy_key_alias_update;",
)


def _execute(schema_editor, *, postgres_sql, sqlite_sql):
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        statements = postgres_sql
    elif connection.vendor == "sqlite":
        statements = sqlite_sql
    else:
        raise RuntimeError(
            f"unsupported database for catalog image authority trigger: {connection.vendor}"
        )
    for statement in statements:
        schema_editor.execute(statement)


def add_product_image_legacy_key_guard(apps, schema_editor):
    _execute(
        schema_editor,
        postgres_sql=POSTGRES_FORWARD,
        sqlite_sql=SQLITE_FORWARD,
    )


def remove_product_image_legacy_key_guard(apps, schema_editor):
    _execute(
        schema_editor,
        postgres_sql=POSTGRES_REVERSE,
        sqlite_sql=SQLITE_REVERSE,
    )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_product_image_lifecycle_outbox")]

    operations = [
        migrations.RunPython(
            add_product_image_legacy_key_guard,
            remove_product_image_legacy_key_guard,
        )
    ]
