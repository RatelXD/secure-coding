from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ReviewForm
from .services import (
    ReviewAuthorityError,
    TradeConflict,
    TradeError,
    TradeService,
    create_review,
)


def _error(code: str, status: int) -> JsonResponse:
    return JsonResponse({"error_code": code}, status=status)


def _version(request: HttpRequest) -> int | None:
    if request.content_type != "application/json":
        raise ValueError
    data = json.loads(request.body or b"{}")
    if not isinstance(data, dict) or set(data) - {"version"}:
        raise ValueError
    value = data.get("version")
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError
    return value


def _response(result, *, status: int = 200) -> JsonResponse:
    trade = result.trade
    return JsonResponse(
        {
            "trade_id": trade.pk,
            "product_id": trade.product_id,
            "status": trade.status.lower(),
            "version": trade.version,
        },
        status=status,
    )


@require_POST
def reserve(request: HttpRequest, product_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error("AUTH_REQUIRED", 401)
    if request.body:
        return _error("INVALID_REQUEST", 400)
    try:
        result = TradeService.reserve(actor=request.user, product_id=product_id)
    except TradeConflict:
        return _error("TRADE_CONFLICT", 409)
    except TradeError:
        return _error("TRADE_NOT_ALLOWED", 422)
    return _response(result, status=201 if result.created else 200)


@require_POST
def cancel(request: HttpRequest, trade_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error("AUTH_REQUIRED", 401)
    try:
        version = _version(request)
        return _response(TradeService.cancel(actor=request.user, trade_id=trade_id, expected_version=version))
    except (ValueError, json.JSONDecodeError):
        return _error("INVALID_REQUEST", 400)
    except TradeConflict:
        return _error("TRADE_CONFLICT", 409)
    except TradeError:
        return _error("TRADE_NOT_ALLOWED", 422)


@require_POST
def complete(request: HttpRequest, trade_id: int) -> JsonResponse:
    if not request.user.is_authenticated:
        return _error("AUTH_REQUIRED", 401)
    try:
        version = _version(request)
        return _response(TradeService.complete(actor=request.user, trade_id=trade_id, expected_version=version))
    except (ValueError, json.JSONDecodeError):
        return _error("INVALID_REQUEST", 400)
    except TradeConflict:
        return _error("TRADE_CONFLICT", 409)
    except TradeError:
        return _error("TRADE_NOT_ALLOWED", 422)


@login_required
@require_http_methods(["GET", "POST"])
def review_create(request: HttpRequest, trade_id: int) -> HttpResponse:
    form = ReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_review(
                actor=request.user,
                trade_id=trade_id,
                rating=form.cleaned_data["rating"],
                body=form.cleaned_data["body"],
            )
        except ReviewAuthorityError:
            form.add_error(None, "후기를 작성할 수 없습니다.")
        else:
            return redirect("/")
    return render(
        request,
        "trades/review_form.html",
        {"form": form},
        status=400 if request.method == "POST" else 200,
    )
