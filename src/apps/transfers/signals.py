from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import ensure_account


@receiver(post_save, sender=get_user_model(), dispatch_uid="transfers.bootstrap_mock_account")
def bootstrap_mock_account(sender, instance, created: bool, raw: bool, **kwargs) -> None:
    if created and not raw:
        ensure_account(instance)
