from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services import purge_expired_notifications

_INTERVAL_SECONDS = 24 * 60 * 60
_MAX_RETRIES = 3
_RETRY_SECONDS = 60


class Command(BaseCommand):
    help = "Run the singleton daily notification expiry scheduler."

    def handle(self, *args, **options):
        if settings.APP_ENV == "test":
            raise CommandError("Notification scheduler must not start in tests.")
        while True:
            for attempt in range(_MAX_RETRIES):
                try:
                    result = purge_expired_notifications()
                except Exception:
                    if attempt + 1 == _MAX_RETRIES:
                        raise
                    time.sleep(_RETRY_SECONDS)
                else:
                    if result.lock_acquired:
                        self.stdout.write(
                            f"Notification purge deleted {result.deleted_count} rows."
                        )
                    break
            time.sleep(_INTERVAL_SECONDS)
