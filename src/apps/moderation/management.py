from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import Product
from apps.trades.models import Review, ReviewVisibilityAction

from .models import AdminAudit, AdminScopeGrant, AbuseReport, ModerationAction, SanctionRelease
from .services import _database_now

_REAUTH_WINDOW = timedelta(seconds=300)


class ManagementError(RuntimeError):
    status_code = 400


class ManagementDenied(ManagementError):
    status_code = 403


class ManagementNotFound(ManagementError):
    status_code = 404


class ManagementConflict(ManagementError):
    status_code = 409


class ManagementUnavailable(ManagementError):
    status_code = 503


@dataclass(frozen=True)
class ManagementResult:
    value: object
    created: bool


def normalize_management_reason(reason: str) -> str:
    if not isinstance(reason, str):
        raise ManagementError("invalid management request")
    normalized = unicodedata.normalize("NFC", reason.strip())
    if not 10 <= len(normalized) <= 500:
        raise ManagementError("invalid management request")
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in normalized):
        raise ManagementError("invalid management request")
    return normalized


def _require_reauthentication(*, reauthenticated_at: datetime, database_now: datetime) -> None:
    if not isinstance(reauthenticated_at, datetime):
        raise ManagementError("recent reauthentication required")
    if timezone.is_naive(reauthenticated_at):
        raise ManagementError("recent reauthentication required")
    age = database_now - reauthenticated_at
    if age < timedelta(0) or age > _REAUTH_WINDOW:
        raise ManagementError("recent reauthentication required")


def _audit(**fields) -> AdminAudit:
    try:
        return AdminAudit.objects.create(**fields)
    except Exception as exc:
        raise ManagementUnavailable("management audit unavailable") from exc


def _target_filter(target_type: str, target_id: int) -> dict[str, int]:
    if target_type == "USER":
        return {"target_user_id": target_id}
    if target_type == "PRODUCT":
        return {"target_product_id": target_id}
    if target_type == "REVIEW":
        return {"target_review_id": target_id}
    raise ManagementError("invalid management request")


def _require_scope(*, actor, codename: str, target_type: str, target_id: int) -> AdminScopeGrant:
    if not actor.is_active or not actor.is_staff or not actor.has_perm(f"moderation.{codename}"):
        raise ManagementDenied("management permission denied")
    try:
        return AdminScopeGrant.objects.get(
            staff=actor,
            codename=codename,
            revoked_at__isnull=True,
            **_target_filter(target_type, target_id),
        )
    except AdminScopeGrant.DoesNotExist as exc:
        raise ManagementNotFound("management target not found") from exc


def _has_direct_meta_permission(actor) -> bool:
    return bool(
        actor.is_active
        and actor.is_staff
        and actor.is_superuser
        and actor.user_permissions.filter(
            content_type__app_label="moderation",
            codename="manage_admin_scope",
        ).exists()
    )


def _audit_conflict(*, actor, action: str, target_type: str, target_id: int, reason: str, before: dict) -> None:
    _audit(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        before=before,
        after=before,
        result="CONFLICT",
    )


def apply_sanction(
    *, actor, target_type: str, target_id: int, reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    if target_type not in {"USER", "PRODUCT"} or not isinstance(version, int) or isinstance(version, bool):
        raise ManagementError("invalid management request")
    with transaction.atomic():
        now = _database_now()
        _require_reauthentication(reauthenticated_at=reauthenticated_at, database_now=now)
        if target_type == "USER":
            try:
                target = get_user_model().objects.select_for_update().get(pk=target_id)
            except get_user_model().DoesNotExist as exc:
                raise ManagementNotFound("management target not found") from exc
            current_version = target.auth_epoch
            kind = ModerationAction.Kind.USER_DORMANCY
        else:
            try:
                target = Product.objects.select_for_update().get(pk=target_id)
            except Product.DoesNotExist as exc:
                raise ManagementNotFound("management target not found") from exc
            current_version = target.version
            kind = ModerationAction.Kind.PRODUCT_HIDE
        _require_scope(actor=actor, codename="apply_sanction", target_type=target_type, target_id=target_id)
        before = {"active": False, "version": current_version}
        if version != current_version:
            _audit_conflict(
                actor=actor,
                action="apply",
                target_type=target_type,
                target_id=target_id,
                reason=normalized_reason,
                before=before,
            )
            raise ManagementConflict("stale management request")
        active = ModerationAction.objects.filter(
            kind=kind,
            starts_at__lte=now,
            expires_at__gt=now,
            release__isnull=True,
            **_target_filter(target_type, target_id),
        ).first()
        if active is not None:
            return ManagementResult(active, False)
        action = ModerationAction.objects.create(
            kind=kind,
            starts_at=now,
            expires_at=now + timedelta(days=7),
            **_target_filter(target_type, target_id),
        )
        _audit(
            actor=actor,
            action="apply",
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
            before=before,
            after={"active": True, "sanction_id": action.pk},
            result="SUCCESS",
        )
        return ManagementResult(action, True)


def release_sanction(
    *, actor, sanction_id: int, reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    with transaction.atomic():
        now = _database_now()
        _require_reauthentication(reauthenticated_at=reauthenticated_at, database_now=now)
        try:
            action = ModerationAction.objects.select_for_update().get(pk=sanction_id)
        except ModerationAction.DoesNotExist as exc:
            raise ManagementNotFound("management target not found") from exc
        target_type = "USER" if action.target_user_id else "PRODUCT"
        target_id = action.target_user_id or action.target_product_id
        _require_scope(actor=actor, codename="release_sanction", target_type=target_type, target_id=target_id)
        before = {"active": action.starts_at <= now < action.expires_at, "sanction_id": action.pk}
        if version != action.pk:
            _audit_conflict(
                actor=actor,
                action="release",
                target_type=target_type,
                target_id=target_id,
                reason=normalized_reason,
                before=before,
            )
            raise ManagementConflict("stale management request")
        existing = SanctionRelease.objects.filter(action=action).first()
        if existing is not None:
            return ManagementResult(existing, False)
        if now >= action.expires_at:
            _audit_conflict(
                actor=actor,
                action="release",
                target_type=target_type,
                target_id=target_id,
                reason=normalized_reason,
                before=before,
            )
            raise ManagementConflict("sanction has expired")
        release = SanctionRelease.objects.create(action=action, actor=actor, reason=normalized_reason)
        _audit(
            actor=actor,
            action="release",
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
            before=before,
            after={"active": False, "sanction_id": action.pk},
            result="SUCCESS",
        )
        return ManagementResult(release, True)


def grant_scope(
    *, actor, staff_id: int, codename: str, target_type: str, target_id: int,
    reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    if codename not in AdminScopeGrant.Codename.values or target_type not in {"USER", "PRODUCT", "REVIEW"}:
        raise ManagementError("invalid management request")
    with transaction.atomic():
        now = _database_now()
        _require_reauthentication(reauthenticated_at=reauthenticated_at, database_now=now)
        if not _has_direct_meta_permission(actor):
            raise ManagementDenied("management permission denied")
        try:
            staff = get_user_model().objects.select_for_update().get(pk=staff_id, is_active=True, is_staff=True)
        except get_user_model().DoesNotExist as exc:
            raise ManagementNotFound("management target not found") from exc
        if actor.pk == staff.pk:
            raise ManagementDenied("self scope changes are forbidden")
        if staff.auth_epoch != version:
            _audit_conflict(
                actor=actor, action="grant", target_type=target_type, target_id=target_id,
                reason=normalized_reason, before={"staff_id": staff.pk, "version": staff.auth_epoch},
            )
            raise ManagementConflict("stale management request")
        # Resolve the target before insert so nonexistent and out-of-scope targets are indistinguishable.
        model = {"USER": get_user_model(), "PRODUCT": Product, "REVIEW": Review}[target_type]
        if not model.objects.filter(pk=target_id).exists():
            raise ManagementNotFound("management target not found")
        try:
            grant = AdminScopeGrant.objects.create(
                staff=staff,
                codename=codename,
                granted_by=actor,
                **_target_filter(target_type, target_id),
            )
        except IntegrityError as exc:
            raise ManagementConflict("scope already exists") from exc
        _audit(
            actor=actor, action="grant", target_type=target_type, target_id=target_id,
            reason=normalized_reason, before={"staff_id": staff.pk, "active": False},
            after={"staff_id": staff.pk, "active": True, "grant_id": grant.pk}, result="SUCCESS",
        )
        return ManagementResult(grant, True)


def revoke_scope(
    *, actor, grant_id: int, reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    with transaction.atomic():
        now = _database_now()
        _require_reauthentication(reauthenticated_at=reauthenticated_at, database_now=now)
        if not _has_direct_meta_permission(actor):
            raise ManagementDenied("management permission denied")
        try:
            grant = AdminScopeGrant.objects.select_for_update().select_related("staff").get(pk=grant_id)
        except AdminScopeGrant.DoesNotExist as exc:
            raise ManagementNotFound("management target not found") from exc
        if actor.pk == grant.staff_id:
            raise ManagementDenied("self scope changes are forbidden")
        target_type = "USER" if grant.target_user_id else "PRODUCT" if grant.target_product_id else "REVIEW"
        target_id = grant.target_user_id or grant.target_product_id or grant.target_review_id
        if grant.version != version:
            _audit_conflict(
                actor=actor, action="revoke", target_type=target_type, target_id=target_id,
                reason=normalized_reason, before={"grant_id": grant.pk, "version": grant.version},
            )
            raise ManagementConflict("stale management request")
        if grant.revoked_at is not None:
            return ManagementResult(grant, False)
        grant.revoked_at = now
        grant.revoked_by = actor
        grant.version = F("version") + 1
        grant.save(update_fields=("revoked_at", "revoked_by", "version"))
        get_user_model().objects.filter(pk=grant.staff_id).update(auth_epoch=F("auth_epoch") + 1)
        grant.refresh_from_db()
        _audit(
            actor=actor, action="revoke", target_type=target_type, target_id=target_id,
            reason=normalized_reason, before={"grant_id": grant.pk, "active": True},
            after={"grant_id": grant.pk, "active": False}, result="SUCCESS",
        )
        return ManagementResult(grant, True)


def set_review_visibility(
    *, actor, review_id: int, kind: str, reason: str, idempotency_key: UUID,
    reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    if kind not in ReviewVisibilityAction.Kind.values or not isinstance(idempotency_key, UUID):
        raise ManagementError("invalid management request")
    codename = "hide_review" if kind == ReviewVisibilityAction.Kind.HIDE else "restore_review"
    with transaction.atomic():
        now = _database_now()
        _require_reauthentication(reauthenticated_at=reauthenticated_at, database_now=now)
        try:
            review = Review.objects.select_for_update().get(pk=review_id)
        except Review.DoesNotExist as exc:
            raise ManagementNotFound("management target not found") from exc
        _require_scope(actor=actor, codename=codename, target_type="REVIEW", target_id=review.pk)
        if not AbuseReport.objects.filter(target_review=review).exists():
            raise ManagementNotFound("management target not found")
        replay = ReviewVisibilityAction.objects.filter(idempotency_key=idempotency_key).first()
        if replay is not None:
            if replay.review_id != review.pk or replay.kind != kind:
                raise ManagementConflict("management replay does not match")
            return ManagementResult(replay, False)
        latest = review.visibility_actions.order_by("-created_at", "-pk").first()
        if latest is not None and latest.kind == kind:
            return ManagementResult(latest, False)
        action = ReviewVisibilityAction.objects.create(
            review=review,
            actor=actor,
            kind=kind,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
        )
        _audit(
            actor=actor, action=kind.lower(), target_type="REVIEW", target_id=review.pk,
            reason=normalized_reason,
            before={"visibility": latest.kind if latest else "VISIBLE"},
            after={"visibility": kind, "action_id": action.pk}, result="SUCCESS",
        )
        return ManagementResult(action, True)


_apply_sanction_authority = apply_sanction
_release_sanction_authority = release_sanction
_grant_scope_authority = grant_scope
_revoke_scope_authority = revoke_scope


def _audit_denial(*, actor, action: str, target_type: str, target_id: int, reason: str) -> None:
    _audit(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        before={},
        after={},
        result="DENIED",
    )


def apply_sanction(
    *, actor, target_type: str, target_id: int, reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    try:
        return _apply_sanction_authority(
            actor=actor,
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
            version=version,
            reauthenticated_at=reauthenticated_at,
        )
    except ManagementConflict:
        _audit_conflict(
            actor=actor,
            action="apply",
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
            before={"version": version},
        )
        raise
    except (ManagementDenied, ManagementNotFound):
        _audit_denial(
            actor=actor,
            action="apply",
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
        )
        raise


def release_sanction(
    *, actor, sanction_id: int, reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    try:
        return _release_sanction_authority(
            actor=actor,
            sanction_id=sanction_id,
            reason=normalized_reason,
            version=version,
            reauthenticated_at=reauthenticated_at,
        )
    except (ManagementConflict, ManagementDenied, ManagementNotFound) as exc:
        action = ModerationAction.objects.filter(pk=sanction_id).first()
        target_type = "USER" if action and action.target_user_id else "PRODUCT" if action else "SANCTION"
        target_id = (
            action.target_user_id or action.target_product_id
            if action is not None
            else sanction_id
        )
        if isinstance(exc, ManagementConflict):
            _audit_conflict(
                actor=actor,
                action="release",
                target_type=target_type,
                target_id=target_id,
                reason=normalized_reason,
                before={"sanction_id": sanction_id, "version": version},
            )
        else:
            _audit_denial(
                actor=actor,
                action="release",
                target_type=target_type,
                target_id=target_id,
                reason=normalized_reason,
            )
        raise


def grant_scope(
    *, actor, staff_id: int, codename: str, target_type: str, target_id: int,
    reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    try:
        return _grant_scope_authority(
            actor=actor,
            staff_id=staff_id,
            codename=codename,
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
            version=version,
            reauthenticated_at=reauthenticated_at,
        )
    except ManagementConflict:
        _audit_conflict(
            actor=actor,
            action="grant",
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
            before={"staff_id": staff_id, "version": version},
        )
        raise
    except (ManagementDenied, ManagementNotFound):
        _audit_denial(
            actor=actor,
            action="grant",
            target_type=target_type,
            target_id=target_id,
            reason=normalized_reason,
        )
        raise


def revoke_scope(
    *, actor, grant_id: int, reason: str, version: int, reauthenticated_at: datetime
) -> ManagementResult:
    normalized_reason = normalize_management_reason(reason)
    try:
        return _revoke_scope_authority(
            actor=actor,
            grant_id=grant_id,
            reason=normalized_reason,
            version=version,
            reauthenticated_at=reauthenticated_at,
        )
    except (ManagementConflict, ManagementDenied, ManagementNotFound) as exc:
        grant = AdminScopeGrant.objects.filter(pk=grant_id).first()
        if grant is None:
            target_type, target_id = "SCOPE", grant_id
        elif grant.target_user_id:
            target_type, target_id = "USER", grant.target_user_id
        elif grant.target_product_id:
            target_type, target_id = "PRODUCT", grant.target_product_id
        else:
            target_type, target_id = "REVIEW", grant.target_review_id
        if isinstance(exc, ManagementConflict):
            _audit_conflict(
                actor=actor,
                action="revoke",
                target_type=target_type,
                target_id=target_id,
                reason=normalized_reason,
                before={"grant_id": grant_id, "version": version},
            )
        else:
            _audit_denial(
                actor=actor,
                action="revoke",
                target_type=target_type,
                target_id=target_id,
                reason=normalized_reason,
            )
        raise
