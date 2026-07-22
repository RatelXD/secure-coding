from __future__ import annotations


from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase


REPOSITORY_ROOT = settings.BASE_DIR
AUTHORITY_APPS = {
    "accounts",
    "catalog",
    "chat",
    "moderation",
    "notifications",
    "trades",
    "transfers",
}


class CycleOneScopeTests(SimpleTestCase):
    def test_integrated_authority_modules_are_present(self) -> None:
        app_root = REPOSITORY_ROOT / "src" / "apps"
        present_modules = {path.name for path in app_root.iterdir() if path.is_dir()}

        self.assertTrue(AUTHORITY_APPS <= present_modules)
        installed = set(settings.INSTALLED_APPS)
        self.assertTrue({f"apps.{app}" for app in AUTHORITY_APPS} <= installed)

    def test_each_authority_app_has_one_leaf_migration(self) -> None:
        loader = MigrationLoader(None, ignore_no_migrations=True)
        leaves_by_app = {
            app: loader.graph.leaf_nodes(app)
            for app in AUTHORITY_APPS
        }

        self.assertEqual(set(leaves_by_app), AUTHORITY_APPS)
        for app, leaves in leaves_by_app.items():
            with self.subTest(app=app):
                self.assertEqual(len(leaves), 1, f"{app} has conflicting migration leaves: {leaves}")
