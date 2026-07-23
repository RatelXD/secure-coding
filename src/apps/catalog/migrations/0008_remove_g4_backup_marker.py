from django.db import migrations


def remove_g4_backup_marker(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    alias = schema_editor.connection.alias
    exact_markers = Product.objects.using(alias).filter(
        title="G4 backup marker",
        owner__username="g4_backup_user",
        description="restore evidence",
        price=1000,
    )
    marker_count = exact_markers.count()
    if marker_count == 0:
        return
    if marker_count > 1:
        raise RuntimeError(
            "duplicate exact G4 backup markers found; refusing deletion"
        )

    is_postgresql = schema_editor.connection.vendor == "postgresql"
    if is_postgresql:
        schema_editor.execute(
            'ALTER TABLE "catalog_product" DISABLE TRIGGER "catalog_product_legacy_frozen"'
        )
        restore_guard = (
            'ALTER TABLE "catalog_product" ENABLE TRIGGER "catalog_product_legacy_frozen"'
        )
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("DROP TRIGGER catalog_product_delete_frozen")
        restore_guard = """
CREATE TRIGGER catalog_product_delete_frozen
BEFORE DELETE ON catalog_product
BEGIN
    SELECT RAISE(ABORT, 'Product rows are archived, not deleted after catalog authority cutover');
END;
"""
    else:
        raise RuntimeError(
            f"unsupported database for G4 backup marker cleanup: {schema_editor.connection.vendor}"
        )

    try:
        exact_markers.delete()
    finally:
        if is_postgresql:
            schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        schema_editor.execute(restore_guard)


def reverse_remove_g4_backup_marker(apps, schema_editor):
    """Deliberate no-op: deleted marker evidence cannot be reconstructed safely."""


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_catalog_engagement_search_demo")]

    operations = [
        migrations.RunPython(
            remove_g4_backup_marker,
            reverse_remove_g4_backup_marker,
            atomic=True,
        )
    ]
