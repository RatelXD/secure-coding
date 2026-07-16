from __future__ import annotations

from collections.abc import Mapping, Set
from datetime import datetime, timedelta
from enum import StrEnum

MIN_REPORTER_AGE = timedelta(days=7)
ACTION_DURATION = timedelta(days=7)
PRODUCT_REPORTER_THRESHOLD = 5
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
    if target_type is TargetType.PRODUCT:
        allowed = {ReportContext.PRODUCT}
    elif target_type is TargetType.USER:
        allowed = USER_CONTEXTS
    else:
        raise ModerationPolicyError("unknown report target type")
    if context not in allowed:
        raise ModerationPolicyError("report context is invalid for the target type")


def is_reporter_eligible(
    *,
    joined_at: datetime,
    is_active: bool,
    database_now: datetime,
) -> bool:
    account_age = database_now - joined_at
    return is_active and account_age >= MIN_REPORTER_AGE


def qualifies_for_action(
    *,
    target_type: TargetType,
    independent_reporters_by_context: Mapping[ReportContext, Set[int]],
) -> bool:
    """Evaluate eligible, independent, unconsumed reports supplied by the caller."""
    seen_reporters: set[int] = set()
    for context, reporter_ids in independent_reporters_by_context.items():
        validate_report_context(target_type=target_type, context=context)
        duplicate_reporters = seen_reporters.intersection(reporter_ids)
        if duplicate_reporters:
            raise ModerationPolicyError("a reporter cannot contribute in multiple contexts")
        seen_reporters.update(reporter_ids)

    if target_type is TargetType.PRODUCT:
        return (
            len(independent_reporters_by_context.get(ReportContext.PRODUCT, set()))
            >= PRODUCT_REPORTER_THRESHOLD
        )

    distinct_contexts = {
        context
        for context, reporter_ids in independent_reporters_by_context.items()
        if context in USER_CONTEXTS and reporter_ids
    }
    return len(distinct_contexts) >= USER_CONTEXT_THRESHOLD


def action_expiry(*, database_now: datetime) -> datetime:
    return database_now + ACTION_DURATION
