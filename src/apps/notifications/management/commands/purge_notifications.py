from django.core.management.base import BaseCommand

from apps.notifications.services import purge_expired_notifications


class Command(BaseCommand):
    help = "Delete notifications whose database-authoritative expiry is in the past."

    def handle(self, *args, **options):
        result = purge_expired_notifications()
        if not result.lock_acquired:
            self.stdout.write("Notification purge is already running.")
            return
        self.stdout.write(self.style.SUCCESS(f"Deleted {result.deleted_count} notifications."))
