from uuid import UUID, uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.transfers.models import TransferSafetyState
from apps.transfers.services import SAFETY_LOCK_KEY, _advisory_lock, ledger_mismatches


class Command(BaseCommand):
    help = "Reconcile the mock ledger and fail closed on any mismatch."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--resume", metavar="INCIDENT_UUID")

    @transaction.atomic
    def handle(self, *args, **options):
        _advisory_lock(SAFETY_LOCK_KEY)
        state, _ = TransferSafetyState.objects.select_for_update().get_or_create(singleton=1)
        mismatches = ledger_mismatches()
        raw_incident = options.get("resume")
        if raw_incident:
            try:
                incident = UUID(raw_incident)
            except ValueError as exc:
                raise CommandError("invalid incident UUID") from exc
            expected_role = getattr(settings, "LEDGER_MAINTAINER_DB_ROLE", "ledger_maintainer")
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_user")
                    current_role = cursor.fetchone()[0]
                if current_role != expected_role:
                    raise CommandError("ledger maintainer database role required")
            if state.state != state.State.BLOCKED or state.incident_id != incident:
                raise CommandError("incident does not match the active block")
            if mismatches:
                raise CommandError("ledger mismatches remain")
            state.state = state.State.OPEN
            state.incident_id = None
            state.blocked_at = None
            state.save(update_fields=("state", "incident_id", "blocked_at"))
            self.stdout.write("OPEN")
            return
        if mismatches:
            if state.state == state.State.OPEN:
                state.state = state.State.BLOCKED
                state.incident_id = uuid4()
                state.blocked_at = timezone.now()
                state.save(update_fields=("state", "incident_id", "blocked_at"))
            raise CommandError(f"ledger blocked incident={state.incident_id} mismatches={len(mismatches)}")
        self.stdout.write(f"{state.state}: mismatches=0")
