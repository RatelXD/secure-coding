from __future__ import annotations

from collections.abc import Mapping, Set
from datetime import datetime, timedelta
from enum import StrEnum

REPORT_WINDOW = timedelta(days=7)
ACTION_DURATION = timedelta(days=7)
INDEPENDENT_REPORTER_THRESHOLD = 5
USER_CONTEXT_THRESHOLD = 2


class TargetType(StrEnum):
    USER = "USER"
    PRODUCT = "PRODUCT"


class ReportContext(StrEnum):
    PROFILE = "PROFILE"
    PRODUCT = "PRODUCT"
    PRODUCT_INTERACTION = "PRODUCT_INTERACTION"
    GLOBAL_CHAT = "GLOBAL_CHAT"
    DIRECT_CHAT = "DIRECT_CHAT"


USER_CONTEXTS = frozenset(
    {
        ReportContext.PROFILE,
        ReportContext.PRODUCT_INTERACTION,
        ReportContext.GLOBAL_CHAT,
        ReportContext.DIRECT_CHAT,
    }
)


class ModerationPolicyError(ValueError):
    pass


def validate_report_context(*, target_type: TargetType, context: ReportContext) -> None:
    allowed = {ReportContext.PRODUCT} if target_type is TargetType.PRODUCT else USER_CONTEXTS
    if context not in allowed:
        raise ModerationPolicyError("report context is invalid for the target type")


def is_report_recent(*, reported_at: datetime, database_now: datetime) -> bool:
    age = database_now - reported_at
    return timedelta(0) <= age < REPORT_WINDOW


def qualifies_for_action(
    *,
    target_type: TargetType,
    independent_reporters_by_context: Mapping[ReportContext, Set[int]],
) -> bool:
    """Evaluate only unconsumed, active, in-window reports supplied by the caller."""
    qualifying_contexts = {
        context
        for context, reporter_ids in independent_reporters_by_context.items()
        if len(reporter_ids) >= INDEPENDENT_REPORTER_THRESHOLD
    }
    if target_type is TargetType.PRODUCT:
        return qualifying_contexts == {ReportContext.PRODUCT}
    return len(qualifying_contexts & USER_CONTEXTS) >= USER_CONTEXT_THRESHOLD


def action_expiry(*, database_now: datetime) -> datetime:
    return database_now + ACTION_DURATION
