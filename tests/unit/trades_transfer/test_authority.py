from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.test import Client
from django.utils import timezone

from apps.catalog.models import Product
from apps.chat.models import ProductConversation, Room
from apps.notifications.models import Notification
from apps.trades.models import Trade, TradeStatusHistory
from apps.trades.services import TradeConflict, TradeError, TradeService
from apps.transfers.models import (
    LedgerEntry,
    LedgerJournal,
    MockAccount,
    Transfer,
    TransferRequest,
    TransferSafetyState,
)
from apps.transfers.services import (
    IdempotencyConflict,
    TransferUnavailable,
    canonical_payload,
    transfer,
    transfer_for_product_room,
)

pytestmark = pytest.mark.django_db(transaction=True)


def user(name):
    return get_user_model().objects.create_user(username=name, password="safe-test-password")


def authenticated_client(user):
    client = Client()
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()
    return client


def product_room(seller, buyer):
    product = Product.objects.create(owner=seller, title="item", description="desc", price=10)
    room = Room.objects.create(kind=Room.Kind.PRODUCT)
    ProductConversation.objects.create(room=room, product=product, seller=seller, buyer=buyer)
    return room


def test_trade_service_is_server_authoritative_and_preserves_history():
    seller = user("seller01")
    buyer = user("buyer001")
    outsider = user("outside1")
    product = Product.objects.create(owner=seller, title="item", description="desc", price=10)

    reserved = TradeService.reserve(actor=buyer, product_id=product.pk).trade
    assert (reserved.seller_id, reserved.buyer_id, reserved.status, reserved.version) == (
        seller.pk,
        buyer.pk,
        Trade.Status.RESERVED,
        1,
    )
    with pytest.raises(TradeConflict):
        TradeService.reserve(actor=outsider, product_id=product.pk)
    with pytest.raises(TradeError):
        TradeService.complete(actor=buyer, trade_id=reserved.pk)

    completed = TradeService.complete(actor=seller, trade_id=reserved.pk, expected_version=1).trade
    assert completed.status == Trade.Status.COMPLETED
    assert completed.version == 2
    assert list(TradeStatusHistory.objects.filter(trade=completed).values_list("to_status", flat=True)) == [
        Trade.Status.RESERVED,
        Trade.Status.COMPLETED,
    ]
    product.refresh_from_db()
    assert product.sale_state == Product.SaleState.AVAILABLE


def test_transfer_balances_ledger_and_replays_without_mutation():
    sender = user("sender01")
    recipient = user("recipient1")
    key = uuid4()
    first = transfer(sender_user=sender, recipient_name=recipient.username, amount=Decimal("10.00"), key=key)
    before = (Transfer.objects.count(), LedgerJournal.objects.count(), LedgerEntry.objects.count())
    replay = transfer(sender_user=sender, recipient_name=recipient.username, amount=Decimal("10.0"), key=key)

    assert first.status == replay.status == 201
    assert first.body == replay.body
    assert replay.replayed
    assert before == (Transfer.objects.count(), LedgerJournal.objects.count(), LedgerEntry.objects.count())
    assert sum(LedgerEntry.objects.filter(journal__transfer__isnull=False).values_list("amount", flat=True)) == 0
    assert MockAccount.objects.get(user=sender).balance == Decimal("99990.00")
    assert MockAccount.objects.get(user=recipient).balance == Decimal("100010.00")


def test_denial_is_stored_and_payload_change_conflicts():
    sender = user("sender02")
    key = uuid4()
    denied = transfer(sender_user=sender, recipient_name="missing1", amount=Decimal("1.00"), key=key)
    assert denied.status == 422
    assert Transfer.objects.count() == 0
    assert TransferRequest.objects.get().response_body == {"error_code": "TRANSFER_NOT_ALLOWED"}
    assert transfer(sender_user=sender, recipient_name="missing1", amount=Decimal("1"), key=key).replayed
    with pytest.raises(IdempotencyConflict):
        transfer(sender_user=sender, recipient_name="missing2", amount=Decimal("1"), key=key)


def test_blocked_state_replays_stored_results_but_rejects_new_keys():
    sender = user("sender04")
    recipient = user("receive04")
    key = uuid4()
    stored = transfer(
        sender_user=sender,
        recipient_name=recipient.username,
        amount=Decimal("1.00"),
        key=key,
    )
    safety = TransferSafetyState.objects.get(singleton=1)
    safety.state = safety.State.BLOCKED
    safety.incident_id = uuid4()
    safety.blocked_at = timezone.now()
    safety.save(update_fields=("state", "incident_id", "blocked_at"))

    assert transfer(
        sender_user=sender,
        recipient_name=recipient.username,
        amount=Decimal("1"),
        key=key,
    ).body == stored.body
    with pytest.raises(TransferUnavailable):
        transfer(
            sender_user=sender,
            recipient_name=recipient.username,
            amount=Decimal("1"),
            key=uuid4(),
        )


def test_canonical_payload_keeps_recipient_exact_and_normalizes_amount():
    assert canonical_payload(" Recipient ", Decimal("1.0")) == (
        '{"amount":"1.00","recipient":" Recipient ","version":1}'
    )


def test_http_boundary_rejects_unauthenticated_csrf_and_forged_fields():
    sender = user("sender03")
    recipient = user("receive03")
    payload = {
        "recipient": recipient.username,
        "amount": "1.00",
        "idempotency_key": str(uuid4()),
    }
    anonymous = Client()
    assert anonymous.post("/transfers/", payload, content_type="application/json").status_code == 401

    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(sender)
    assert csrf_client.post("/transfers/", payload, content_type="application/json").status_code == 403

    forged = Client()
    forged.force_login(sender)
    session = forged.session
    session["account_auth_epoch"] = sender.auth_epoch
    session.save()
    forged_payload = {**payload, "sender": recipient.username}
    response = forged.post("/transfers/", forged_payload, content_type="application/json")
    assert response.status_code == 400
    assert Transfer.objects.count() == 0


def test_room_transfer_derives_product_counterparty_and_creates_two_notices():
    seller = user("room_seller")
    buyer = user("room_buyer")
    room = product_room(seller, buyer)
    response = authenticated_client(seller).post(
        f"/transfers/rooms/{room.pk}/",
        {"amount": "25.00", "idempotency_key": str(uuid4())},
        content_type="application/json",
    )

    assert response.status_code == 201
    transfer_record = Transfer.objects.get()
    assert (transfer_record.sender.user_id, transfer_record.recipient.user_id) == (seller.pk, buyer.pk)
    assert set(
        Notification.objects.values_list("recipient_id", "event_key", "kind")
    ) == {
        (seller.pk, f"transfer.sender:{transfer_record.pk}", "TRANSFER_SENT"),
        (buyer.pk, f"transfer.recipient:{transfer_record.pk}", "TRANSFER_RECEIVED"),
    }


def test_room_transfer_replay_reuses_original_response_without_duplicate_side_effects():
    seller = user("replay_seller")
    buyer = user("replay_buyer")
    room = product_room(seller, buyer)
    key = uuid4()
    client = authenticated_client(seller)
    payload = {"amount": "25.00", "idempotency_key": str(key)}
    first = client.post(f"/transfers/rooms/{room.pk}/", payload, content_type="application/json")
    before = (Transfer.objects.count(), LedgerEntry.objects.count(), Notification.objects.count())
    replay = client.post(
        f"/transfers/rooms/{room.pk}/",
        {"amount": "25.0", "idempotency_key": str(key)},
        content_type="application/json",
    )

    assert replay.status_code == first.status_code == 201
    assert replay.json() == first.json()
    assert before == (Transfer.objects.count(), LedgerEntry.objects.count(), Notification.objects.count())


def test_room_transfer_rejects_client_supplied_recipient_without_mutation():
    seller = user("forged_seller")
    buyer = user("forged_buyer")
    outsider = user("forged_outside")
    room = product_room(seller, buyer)
    response = authenticated_client(seller).post(
        f"/transfers/rooms/{room.pk}/",
        {"amount": "25.00", "idempotency_key": str(uuid4()), "recipient": outsider.username},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not Transfer.objects.exists()
    assert not Notification.objects.exists()


def test_room_transfer_rejects_nonproduct_room_without_mutation():
    seller = user("scope_seller")
    buyer = user("scope_buyer")
    outsider = user("scope_outside")
    direct_room = Room.objects.create(kind=Room.Kind.DIRECT, direct_user_low=seller, direct_user_high=outsider)
    client = authenticated_client(seller)
    response = client.post(
        f"/transfers/rooms/{direct_room.pk}/",
        {"amount": "25.00", "idempotency_key": str(uuid4())},
        content_type="application/json",
    )

    assert response.status_code == 422
    assert not Transfer.objects.exists()
    assert not Notification.objects.exists()


def test_room_transfer_rejects_changed_idempotency_payload_without_mutation():
    seller = user("conflict_seller")
    buyer = user("conflict_buyer")
    room = product_room(seller, buyer)
    key = uuid4()
    client = authenticated_client(seller)
    first = client.post(
        f"/transfers/rooms/{room.pk}/",
        {"amount": "25.00", "idempotency_key": str(key)},
        content_type="application/json",
    )
    changed = client.post(
        f"/transfers/rooms/{room.pk}/",
        {"amount": "26.00", "idempotency_key": str(key)},
        content_type="application/json",
    )

    assert first.status_code == 201
    assert changed.status_code == 409
    assert Transfer.objects.count() == 1
    assert Notification.objects.count() == 2


def test_room_transfer_auth_csrf_and_invalid_amount_do_not_mutate():
    seller = user("boundary_seller")
    buyer = user("boundary_buyer")
    room = product_room(seller, buyer)
    payload = {"amount": "zero", "idempotency_key": str(uuid4())}

    assert Client().post(f"/transfers/rooms/{room.pk}/", payload, content_type="application/json").status_code == 401
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(seller)
    assert csrf_client.post(f"/transfers/rooms/{room.pk}/", payload, content_type="application/json").status_code == 403
    response = authenticated_client(seller).post(
        f"/transfers/rooms/{room.pk}/",
        payload,
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not Transfer.objects.exists()
    assert not Notification.objects.exists()


def test_room_transfer_notification_exception_rolls_back_ledger_and_transfer(monkeypatch):
    seller = user("notice_seller")
    buyer = user("notice_buyer")
    room = product_room(seller, buyer)

    def fail_notification(*, transfer_notification):
        raise RuntimeError("notification failure")

    monkeypatch.setattr("apps.transfers.services.create_transfer_notifications", fail_notification)

    with pytest.raises(RuntimeError, match="notification failure"):
        transfer_for_product_room(
            sender_user=seller,
            room_id=room.pk,
            amount=Decimal("25.00"),
            key=uuid4(),
        )

    assert not Transfer.objects.exists()
    assert not LedgerEntry.objects.filter(journal__kind=LedgerJournal.Kind.TRANSFER).exists()
    assert not Notification.objects.exists()


def test_database_rejects_unbalanced_and_mutated_ledger():
    account = user("ledger01").mock_account
    reserve = account.ledger_account
    with pytest.raises(DatabaseError), transaction.atomic():
        journal = LedgerJournal.objects.create(kind=LedgerJournal.Kind.TRANSFER)
        LedgerEntry.objects.create(journal=journal, account=reserve, amount=Decimal("1.00"))
    entry = LedgerEntry.objects.filter(journal__kind=LedgerJournal.Kind.SEED_ISSUE).first()
    with pytest.raises(DatabaseError), transaction.atomic():
        LedgerEntry.objects.filter(pk=entry.pk).update(amount=Decimal("0.00"))
