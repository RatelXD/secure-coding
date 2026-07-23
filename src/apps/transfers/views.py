from __future__ import annotations

import json
import re
from decimal import Decimal
from uuid import UUID

from django.http import HttpRequest, JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.csrf import csrf_failure as default_csrf_failure

from .services import (
    IdempotencyConflict,
    TransferUnavailable,
    close_account,
    transfer,
    transfer_for_product_room,
)

_AMOUNT = re.compile(r"^[1-9][0-9]{0,7}$")


def _error(code: str, status: int) -> JsonResponse:
    return JsonResponse({"error_code": code}, status=status)


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    if request.path.startswith(("/transfers/", "/trades/")):
        return _error("CSRF_FAILED", 403)
    return default_csrf_failure(request, reason=reason)


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


@require_POST
def create_transfer(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error("AUTH_REQUIRED", 401)
    if request.content_type != "application/json":
        return _error("INVALID_REQUEST", 400)
    try:
        data = json.loads(request.body, object_pairs_hook=_pairs_no_duplicates)
        if not isinstance(data, dict) or set(data) != {"recipient", "amount", "idempotency_key"}:
            raise ValueError
        recipient = data["recipient"]
        raw_amount = data["amount"]
        raw_key = data["idempotency_key"]
        if not isinstance(recipient, str) or not 1 <= len(recipient) <= 150:
            raise ValueError
        if not isinstance(raw_amount, str) or not _AMOUNT.fullmatch(raw_amount):
            raise ValueError
        amount = Decimal(raw_amount)
        if not Decimal("1") <= amount <= Decimal("99999999"):
            raise ValueError
        if not isinstance(raw_key, str):
            raise ValueError
        key = UUID(raw_key)
        if str(key) != raw_key:
            raise ValueError
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, ArithmeticError):
        return _error("INVALID_REQUEST", 400)
    try:
        result = transfer(sender_user=request.user, recipient_name=recipient, amount=amount, key=key)
    except IdempotencyConflict:
        return _error("IDEMPOTENCY_CONFLICT", 409)
    except TransferUnavailable:
        return _error("TRANSFER_UNAVAILABLE", 503)
    return JsonResponse(result.body, status=result.status)


@require_POST
def create_room_transfer(request: HttpRequest, room_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error("AUTH_REQUIRED", 401)
    if request.content_type != "application/json":
        return _error("INVALID_REQUEST", 400)
    try:
        data = json.loads(request.body, object_pairs_hook=_pairs_no_duplicates)
        if not isinstance(data, dict) or set(data) != {"amount", "idempotency_key"}:
            raise ValueError
        raw_amount = data["amount"]
        raw_key = data["idempotency_key"]
        if not isinstance(raw_amount, str) or not _AMOUNT.fullmatch(raw_amount):
            raise ValueError
        amount = Decimal(raw_amount)
        if not Decimal("1") <= amount <= Decimal("99999999"):
            raise ValueError
        if not isinstance(raw_key, str):
            raise ValueError
        key = UUID(raw_key)
        if str(key) != raw_key:
            raise ValueError
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, ArithmeticError):
        return _error("INVALID_REQUEST", 400)
    try:
        result = transfer_for_product_room(
            sender_user=request.user,
            room_id=room_id,
            amount=amount,
            key=key,
        )
    except IdempotencyConflict:
        return _error("IDEMPOTENCY_CONFLICT", 409)
    except TransferUnavailable:
        return _error("TRANSFER_UNAVAILABLE", 503)
    return JsonResponse(result.body, status=result.status)


@require_POST
def close_mock_account(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return _error("AUTH_REQUIRED", 401)
    if request.body:
        return _error("INVALID_REQUEST", 400)
    try:
        close_account(user=request.user)
    except ValueError:
        return _error("ACCOUNT_NOT_EMPTY", 409)
    except TransferUnavailable:
        return _error("TRANSFER_UNAVAILABLE", 503)
    return HttpResponse(status=204)
