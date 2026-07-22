from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.trades.models import ReviewVisibilityAction

from .management import (
    ManagementDenied,
    ManagementError,
    ManagementNotFound,
    apply_sanction,
    grant_scope,
    release_sanction,
    revoke_scope,
    set_review_visibility,
)
from .models import AdminAudit, AdminScopeGrant, AbuseReport

_REAUTH_SESSION_KEY = "management_reauthenticated_at"


def _error_response(exc: ManagementError) -> HttpResponse:
    if isinstance(exc, ManagementDenied):
        return HttpResponseForbidden("관리 권한이 없습니다.")
    if isinstance(exc, ManagementNotFound):
        return HttpResponseNotFound("대상을 찾을 수 없습니다.")
    return HttpResponse("관리 요청을 처리할 수 없습니다.", status=exc.status_code)


def _reauthenticated_at(request: HttpRequest) -> datetime:
    raw = request.session.get(_REAUTH_SESSION_KEY)
    if not isinstance(raw, str):
        raise ManagementError("recent reauthentication required")
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ManagementError("recent reauthentication required") from exc


def _strict_post(request: HttpRequest, fields: set[str]) -> bool:
    return set(request.POST) == fields and all(len(request.POST.getlist(field)) == 1 for field in fields)


def _positive_int(raw: str) -> int:
    if not raw.isascii() or not raw.isdecimal() or raw.startswith("0"):
        raise ManagementError("invalid management request")
    value = int(raw)
    if value <= 0:
        raise ManagementError("invalid management request")
    return value


def _version(raw: str) -> int:
    if not raw.isascii() or not raw.isdecimal() or (raw != "0" and raw.startswith("0")):
        raise ManagementError("invalid management request")
    return int(raw)


def _staff_with_permission(request: HttpRequest, codename: str) -> bool:
    actor = request.user
    return actor.is_active and actor.is_staff and actor.has_perm(f"moderation.{codename}")


@login_required
@require_GET
def reports(request: HttpRequest) -> HttpResponse:
    if request.GET:
        return HttpResponse("잘못된 요청입니다.", status=400)
    if not _staff_with_permission(request, "view_report"):
        return HttpResponseForbidden("관리 권한이 없습니다.")
    grants = AdminScopeGrant.objects.filter(
        staff=request.user,
        codename=AdminScopeGrant.Codename.VIEW_REPORT,
        revoked_at__isnull=True,
    )
    scope = Q(pk__in=[])
    for grant in grants:
        if grant.target_user_id:
            scope |= Q(target_user_id=grant.target_user_id)
        elif grant.target_product_id:
            scope |= Q(target_product_id=grant.target_product_id)
        else:
            scope |= Q(target_review_id=grant.target_review_id)
    rows = AbuseReport.objects.filter(scope).select_related("reporter").order_by("-created_at", "-pk")[:100]
    return render(request, "moderation/management_reports.html", {"reports": rows})


@login_required
@require_GET
def audit(request: HttpRequest) -> HttpResponse:
    if request.GET:
        return HttpResponse("잘못된 요청입니다.", status=400)
    if not _staff_with_permission(request, "view_admin_audit"):
        return HttpResponseForbidden("관리 권한이 없습니다.")
    grants = AdminScopeGrant.objects.filter(
        staff=request.user,
        codename=AdminScopeGrant.Codename.VIEW_ADMIN_AUDIT,
        revoked_at__isnull=True,
    )
    scope = Q(pk__in=[])
    for grant in grants:
        target_type = "USER" if grant.target_user_id else "PRODUCT" if grant.target_product_id else "REVIEW"
        target_id = grant.target_user_id or grant.target_product_id or grant.target_review_id
        scope |= Q(target_type=target_type, target_id=target_id)
    rows = AdminAudit.objects.filter(scope).order_by("-created_at", "-pk")[:100]
    return render(request, "moderation/management_audit.html", {"audits": rows})


@login_required
@require_POST
def sanctions_apply(request: HttpRequest) -> HttpResponse:
    fields = {"target_type", "target_id", "reason", "version"}
    if not _strict_post(request, fields):
        return HttpResponse("잘못된 요청입니다.", status=400)
    try:
        result = apply_sanction(
            actor=request.user,
            target_type=request.POST["target_type"].upper(),
            target_id=_positive_int(request.POST["target_id"]),
            reason=request.POST["reason"],
            version=_version(request.POST["version"]),
            reauthenticated_at=_reauthenticated_at(request),
        )
    except ManagementError as exc:
        return _error_response(exc)
    return HttpResponse(f"sanction:{result.value.pk}")


@login_required
@require_POST
def sanctions_release(request: HttpRequest, sanction_id: int) -> HttpResponse:
    if not _strict_post(request, {"reason", "version"}):
        return HttpResponse("잘못된 요청입니다.", status=400)
    try:
        result = release_sanction(
            actor=request.user,
            sanction_id=sanction_id,
            reason=request.POST["reason"],
            version=_version(request.POST["version"]),
            reauthenticated_at=_reauthenticated_at(request),
        )
    except ManagementError as exc:
        return _error_response(exc)
    return HttpResponse(f"release:{result.value.pk}")


@login_required
@require_POST
def scopes_grant(request: HttpRequest) -> HttpResponse:
    fields = {"staff_id", "codename", "target_type", "target_id", "reason", "version"}
    if not _strict_post(request, fields):
        return HttpResponse("잘못된 요청입니다.", status=400)
    try:
        result = grant_scope(
            actor=request.user,
            staff_id=_positive_int(request.POST["staff_id"]),
            codename=request.POST["codename"],
            target_type=request.POST["target_type"].upper(),
            target_id=_positive_int(request.POST["target_id"]),
            reason=request.POST["reason"],
            version=_version(request.POST["version"]),
            reauthenticated_at=_reauthenticated_at(request),
        )
    except ManagementError as exc:
        return _error_response(exc)
    return HttpResponse(f"grant:{result.value.pk}")


@login_required
@require_POST
def scopes_revoke(request: HttpRequest, grant_id: int) -> HttpResponse:
    if not _strict_post(request, {"reason", "version"}):
        return HttpResponse("잘못된 요청입니다.", status=400)
    try:
        result = revoke_scope(
            actor=request.user,
            grant_id=grant_id,
            reason=request.POST["reason"],
            version=_version(request.POST["version"]),
            reauthenticated_at=_reauthenticated_at(request),
        )
    except ManagementError as exc:
        return _error_response(exc)
    return HttpResponse(f"revoke:{result.value.pk}")


@login_required
@require_POST
def review_visibility(request: HttpRequest, review_id: int) -> HttpResponse:
    if not _strict_post(request, {"action", "reason", "idempotency_key"}):
        return HttpResponse("잘못된 요청입니다.", status=400)
    kind = {
        "hide": ReviewVisibilityAction.Kind.HIDE,
        "restore": ReviewVisibilityAction.Kind.RESTORE,
    }.get(request.POST["action"])
    try:
        if kind is None:
            raise ManagementError("invalid management request")
        result = set_review_visibility(
            actor=request.user,
            review_id=review_id,
            kind=kind,
            reason=request.POST["reason"],
            idempotency_key=UUID(request.POST["idempotency_key"]),
            reauthenticated_at=_reauthenticated_at(request),
        )
    except (ManagementError, ValueError) as exc:
        return _error_response(exc if isinstance(exc, ManagementError) else ManagementError(str(exc)))
    return HttpResponse(f"review-action:{result.value.pk}")
