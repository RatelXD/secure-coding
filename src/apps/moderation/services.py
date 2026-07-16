from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from django.db.models.functions import Now

from .models import ModerationAction
from .policies import TargetType


class EffectiveUserStatus(StrEnum):
    ACTIVE = "active"
    DORMANT = "dormant"


class EffectiveProductVisibility(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"

class ModerationActionAuthority(Protocol):
    """Transactional boundary for POL-MOD-001/002.

    Implementations lock and re-check reporter eligibility, unconsumed reports,
    canonical target status, and active actions. A qualifying transition creates
    exactly one seven-day action and audit event, consumes only contributing
    reports, and increments ``auth_epoch`` for user dormancy in one transaction.
    """

    def evaluate_threshold(
        self,
        *,
        target_type: TargetType,
        target_id: int,
    ) -> ModerationAction | None: ...


def effective_user_status(*, user_id: int) -> EffectiveUserStatus:
    """Return the canonical status using database time in the authority query."""
    dormant = ModerationAction.objects.filter(
        kind=ModerationAction.Kind.USER_DORMANCY,
        target_user_id=user_id,
        starts_at__lte=Now(),
        expires_at__gt=Now(),
    ).exists()
    return EffectiveUserStatus.DORMANT if dormant else EffectiveUserStatus.ACTIVE


def effective_product_visibility(*, product_id: int) -> EffectiveProductVisibility:
    """Return canonical visibility; callers must not trust a stored flag."""
    hidden = ModerationAction.objects.filter(
        kind=ModerationAction.Kind.PRODUCT_HIDE,
        target_product_id=product_id,
        starts_at__lte=Now(),
        expires_at__gt=Now(),
    ).exists()
    return EffectiveProductVisibility.HIDDEN if hidden else EffectiveProductVisibility.VISIBLE
