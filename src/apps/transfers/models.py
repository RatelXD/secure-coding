from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class MockAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mock_account")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default="100000.00")
    is_open = models.BooleanField(default=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(balance__gte=0, balance__lte=1_000_000_000), name="transfers_balance_range"),
        ]


class LedgerAccount(models.Model):
    class Kind(models.TextChoices):
        USER = "USER", "User"
        SYSTEM_ISSUANCE = "SYSTEM_ISSUANCE", "System issuance"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    mock_account = models.OneToOneField(MockAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_account")
    code = models.CharField(max_length=64, unique=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(kind="USER", mock_account__isnull=False) | models.Q(kind="SYSTEM_ISSUANCE", mock_account__isnull=True)),
                name="transfers_ledger_account_kind",
            )
        ]


class LedgerJournal(models.Model):
    class Kind(models.TextChoices):
        SEED_ISSUE = "SEED_ISSUE", "Seed issue"
        TRANSFER = "TRANSFER", "Transfer"
        COMPENSATION = "COMPENSATION", "Compensation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    target_mock_account = models.ForeignKey(MockAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="seed_journals")
    original_journal = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="compensations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("target_mock_account",), condition=models.Q(kind="SEED_ISSUE", target_mock_account__isnull=False), name="transfers_one_seed_per_account"),
        ]


class LedgerEntry(models.Model):
    journal = models.ForeignKey(LedgerJournal, on_delete=models.PROTECT, related_name="entries")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="entries")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class Transfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(MockAccount, on_delete=models.PROTECT, related_name="sent_transfers")
    recipient = models.ForeignKey(MockAccount, on_delete=models.PROTECT, related_name="received_transfers")
    journal = models.OneToOneField(LedgerJournal, on_delete=models.PROTECT, related_name="transfer")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class TransferRequest(models.Model):
    sender = models.ForeignKey(MockAccount, on_delete=models.PROTECT, related_name="transfer_requests")
    idempotency_key = models.UUIDField()
    canonical_payload = models.TextField()
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    transfer = models.OneToOneField(Transfer, null=True, blank=True, on_delete=models.PROTECT, related_name="request_result")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("sender", "idempotency_key"), name="transfers_sender_idempotency_unique"),
        ]


class TransferSafetyState(models.Model):
    class State(models.TextChoices):
        OPEN = "OPEN", "Open"
        BLOCKED = "BLOCKED", "Blocked"

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    state = models.CharField(max_length=8, choices=State.choices, default=State.OPEN)
    incident_id = models.UUIDField(null=True, blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(singleton=1), name="transfers_safety_singleton"),
            models.CheckConstraint(
                condition=(models.Q(state="OPEN", incident_id__isnull=True, blocked_at__isnull=True) | models.Q(state="BLOCKED", incident_id__isnull=False, blocked_at__isnull=False)),
                name="transfers_safety_state_consistent",
            ),
        ]


class TransferAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event_type = models.CharField(max_length=32)
    transfer = models.ForeignKey(Transfer, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
