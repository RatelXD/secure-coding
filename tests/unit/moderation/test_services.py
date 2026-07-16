from __future__ import annotations

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.utils import timezone

from apps.catalog.models import Product
from apps.moderation.models import AbuseReport, AuditEvent, ModerationAction
from apps.moderation.policies import ReportContext, TargetType
from apps.moderation.services import (
    DuplicateReportError,
    EffectiveProductVisibility,
    EffectiveUserStatus,
    ReportSubmissionError,
    effective_product_visibility,
    effective_user_status,
    submit_report,
    visible_products,
)

pytestmark = pytest.mark.django_db(transaction=True)


def make_user(username: str, *, age_days: int = 8, active: bool = True):
    user = get_user_model().objects.create_user(username=username, password="valid-test-password-123", is_active=active)
    get_user_model().objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=age_days))
    user.refresh_from_db()
    return user


def make_product(owner, suffix: str = "one") -> Product:
    return Product.objects.create(owner=owner, title=f"product-{suffix}", description="description", price=10_000)


def test_product_threshold_is_exactly_one_reversible_action() -> None:
    owner = make_user("owner_01")
    product = make_product(owner)
    reporters = [make_user(f"reporter_{index}") for index in range(5)]

    for reporter in reporters[:4]:
        result = submit_report(
            reporter=reporter,
            target_type=TargetType.PRODUCT,
            target_id=product.pk,
            context=ReportContext.PRODUCT,
            reason="unsafe listing",
        )
        assert result.action is None

    result = submit_report(
        reporter=reporters[4],
        target_type=TargetType.PRODUCT,
        target_id=product.pk,
        context=ReportContext.PRODUCT,
        reason="unsafe listing",
    )
    assert result.action is not None
    assert result.action.expires_at - result.action.starts_at == timedelta(days=7)
    assert ModerationAction.objects.count() == 1
    assert AuditEvent.objects.filter(action=result.action).count() == 1
    assert AbuseReport.objects.filter(consumed_by=result.action).count() == 5
    assert effective_product_visibility(product_id=product.pk) is EffectiveProductVisibility.HIDDEN
    assert not visible_products(Product.objects.all()).filter(pk=product.pk).exists()


def test_user_requires_five_reporters_and_two_contexts_and_increments_epoch() -> None:
    target = make_user("target_01")
    reporters = [make_user(f"actor_{index}") for index in range(5)]
    contexts = [
        ReportContext.PROFILE,
        ReportContext.PROFILE,
        ReportContext.PROFILE,
        ReportContext.PROFILE,
        ReportContext.DIRECT_CHAT,
    ]

    for reporter, context in zip(reporters[:4], contexts[:4], strict=True):
        assert submit_report(
            reporter=reporter,
            target_type=TargetType.USER,
            target_id=target.pk,
            context=context,
            reason="abusive behavior",
        ).action is None

    result = submit_report(
        reporter=reporters[4],
        target_type=TargetType.USER,
        target_id=target.pk,
        context=contexts[4],
        reason="abusive behavior",
    )
    target.refresh_from_db()
    assert result.action is not None
    assert target.auth_epoch == 1
    assert effective_user_status(user_id=target.pk) is EffectiveUserStatus.DORMANT
    assert ModerationAction.objects.count() == 1
    assert AuditEvent.objects.filter(action=result.action).count() == 1


def test_invalid_reporters_self_reports_duplicates_and_blank_reason_are_rejected() -> None:
    owner = make_user("owner_02")
    product = make_product(owner, "two")
    young = make_user("young_01", age_days=6)
    inactive = make_user("inactive_01", active=False)
    eligible = make_user("eligible_01")

    for reporter in (owner, young, inactive):
        with pytest.raises(ReportSubmissionError):
            submit_report(
                reporter=reporter,
                target_type=TargetType.PRODUCT,
                target_id=product.pk,
                context=ReportContext.PRODUCT,
                reason="reason",
            )
    with pytest.raises(ReportSubmissionError):
        submit_report(
            reporter=eligible,
            target_type=TargetType.PRODUCT,
            target_id=product.pk,
            context=ReportContext.PRODUCT,
            reason="  ",
        )

    submit_report(
        reporter=eligible,
        target_type=TargetType.PRODUCT,
        target_id=product.pk,
        context=ReportContext.PRODUCT,
        reason="first report",
    )
    with pytest.raises(DuplicateReportError):
        submit_report(
            reporter=eligible,
            target_type=TargetType.PRODUCT,
            target_id=product.pk,
            context=ReportContext.PRODUCT,
            reason="duplicate report",
        )
    assert AbuseReport.objects.count() == 1


def test_expired_action_restores_visibility_without_deletion() -> None:
    owner = make_user("owner_03")
    product = make_product(owner, "three")
    now = timezone.now()
    action = ModerationAction.objects.create(
        kind=ModerationAction.Kind.PRODUCT_HIDE,
        target_product=product,
        starts_at=now - timedelta(days=8),
        expires_at=now - timedelta(days=1),
    )
    assert effective_product_visibility(product_id=product.pk) is EffectiveProductVisibility.VISIBLE
    assert visible_products(Product.objects.all()).filter(pk=product.pk).exists()
    assert ModerationAction.objects.filter(pk=action.pk).exists()


def test_concurrent_fifth_report_creates_one_action_and_one_audit() -> None:
    owner = make_user("owner_04")
    product = make_product(owner, "concurrent")
    reporter_ids = [make_user(f"racer_{index}").pk for index in range(5)]
    barrier = Barrier(5)

    def report(reporter_id: int) -> None:
        close_old_connections()
        try:
            reporter = get_user_model().objects.get(pk=reporter_id)
            barrier.wait(timeout=10)
            submit_report(
                reporter=reporter,
                target_type=TargetType.PRODUCT,
                target_id=product.pk,
                context=ReportContext.PRODUCT,
                reason="concurrent report",
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(report, reporter_id) for reporter_id in reporter_ids]
        for future in futures:
            future.result(timeout=20)

    action = ModerationAction.objects.get(target_product=product)
    assert AbuseReport.objects.filter(consumed_by=action).count() == 5
    assert AuditEvent.objects.filter(action=action).count() == 1
