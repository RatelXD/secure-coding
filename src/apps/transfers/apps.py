from django.apps import AppConfig


class TransfersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.transfers"

    def ready(self) -> None:
        from . import signals  # noqa: F401
