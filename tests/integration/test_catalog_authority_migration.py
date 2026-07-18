import hashlib
import importlib
import inspect
from io import BytesIO
from types import SimpleNamespace

import pytest
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from PIL import Image

pytestmark = pytest.mark.django_db(transaction=True)

CATALOG_BEFORE = ("catalog", "0002_product_price_sale_state")
CATALOG_AFTER = ("catalog", "0006_reject_product_image_legacy_key_alias")
TRADES_AFTER = ("trades", "0001_typed_trade_authority")
CATALOG_FREEZE = ("catalog", "0004_freeze_legacy_product_authority")


def _png_bytes(color="blue") -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color).save(output, format="PNG")
    return output.getvalue()


def test_upgrade_copy_backfill_and_reverse_preserve_legacy_bytes(settings, tmp_path) -> None:
    """G7A-CAT-MIG-001: copy/count/checksum/typed backfill과 reverse를 한 경로에서 검증한다."""
    settings.MEDIA_ROOT = tmp_path
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([CATALOG_BEFORE, ("trades", None)])
        before_apps = executor.loader.project_state([CATALOG_BEFORE]).apps
        User = before_apps.get_model("accounts", "User")
        Product = before_apps.get_model("catalog", "Product")
        owner = User.objects.create(username="migration_owner", password="unusable")

        payload = _png_bytes()
        source_name = Product._meta.get_field("image").storage.save(
            "product-images/legacy.png", ContentFile(payload)
        )
        sold = Product.objects.create(
            owner_id=owner.pk,
            title="레거시 판매 완료",
            description="migration sold backfill",
            price=10_000,
            sale_state="SOLD",
            image=source_name,
        )
        available = Product.objects.create(
            owner_id=owner.pk,
            title="레거시 판매 중",
            description="migration available backfill",
            price=20_000,
            sale_state="AVAILABLE",
            image="",
        )
        source_checksum = hashlib.sha256(payload).hexdigest()

        executor = MigrationExecutor(connection)
        executor.migrate([CATALOG_AFTER, TRADES_AFTER])
        after_apps = executor.loader.project_state([CATALOG_AFTER, TRADES_AFTER]).apps
        ProductAfter = after_apps.get_model("catalog", "Product")
        ProductImage = after_apps.get_model("catalog", "ProductImage")
        Trade = after_apps.get_model("trades", "Trade")

        copied = ProductImage.objects.get(product_id=sold.pk)
        destination_name = copied.image.name
        storage = ProductImage._meta.get_field("image").storage
        with storage.open(source_name, "rb") as source_file:
            source_after = source_file.read()
        with storage.open(destination_name, "rb") as destination_file:
            destination_bytes = destination_file.read()

        assert ProductImage.objects.count() == 1
        assert source_name != destination_name
        assert destination_name == (
            f"product-images/migrated/{sold.pk}/{source_checksum}.png"
        )
        assert source_after == destination_bytes == payload
        assert copied.sha256 == source_checksum
        assert hashlib.sha256(destination_bytes).hexdigest() == source_checksum
        assert storage.exists(source_name)
        assert storage.exists(destination_name)
        assert ProductAfter.objects.filter(
            pk__in=(sold.pk, available.pk),
            category_id="OTHER",
            region_id=None,
            region_source="LEGACY_UNSET",
        ).count() == 2

        legacy_trade = Trade.objects.get(product_id=sold.pk)
        assert legacy_trade.kind == "LEGACY_SOLD"
        assert legacy_trade.status == "COMPLETED"
        assert legacy_trade.buyer_id is None
        assert legacy_trade.completed_at is not None
        assert not Trade.objects.filter(product_id=available.pk).exists()
        new_gallery_image = ProductImage(
            product_id=sold.pk,
            position=1,
            sha256=source_checksum,
            byte_size=len(payload),
            width=8,
            height=8,
        )
        new_gallery_name = ""
        try:
            new_gallery_image.image.save("new.png", ContentFile(payload), save=False)
            new_gallery_name = new_gallery_image.image.name
            new_gallery_image.save()

            migration = importlib.import_module(
                "apps.catalog.migrations.0003_catalog_authority_expand"
            )
            with pytest.raises(RuntimeError, match="new gallery image write"):
                migration.reverse_seed_and_copy(
                    after_apps, SimpleNamespace(connection=connection)
                )

            assert ProductImage.objects.filter(pk=copied.pk).exists()
            assert ProductImage.objects.filter(pk=new_gallery_image.pk).exists()
            assert storage.exists(source_name)
            assert storage.exists(destination_name)
            assert storage.exists(new_gallery_name)
        finally:
            if new_gallery_image.pk:
                new_gallery_image.delete()
            if new_gallery_name:
                storage.delete(new_gallery_name)

        executor = MigrationExecutor(connection)
        executor.migrate([CATALOG_BEFORE, ("trades", None)])
        reversed_apps = executor.loader.project_state([CATALOG_BEFORE]).apps
        ProductReversed = reversed_apps.get_model("catalog", "Product")
        ProductReversed.objects.filter(pk=sold.pk).update(sale_state="AVAILABLE")

        assert ProductReversed.objects.get(pk=sold.pk).image.name == source_name
        assert storage.exists(source_name)
        assert storage.exists(destination_name)
    finally:
        MigrationExecutor(connection).migrate(original_leaves)

@pytest.mark.parametrize(
    ("boundary_mutation", "error"),
    [
        ("sale_state", "legacy SOLD product ID mismatch"),
        ("image", "legacy product image copy mismatch"),
    ],
)
def test_freeze_cutover_revalidates_boundary_mutations_atomically(
    settings, tmp_path, boundary_mutation, error
) -> None:
    settings.MEDIA_ROOT = tmp_path
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([CATALOG_BEFORE, ("trades", None)])
        before_apps = executor.loader.project_state([CATALOG_BEFORE]).apps
        User = before_apps.get_model("accounts", "User")
        Product = before_apps.get_model("catalog", "Product")
        owner = User.objects.create(
            username=f"freeze_{boundary_mutation}", password="unusable"
        )
        payload = _png_bytes()
        storage = Product._meta.get_field("image").storage
        source_name = storage.save("product-images/freeze-boundary.png", ContentFile(payload))
        sold = Product.objects.create(
            owner_id=owner.pk,
            title="freeze boundary",
            description="freeze boundary validation",
            price=10_000,
            sale_state="SOLD",
            image=source_name,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([("catalog", "0003_catalog_authority_expand"), TRADES_AFTER])
        boundary_apps = executor.loader.project_state(
            [("catalog", "0003_catalog_authority_expand"), TRADES_AFTER]
        ).apps
        ProductAfter = boundary_apps.get_model("catalog", "Product")

        if boundary_mutation == "sale_state":
            ProductAfter.objects.filter(pk=sold.pk).update(sale_state="AVAILABLE")
        else:
            storage.delete(source_name)
            assert storage.save(source_name, ContentFile(_png_bytes("red"))) == source_name

        executor = MigrationExecutor(connection)
        with pytest.raises(RuntimeError, match=error):
            executor.migrate([CATALOG_FREEZE, TRADES_AFTER])

        # A failed validation rolls back the just-installed guards.
        if boundary_mutation == "sale_state":
            ProductAfter.objects.filter(pk=sold.pk).update(sale_state="SOLD")
        else:
            ProductAfter.objects.filter(pk=sold.pk).update(image="")
            ProductAfter.objects.filter(pk=sold.pk).update(image=source_name)
            storage.delete(source_name)
            assert storage.save(source_name, ContentFile(payload)) == source_name

        executor = MigrationExecutor(connection)
        executor.migrate([CATALOG_FREEZE, TRADES_AFTER])
    finally:
        MigrationExecutor(connection).migrate(original_leaves)


def test_migrations_bind_historical_orm_and_storage_work_to_schema_alias() -> None:
    migration_0003 = importlib.import_module(
        "apps.catalog.migrations.0003_catalog_authority_expand"
    )
    migration_0001 = importlib.import_module(
        "apps.trades.migrations.0001_typed_trade_authority"
    )
    migration_0004 = importlib.import_module(
        "apps.catalog.migrations.0004_freeze_legacy_product_authority"
    )
    catalog_source = inspect.getsource(migration_0003)
    trades_source = inspect.getsource(migration_0001)
    assert catalog_source.count(".objects") == catalog_source.count(".objects.using(alias)")
    assert trades_source.count(".objects") == trades_source.count(".objects.using(alias)")
    assert "executescript" not in inspect.getsource(migration_0004)
    assert "storage.delete(" not in inspect.getsource(
        migration_0003.reverse_seed_and_copy
    )


def test_legacy_image_reads_reject_overflow_before_decode() -> None:
    migration = importlib.import_module(
        "apps.catalog.migrations.0003_catalog_authority_expand"
    )
    requested_sizes = []

    class OverflowFile(BytesIO):
        def read(self, size=-1):
            requested_sizes.append(size)
            return super().read(size)

    class OverflowStorage:
        def open(self, name, mode):
            return OverflowFile(b"x" * (migration.MAX_IMAGE_BYTES + 1))

    with pytest.raises(RuntimeError, match="byte limit"):
        migration._read_bounded(OverflowStorage(), "overflow")
    assert requested_sizes == [migration.MAX_IMAGE_BYTES + 1]


def test_trade_backfill_retries_only_exact_legacy_sold_set() -> None:
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([CATALOG_AFTER, TRADES_AFTER])
        apps = executor.loader.project_state([CATALOG_AFTER, TRADES_AFTER]).apps
        User = apps.get_model("accounts", "User")
        Product = apps.get_model("catalog", "Product")
        Trade = apps.get_model("trades", "Trade")
        alias = connection.alias
        Category = apps.get_model("catalog", "Category")
        Category.objects.using(alias).get_or_create(
            code="OTHER",
            defaults={"label": "기타", "display_order": 6},
        )
        owner = User.objects.create(username="trade_migration_owner", password="x")
        sold = Product.objects.create(
            owner_id=owner.pk,
            title="sold",
            description="sold product",
            price=1,
            sale_state="SOLD",
            image="",
            category_id="OTHER",
            region_source="LEGACY_UNSET",
        )
        available = Product.objects.create(
            owner_id=owner.pk,
            title="available",
            description="available product",
            price=1,
            sale_state="AVAILABLE",
            image="",
            category_id="OTHER",
            region_source="LEGACY_UNSET",
        )
        migration = importlib.import_module(
            "apps.trades.migrations.0001_typed_trade_authority"
        )
        def execute(sql):
            with connection.cursor() as cursor:
                cursor.execute(sql)

        schema_editor = SimpleNamespace(connection=connection, execute=execute)

        # Run the direct migration helper under the same atomic contract as
        # Django's RunPython operation.
        with transaction.atomic():
            migration.backfill_legacy_sold(apps, schema_editor)
            migration.backfill_legacy_sold(apps, schema_editor)
            assert Trade.objects.filter(
                product_id=sold.pk, kind="LEGACY_SOLD", status="COMPLETED"
            ).count() == 1

            Trade.objects.create(
                product_id=available.pk,
                seller_id=owner.pk,
                kind="LEGACY_SOLD",
                status="COMPLETED",
                completed_at=available.updated_at,
            )
            with pytest.raises(RuntimeError, match="do not match"):
                migration.backfill_legacy_sold(apps, schema_editor)
            Trade.objects.filter(product_id=available.pk).delete()
    finally:
        MigrationExecutor(connection).migrate(original_leaves)
