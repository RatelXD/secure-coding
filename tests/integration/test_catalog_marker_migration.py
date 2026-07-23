import pytest
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import ProgrammingError

pytestmark = pytest.mark.django_db(transaction=True)

CATALOG_BASELINE = ("catalog", "0007_catalog_engagement_search_demo")
CATALOG_MARKER_CLEANUP = ("catalog", "0008_remove_g4_backup_marker")


def test_catalog_baseline_migration_leaves_g4_marker_unchanged() -> None:
    """Characterize the pre-marker-cleanup catalog migration boundary."""
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()
    targets = [
        CATALOG_BASELINE if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]

    try:
        executor.migrate(targets)
        apps = executor.loader.project_state(targets).apps
        User = apps.get_model("accounts", "User")
        Product = apps.get_model("catalog", "Product")
        owner = User.objects.create(username="g4_backup_user", password="unusable")
        marker = Product.objects.create(
            owner_id=owner.pk,
            title="G4 backup marker",
            description="restore evidence",
            price=1000,
            category_id="OTHER",
            region_source="LEGACY_UNSET",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(targets)

        assert Product.objects.filter(pk=marker.pk).count() == 1
    finally:
        MigrationExecutor(connection).migrate(original_leaves)


def test_marker_cleanup_aborts_when_a_related_trade_protects_the_marker() -> None:
    """Given a protected relation, the migration rolls back without deleting the marker."""
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()
    before_targets = [
        CATALOG_BASELINE if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]
    after_targets = [
        CATALOG_MARKER_CLEANUP if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]

    try:
        executor.migrate(before_targets)
        before_apps = executor.loader.project_state(before_targets).apps
        User = before_apps.get_model("accounts", "User")
        Product = before_apps.get_model("catalog", "Product")
        Trade = before_apps.get_model("trades", "Trade")
        owner = User.objects.create(username="g4_backup_user", password="unusable")
        buyer = User.objects.create(username="g4_backup_buyer", password="unusable")
        marker = Product.objects.create(
            owner_id=owner.pk,
            title="G4 backup marker",
            description="restore evidence",
            price=1000,
            category_id="OTHER",
            region_source="LEGACY_UNSET",
        )
        protected_trade = Trade.objects.create(
            product_id=marker.pk,
            seller_id=owner.pk,
            buyer_id=buyer.pk,
            kind="STANDARD",
            status="RESERVED",
        )

        executor = MigrationExecutor(connection)
        with pytest.raises(ProtectedError):
            executor.migrate(after_targets)

        assert Product.objects.filter(pk=marker.pk).count() == 1
        assert Trade.objects.filter(pk=protected_trade.pk).count() == 1
        protected_trade.delete()
    finally:
        MigrationExecutor(connection).migrate(original_leaves)


def test_marker_cleanup_removes_only_the_exact_g4_marker() -> None:
    """Given near matches, the migration deletes only the fully matched marker."""
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()
    before_targets = [
        CATALOG_BASELINE if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]
    after_targets = [
        CATALOG_MARKER_CLEANUP if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]

    try:
        executor.migrate(before_targets)
        before_apps = executor.loader.project_state(before_targets).apps
        User = before_apps.get_model("accounts", "User")
        Product = before_apps.get_model("catalog", "Product")
        owner = User.objects.create(username="g4_backup_user", password="unusable")
        another_owner = User.objects.create(username="g4_backup_other", password="unusable")
        exact_marker = Product.objects.create(
            owner_id=owner.pk,
            title="G4 backup marker",
            description="restore evidence",
            price=1000,
            category_id="OTHER",
            region_source="LEGACY_UNSET",
        )
        near_markers = [
            Product.objects.create(
                owner_id=owner.pk,
                title="G4 backup marker ",
                description="restore evidence",
                price=1000,
                category_id="OTHER",
                region_source="LEGACY_UNSET",
            ).pk,
            Product.objects.create(
                owner_id=owner.pk,
                title="G4 backup marker",
                description="restore evidence ",
                price=1000,
                category_id="OTHER",
                region_source="LEGACY_UNSET",
            ).pk,
            Product.objects.create(
                owner_id=owner.pk,
                title="G4 backup marker",
                description="restore evidence",
                price=1001,
                category_id="OTHER",
                region_source="LEGACY_UNSET",
            ).pk,
            Product.objects.create(
                owner_id=another_owner.pk,
                title="G4 backup marker",
                description="restore evidence",
                price=1000,
                category_id="OTHER",
                region_source="LEGACY_UNSET",
            ).pk,
        ]

        executor = MigrationExecutor(connection)
        executor.migrate(after_targets)
        after_apps = executor.loader.project_state(after_targets).apps
        ProductAfter = after_apps.get_model("catalog", "Product")

        assert not ProductAfter.objects.filter(pk=exact_marker.pk).exists()
        assert ProductAfter.objects.filter(pk__in=near_markers).count() == 4
        with pytest.raises(ProgrammingError, match="archived"):
            ProductAfter.objects.filter(pk=near_markers[0]).delete()
    finally:
        MigrationExecutor(connection).migrate(original_leaves)


def test_marker_cleanup_aborts_before_deleting_duplicate_exact_markers() -> None:
    """Given duplicate exact markers, the migration leaves both rows untouched."""
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()
    before_targets = [
        CATALOG_BASELINE if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]
    after_targets = [
        CATALOG_MARKER_CLEANUP if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]

    try:
        executor.migrate(before_targets)
        before_apps = executor.loader.project_state(before_targets).apps
        User = before_apps.get_model("accounts", "User")
        Product = before_apps.get_model("catalog", "Product")
        owner = User.objects.create(username="g4_backup_user", password="unusable")
        duplicate_marker_ids = []
        for _ in range(2):
            duplicate_marker_ids.append(Product.objects.create(
                owner_id=owner.pk,
                title="G4 backup marker",
                description="restore evidence",
                price=1000,
                category_id="OTHER",
                region_source="LEGACY_UNSET",
            ).pk)

        executor = MigrationExecutor(connection)
        with pytest.raises(RuntimeError, match="duplicate exact G4 backup markers"):
            executor.migrate(after_targets)

        assert Product.objects.filter(
            owner_id=owner.pk,
            title="G4 backup marker",
            description="restore evidence",
            price=1000,
        ).count() == 2
        Product.objects.filter(pk=duplicate_marker_ids[0]).update(
            title="G4 backup marker retained"
        )
    finally:
        MigrationExecutor(connection).migrate(original_leaves)


def test_marker_cleanup_is_a_noop_when_no_exact_marker_exists() -> None:
    """Given only a nonmatching seller, the migration preserves that product."""
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()
    before_targets = [
        CATALOG_BASELINE if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]
    after_targets = [
        CATALOG_MARKER_CLEANUP if app_label == "catalog" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]

    try:
        executor.migrate(before_targets)
        before_apps = executor.loader.project_state(before_targets).apps
        User = before_apps.get_model("accounts", "User")
        Product = before_apps.get_model("catalog", "Product")
        nonmatching_owner = User.objects.create(
            username="g4_backup_other", password="unusable"
        )
        near_marker = Product.objects.create(
            owner_id=nonmatching_owner.pk,
            title="G4 backup marker",
            description="restore evidence",
            price=1000,
            category_id="OTHER",
            region_source="LEGACY_UNSET",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(after_targets)
        after_apps = executor.loader.project_state(after_targets).apps
        ProductAfter = after_apps.get_model("catalog", "Product")

        assert ProductAfter.objects.filter(pk=near_marker.pk).count() == 1
    finally:
        MigrationExecutor(connection).migrate(original_leaves)
