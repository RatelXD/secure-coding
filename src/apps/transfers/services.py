from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import OperationalError, connection, transaction
from django.db.models import Count, Sum
from django.db.models.functions import Now
from django.utils import timezone

from apps.chat.models import ProductConversation, Room
from apps.moderation.models import ModerationAction
from apps.notifications.services import TransferNotification, create_transfer_notifications

from .models import (
    LedgerAccount,
    LedgerEntry,
    LedgerJournal,
    MockAccount,
    Transfer,
    TransferAudit,
    TransferRequest,
    TransferSafetyState,
)

SEED_AMOUNT = Decimal("100000.00")
MAX_BALANCE = Decimal("1000000000.00")
SAFETY_LOCK_KEY = 0x5452414E53464552


class TransferUnavailable(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


@dataclass(frozen=True)
class TransferResult:
    status: int
    body: dict[str, str]
    replayed: bool = False


def _advisory_lock(key: int, *, shared: bool = False) -> None:
    if connection.vendor != "postgresql":
        return
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {function}(%s)", [key])


def _idempotency_lock(sender_id: int, key: UUID) -> None:
    digest = hashlib.blake2b(f"{sender_id}:{key}".encode(), digest_size=8).digest()
    _advisory_lock(int.from_bytes(digest, "big", signed=True))


def canonical_payload(recipient: str, amount: Decimal) -> str:
    return json.dumps(
        {"amount": f"{amount:.2f}", "recipient": recipient, "version": 1},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_room_payload(room_id: int, amount: Decimal) -> str:
    return json.dumps(
        {"amount": f"{amount:.2f}", "room_id": room_id, "version": 2}, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True,
    )


def _is_active_user(user_id: int) -> bool:
    User = get_user_model()
    if not User.objects.filter(pk=user_id, is_active=True, withdrawn_at__isnull=True).exists():
        return False
    return not ModerationAction.objects.filter(
        kind=ModerationAction.Kind.USER_DORMANCY,
        target_user_id=user_id,
        starts_at__lte=Now(),
        expires_at__gt=Now(),
    ).exists()


@transaction.atomic
def ensure_account(user) -> MockAccount:
    account = MockAccount.objects.select_for_update().filter(user=user).first()
    if account:
        return account
    reserve, _ = LedgerAccount.objects.get_or_create(
        code="SEED_RESERVE",
        defaults={"kind": LedgerAccount.Kind.SYSTEM_ISSUANCE},
    )
    account = MockAccount.objects.create(user=user, balance=SEED_AMOUNT)
    ledger = LedgerAccount.objects.create(
        kind=LedgerAccount.Kind.USER,
        mock_account=account,
        code=f"USER:{user.pk}",
    )
    journal = LedgerJournal.objects.create(
        kind=LedgerJournal.Kind.SEED_ISSUE,
        target_mock_account=account,
    )
    LedgerEntry.objects.bulk_create(
        (
            LedgerEntry(journal=journal, account=ledger, amount=SEED_AMOUNT),
            LedgerEntry(journal=journal, account=reserve, amount=-SEED_AMOUNT),
        )
    )
    TransferSafetyState.objects.get_or_create(singleton=1)
    return account


def _store_denial(*, sender: MockAccount, key: UUID, payload: str) -> TransferResult:
    body = {"error_code": "TRANSFER_NOT_ALLOWED"}
    TransferRequest.objects.create(
        sender=sender,
        idempotency_key=key,
        canonical_payload=payload,
        response_status=422,
        response_body=body,
    )
    return TransferResult(422, body)


@transaction.atomic
def _execute_once(*, sender_user, recipient_name: str, amount: Decimal, key: UUID, request_payload: str | None = None) -> TransferResult:
    sender = MockAccount.objects.get(user=sender_user)
    _advisory_lock(SAFETY_LOCK_KEY, shared=True)
    _idempotency_lock(sender.pk, key)
    previous = TransferRequest.objects.select_for_update().filter(sender=sender, idempotency_key=key).first()
    payload = request_payload or canonical_payload(recipient_name, amount)
    if previous:
        if previous.canonical_payload != payload:
            raise IdempotencyConflict
        return TransferResult(previous.response_status, previous.response_body, replayed=True)

    safety = TransferSafetyState.objects.get(singleton=1)
    if safety.state != TransferSafetyState.State.OPEN:
        raise TransferUnavailable

    User = get_user_model()
    recipient_user = User.objects.filter(username=recipient_name).first()
    if recipient_user is None or recipient_user.pk == sender_user.pk:
        return _store_denial(sender=sender, key=key, payload=payload)
    recipient = MockAccount.objects.filter(user=recipient_user).first()
    if recipient is None:
        return _store_denial(sender=sender, key=key, payload=payload)
    accounts = {
        account.pk: account
        for account in MockAccount.objects.select_for_update().filter(pk__in=sorted((sender.pk, recipient.pk)))
    }
    sender = accounts[sender.pk]
    recipient = accounts[recipient.pk]
    if (
        not sender.is_open
        or not recipient.is_open
        or not _is_active_user(sender.user_id)
        or not _is_active_user(recipient.user_id)
        or sender.balance < amount
        or recipient.balance + amount > MAX_BALANCE
    ):
        return _store_denial(sender=sender, key=key, payload=payload)

    sender.balance -= amount
    recipient.balance += amount
    sender.save(update_fields=("balance",))
    recipient.save(update_fields=("balance",))
    journal = LedgerJournal.objects.create(kind=LedgerJournal.Kind.TRANSFER)
    LedgerEntry.objects.bulk_create(
        (
            LedgerEntry(journal=journal, account=sender.ledger_account, amount=-amount),
            LedgerEntry(journal=journal, account=recipient.ledger_account, amount=amount),
        )
    )
    transfer = Transfer.objects.create(sender=sender, recipient=recipient, journal=journal, amount=amount)
    body = {
        "transfer_id": str(transfer.pk),
        "status": "completed",
        "recipient": recipient_name,
        "amount": f"{amount:.0f}",
        "sender_balance": f"{sender.balance:.0f}",
    }
    TransferRequest.objects.create(
        sender=sender,
        idempotency_key=key,
        canonical_payload=payload,
        response_status=201,
        response_body=body,
        transfer=transfer,
    )
    TransferAudit.objects.create(actor=sender_user, event_type="TRANSFER_COMPLETED", transfer=transfer)
    return TransferResult(201, body)


def transfer(*, sender_user, recipient_name: str, amount: Decimal, key: UUID, request_payload: str | None = None) -> TransferResult:
    for attempt in range(4):
        try:
            return _execute_once(
                sender_user=sender_user,
                recipient_name=recipient_name,
                amount=amount,
                key=key,
                request_payload=request_payload,
            )
        except OperationalError as exc:
            sqlstate = getattr(exc.__cause__, "sqlstate", None)
            if sqlstate not in {"40001", "40P01"} or attempt == 3:
                if sqlstate in {"40001", "40P01"}:
                    raise TransferUnavailable from exc
                raise
    raise TransferUnavailable


@transaction.atomic
def transfer_for_product_room(*, sender_user, room_id: int, amount: Decimal, key: UUID) -> TransferResult:
    sender = MockAccount.objects.get(user=sender_user)
    _idempotency_lock(sender.pk, key)
    payload = canonical_room_payload(room_id, amount)
    previous = TransferRequest.objects.select_for_update().filter(sender=sender, idempotency_key=key).first()
    if previous:
        if previous.canonical_payload != payload:
            raise IdempotencyConflict
        return TransferResult(previous.response_status, previous.response_body, replayed=True)
    try:
        conversation = ProductConversation.objects.select_for_update().select_related("room", "seller", "buyer").get(room_id=room_id)
    except ProductConversation.DoesNotExist:
        return _store_denial(sender=sender, key=key, payload=payload)
    if conversation.room.kind != Room.Kind.PRODUCT:
        return _store_denial(sender=sender, key=key, payload=payload)
    if sender_user.pk == conversation.seller_id:
        recipient = conversation.buyer
    elif sender_user.pk == conversation.buyer_id:
        recipient = conversation.seller
    else:
        return _store_denial(sender=sender, key=key, payload=payload)
    result = transfer(sender_user=sender_user, recipient_name=recipient.username, amount=amount, key=key, request_payload=payload)
    if result.status == 201 and not result.replayed:
        create_transfer_notifications(
            transfer_notification=TransferNotification(
                sender_id=sender_user.pk,
                recipient_id=recipient.pk,
                transfer_id=UUID(result.body["transfer_id"]),
                amount=amount,
            )
        )
    return result


@transaction.atomic
def close_account(*, user) -> bool:
    _advisory_lock(SAFETY_LOCK_KEY, shared=True)
    safety, _ = TransferSafetyState.objects.select_for_update().get_or_create(singleton=1)
    if safety.state != TransferSafetyState.State.OPEN:
        raise TransferUnavailable
    account = ensure_account(user)
    account = MockAccount.objects.select_for_update().get(pk=account.pk)
    if not account.is_open:
        return False
    if account.balance != Decimal("0.00"):
        raise ValueError("ACCOUNT_NOT_EMPTY")
    account.is_open = False
    account.closed_at = timezone.now()
    account.save(update_fields=("is_open", "closed_at"))
    TransferAudit.objects.create(actor=user, event_type="ACCOUNT_CLOSED")
    return True


def ledger_mismatches() -> list[str]:
    mismatches: list[str] = []
    for journal in LedgerJournal.objects.annotate(total=Sum("entries__amount"), count=Count("entries")):
        if journal.count != 2 or journal.total != Decimal("0.00"):
            mismatches.append(str(journal.pk))
    for account in MockAccount.objects.select_related("ledger_account"):
        total = account.ledger_account.entries.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        if total != account.balance:
            mismatches.append(f"account:{account.pk}")
    return mismatches
