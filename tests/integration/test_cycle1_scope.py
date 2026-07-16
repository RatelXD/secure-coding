from __future__ import annotations


from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase


REPOSITORY_ROOT = settings.BASE_DIR
CYCLE_ONE_APPS = {"accounts", "catalog", "chat", "moderation"}
DEFERRED_MODULES = {"transfers", "search", "administration"}


class CycleOneScopeTests(SimpleTestCase):
    def test_cycle_two_modules_are_absent(self) -> None:
        app_root = REPOSITORY_ROOT / "src" / "apps"
        present_modules = {path.name for path in app_root.iterdir() if path.is_dir()}

        self.assertTrue(CYCLE_ONE_APPS <= present_modules)
        self.assertFalse(DEFERRED_MODULES & present_modules)
        self.assertFalse(
            any(
                deferred in app.lower()
                for app in settings.INSTALLED_APPS
                for deferred in DEFERRED_MODULES
            )
        )

    def test_each_cycle_one_app_has_one_leaf_migration(self) -> None:
        loader = MigrationLoader(None, ignore_no_migrations=True)
        leaves_by_app = {
            app: loader.graph.leaf_nodes(app)
            for app in CYCLE_ONE_APPS
        }

        self.assertEqual(set(leaves_by_app), CYCLE_ONE_APPS)
        for app, leaves in leaves_by_app.items():
            with self.subTest(app=app):
                self.assertEqual(len(leaves), 1, f"{app} has conflicting migration leaves: {leaves}")
