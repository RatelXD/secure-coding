from django.apps import AppConfig
from django.conf import settings
from django.db import connections, router, transaction
from django.db.models.signals import post_migrate


def reseed_categories(sender, *, using: str, **kwargs) -> None:
    """Restore canonical category rows only for explicitly enabled test databases."""
    if not getattr(settings, "CATALOG_RESEED_CATEGORIES_FOR_TESTS", False):
        return

    from .models import CATEGORY_CHOICES, Category

    if not router.allow_migrate_model(using, Category):
        return
    if Category._meta.db_table not in connections[using].introspection.table_names():
        return

    with transaction.atomic(using=using):
        for display_order, (code, label) in enumerate(CATEGORY_CHOICES):
            Category.objects.using(using).update_or_create(
                code=code,
                defaults={"label": label, "display_order": display_order},
            )


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"

    def ready(self) -> None:
        post_migrate.connect(
            reseed_categories,
            sender=self,
            dispatch_uid="catalog.reseed_canonical_categories",
        )