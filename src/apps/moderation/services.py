from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, TypeVar

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import Exists, F, OuterRef, QuerySet
from django.db.models.functions import Now
from django.utils import timezone

from apps.catalog.models import Product

from .models import AbuseReport, AuditEvent, ModerationAction
from .policies import (
    ACTION_DURATION,
    ModerationPolicyError,
    ReportContext,
    TargetType,
    is_reporter_eligible,
    qualifies_for_action,
    validate_report_context,
)


class EffectiveUserStatus(StrEnum):
    ACTIVE = "active"
    DORMANT = "dormant"


class EffectiveProductVisibility(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"


class ReportSubmissionError(ValueError):
    """A report was rejected without exposing target or account state."""


class DuplicateReportError(ReportSubmissionError):
    pass


@dataclass(frozen=True)
class ReportSubmission:
    report: AbuseReport
    action: ModerationAction | None


class ModerationActionAuthority(Protocol):
    """Create exactly one seven-day action and audit event at the transactional threshold."""

    def evaluate_threshold(
        self,
        *,
        target_type: TargetType,
        target_id: int,
    ) -> ModerationAction | None: ...


_QuerySetT = TypeVar("_QuerySetT", bound=QuerySet)


def _active_actions() -> QuerySet[ModerationAction]:
    return ModerationAction.objects.filter(starts_at__lte=Now(), expires_at__gt=Now())


def effective_user_status(*, user_id: int) -> EffectiveUserStatus:
    """Return canonical user status using database time."""
    dormant = _active_actions().filter(
        kind=ModerationAction.Kind.USER_DORMANCY,
        target_user_id=user_id,
    ).exists()
    return EffectiveUserStatus.DORMANT if dormant else EffectiveUserStatus.ACTIVE


def effective_product_visibility(*, product_id: int) -> EffectiveProductVisibility:
    """Return canonical visibility; callers must not trust a stored flag."""
    visible = Product.objects.filter(
        pk=product_id,
        archived_at__isnull=True,
    ).exists()
    hidden = _active_actions().filter(
        kind=ModerationAction.Kind.PRODUCT_HIDE,
        target_product_id=product_id,
    ).exists()
    return (
        EffectiveProductVisibility.HIDDEN
        if hidden or not visible
        else EffectiveProductVisibility.VISIBLE
    )


def visible_products(queryset: _QuerySetT) -> _QuerySetT:
    """Filter a product queryset with the same DB-time policy used by detail views."""
    active_hide = ModerationAction.objects.filter(
        kind=ModerationAction.Kind.PRODUCT_HIDE,
        target_product_id=OuterRef("pk"),
        starts_at__lte=Now(),
        expires_at__gt=Now(),
    )
    return (
        queryset.filter(archived_at__isnull=True)
        .annotate(_moderation_hidden=Exists(active_hide))
        .filter(_moderation_hidden=False)
    )


def _normalize_reason(reason: str) -> str:
    normalized = reason.strip()
    if not normalized or len(normalized) > 1_000 or "\x00" in normalized:
        raise ReportSubmissionError("report cannot be accepted")
    if any(ord(character) < 32 and character != "\n" for character in normalized):
        raise ReportSubmissionError("report cannot be accepted")
    return normalized


def _database_now() -> datetime:
    with connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        value = cursor.fetchone()[0]
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _lock_submission_parties(*, reporter_id: int, target_type: TargetType, target_id: int):
    user_model = get_user_model()
    if target_type is TargetType.USER:
        users = list(
            user_model.objects.select_for_update()
            .filter(pk__in={reporter_id, target_id})
            .order_by("pk")
        )
        by_id = {user.pk: user for user in users}
        if reporter_id not in by_id or target_id not in by_id:
            raise ReportSubmissionError("report cannot be accepted")
        return by_id[reporter_id], by_id[target_id], None, _database_now()

    try:
        product = Product.objects.select_for_update().get(
            pk=target_id,
            archived_at__isnull=True,
        )
        reporter = user_model.objects.select_for_update().get(pk=reporter_id)
    except (Product.DoesNotExist, user_model.DoesNotExist) as exc:
        raise ReportSubmissionError("report cannot be accepted") from exc
    return reporter, None, product, _database_now()


def _reporter_can_contribute(*, reporter, database_now: datetime) -> bool:
    return is_reporter_eligible(
        joined_at=reporter.date_joined,
        is_active=reporter.is_active,
        database_now=database_now,
    ) and effective_user_status(user_id=reporter.pk) is EffectiveUserStatus.ACTIVE


def _active_action_for_target(*, target_type: TargetType, target_id: int) -> ModerationAction | None:
    filters = {"target_user_id": target_id} if target_type is TargetType.USER else {"target_product_id": target_id}
    return _active_actions().filter(**filters).first()


def _qualifying_reports(
    *, target_type: TargetType, target_id: int, database_now: datetime
) -> tuple[list[AbuseReport], dict[ReportContext, set[int]]]:
    target_filter = {"target_user_id": target_id} if target_type is TargetType.USER else {"target_product_id": target_id}
    reports = list(
        AbuseReport.objects.select_related("reporter")
        .filter(
            target_type=target_type.value,
            consumed_by__isnull=True,
            created_at__gte=database_now - timedelta(days=7),
            created_at__lte=database_now,
            **target_filter,
        )
        .order_by("created_at", "pk")
    )
    eligible: list[AbuseReport] = []
    by_context: dict[ReportContext, set[int]] = defaultdict(set)
    for report in reports:
        if not _reporter_can_contribute(reporter=report.reporter, database_now=database_now):
            continue
        context = ReportContext(report.context)
        eligible.append(report)
        by_context[context].add(report.reporter_id)
    return eligible, dict(by_context)


def _evaluate_locked(
    *, target_type: TargetType, target_id: int, database_now: datetime, actor_id: int | None
) -> ModerationAction | None:
    if _active_action_for_target(target_type=target_type, target_id=target_id) is not None:
        return None

    reports, by_context = _qualifying_reports(
        target_type=target_type,
        target_id=target_id,
        database_now=database_now,
    )
    if not qualifies_for_action(
        target_type=target_type,
        independent_reporters_by_context=by_context,
    ):
        return None

    action_fields = {
        "kind": ModerationAction.Kind.USER_DORMANCY
        if target_type is TargetType.USER
        else ModerationAction.Kind.PRODUCT_HIDE,
        "starts_at": database_now,
        "expires_at": database_now + ACTION_DURATION,
    }
    if target_type is TargetType.USER:
        action_fields["target_user_id"] = target_id
    else:
        action_fields["target_product_id"] = target_id
    action = ModerationAction.objects.create(**action_fields)
    AbuseReport.objects.filter(pk__in=[report.pk for report in reports]).update(consumed_by=action)

    if target_type is TargetType.USER:
        get_user_model().objects.filter(pk=target_id).update(auth_epoch=F("auth_epoch") + 1)

    AuditEvent.objects.create(
        event_type="MODERATION_ACTION_APPLIED",
        actor_id=actor_id,
        action=action,
        details={
            "target_type": target_type.value,
            "target_id": target_id,
            "consumed_report_count": len(reports),
            "duration_days": ACTION_DURATION.days,
        },
    )
    return action


def submit_report(
    *, reporter, target_type: TargetType | str, target_id: int, context: ReportContext | str, reason: str
) -> ReportSubmission:
    """Store a valid report and atomically apply at most one reversible action."""
    try:
        normalized_target_type = TargetType(target_type)
        normalized_context = ReportContext(context)
        validate_report_context(target_type=normalized_target_type, context=normalized_context)
    except (ValueError, ModerationPolicyError) as exc:
        raise ReportSubmissionError("report cannot be accepted") from exc
    normalized_reason = _normalize_reason(reason)

    try:
        with transaction.atomic():
            locked_reporter, target_user, target_product, database_now = _lock_submission_parties(
                reporter_id=reporter.pk,
                target_type=normalized_target_type,
                target_id=target_id,
            )
            if not _reporter_can_contribute(reporter=locked_reporter, database_now=database_now):
                raise ReportSubmissionError("report cannot be accepted")
            if normalized_target_type is TargetType.USER:
                if target_user.pk == locked_reporter.pk or not target_user.is_active:
                    raise ReportSubmissionError("report cannot be accepted")
                if effective_user_status(user_id=target_user.pk) is not EffectiveUserStatus.ACTIVE:
                    raise ReportSubmissionError("report cannot be accepted")
            else:
                if target_product.owner_id == locked_reporter.pk:
                    raise ReportSubmissionError("report cannot be accepted")
                if effective_product_visibility(product_id=target_product.pk) is not EffectiveProductVisibility.VISIBLE:
                    raise ReportSubmissionError("report cannot be accepted")

            report = AbuseReport.objects.create(
                reporter=locked_reporter,
                target_type=normalized_target_type.value,
                target_user=target_user,
                target_product=target_product,
                context=normalized_context.value,
                reason=normalized_reason,
                created_at=database_now,
            )
            action = _evaluate_locked(
                target_type=normalized_target_type,
                target_id=target_id,
                database_now=database_now,
                actor_id=locked_reporter.pk,
            )
            return ReportSubmission(report=report, action=action)
    except IntegrityError as exc:
        raise DuplicateReportError("report cannot be accepted") from exc


def evaluate_threshold(*, target_type: TargetType | str, target_id: int) -> ModerationAction | None:
    """Re-evaluate unconsumed reports while holding the canonical target lock."""
    try:
        normalized_target_type = TargetType(target_type)
    except ValueError as exc:
        raise ReportSubmissionError("report cannot be accepted") from exc
    with transaction.atomic():
        user_model = get_user_model()
        if normalized_target_type is TargetType.USER:
            try:
                target = user_model.objects.select_for_update().get(pk=target_id)
            except user_model.DoesNotExist as exc:
                raise ReportSubmissionError("report cannot be accepted") from exc
        else:
            try:
                target = Product.objects.select_for_update().get(
                    pk=target_id,
                    archived_at__isnull=True,
                )
            except Product.DoesNotExist as exc:
                raise ReportSubmissionError("report cannot be accepted") from exc
        if normalized_target_type is TargetType.USER and (
            not target.is_active
            or effective_user_status(user_id=target.pk) is not EffectiveUserStatus.ACTIVE
        ):
            return None
        if (
            normalized_target_type is TargetType.PRODUCT
            and effective_product_visibility(product_id=target.pk)
            is not EffectiveProductVisibility.VISIBLE
        ):
            return None
        return _evaluate_locked(
            target_type=normalized_target_type,
            target_id=target_id,
            database_now=_database_now(),
            actor_id=None,
        )


class DatabaseModerationActionAuthority:
    def evaluate_threshold(
        self, *, target_type: TargetType, target_id: int
    ) -> ModerationAction | None:
        return evaluate_threshold(target_type=target_type, target_id=target_id)
