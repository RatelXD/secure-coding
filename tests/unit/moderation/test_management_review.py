from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.moderation.management import (
    ManagementDenied,
    ManagementConflict,
    ManagementNotFound,
    apply_sanction,
    set_review_visibility,
)
from apps.moderation.models import AdminAudit, AdminScopeGrant, AbuseReport, ModerationAction
from apps.moderation.services import ReportSubmissionError, submit_review_report
from apps.trades.models import Review, ReviewVisibilityAction, Trade
from apps.trades.services import ReviewAuthorityError, create_review, public_reviews

pytestmark = pytest.mark.django_db(transaction=True)


def _user(username: str, **fields):
    return get_user_model().objects.create_user(
        username=username,
        password="long-test-password-123",
        date_joined=timezone.now() - timedelta(days=30),
        **fields,
    )


def _product(owner) -> Product:
    category, _ = Category.objects.get_or_create(
        code="OTHER",
        defaults={"label": "기타", "display_order": 99},
    )
    return Product.objects.create(
        owner=owner,
        title="권위 상품",
        description="거래 후기 테스트 상품",
        price=10000,
        category=category,
    )


def _completed_trade(seller, buyer) -> Trade:
    return Trade.objects.create(
        product=_product(seller),
        seller=seller,
        buyer=buyer,
        kind=Trade.Kind.STANDARD,
        status=Trade.Status.COMPLETED,
        completed_at=timezone.now(),
    )


def _permission(codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label="moderation", codename=codename)


def test_review_eligibility_is_derived_from_completed_trade_parties() -> None:
    seller = _user("review_seller")
    buyer = _user("review_buyer")
    outsider = _user("review_outsider")
    trade = _completed_trade(seller, buyer)

    created = create_review(actor=buyer, trade_id=trade.pk, rating=5, body="  안전한 거래였습니다  ")
    replay = create_review(actor=buyer, trade_id=trade.pk, rating=5, body="안전한 거래였습니다")

    assert created.created is True
    assert replay.created is False
    assert created.review.subject_id == seller.pk
    assert Review.objects.count() == 1
    with pytest.raises(ReviewAuthorityError):
        create_review(actor=outsider, trade_id=trade.pk, rating=5, body="위조 후기입니다")
    with pytest.raises(ReviewAuthorityError, match="replay"):
        create_review(actor=buyer, trade_id=trade.pk, rating=1, body="내용을 바꿉니다")
    assert Review.objects.count() == 1


def test_legacy_or_incomplete_trade_cannot_fabricate_review_eligibility() -> None:
    seller = _user("legacy_review_seller")
    product = _product(seller)
    legacy = Trade.objects.create(
        product=product,
        seller=seller,
        buyer=None,
        kind=Trade.Kind.LEGACY_SOLD,
        status=Trade.Status.COMPLETED,
        completed_at=timezone.now(),
    )

    with pytest.raises(ReviewAuthorityError):
        create_review(actor=seller, trade_id=legacy.pk, rating=5, body="허용되지 않는 후기")
    assert Review.objects.count() == 0


def test_review_rows_are_database_immutable() -> None:
    seller = _user("immutable_seller")
    buyer = _user("immutable_buyer")
    review = create_review(
        actor=buyer,
        trade_id=_completed_trade(seller, buyer).pk,
        rating=4,
        body="수정할 수 없는 후기",
    ).review

    with pytest.raises(DatabaseError), transaction.atomic():
        Review.objects.filter(pk=review.pk).update(rating=1)
    review.refresh_from_db()
    assert review.rating == 4


def test_review_hide_requires_report_permission_and_exact_scope() -> None:
    seller = _user("visibility_seller")
    buyer = _user("visibility_buyer")
    reporter = _user("visibility_reporter")
    staff = _user("visibility_staff", is_staff=True)
    review = create_review(
        actor=buyer,
        trade_id=_completed_trade(seller, buyer).pk,
        rating=5,
        body="신고 기반 가시성 후기",
    ).review
    report = submit_review_report(reporter=reporter, review_id=review.pk, reason="정책 위반 후기 신고")
    assert report.target_review_id == review.pk

    staff.user_permissions.add(_permission("hide_review"))

    with pytest.raises(ManagementNotFound):
        set_review_visibility(
            actor=staff,
            review_id=review.pk,
            kind=ReviewVisibilityAction.Kind.HIDE,
            reason="신고 확인 후 숨김 처리",
            idempotency_key=uuid4(),
            reauthenticated_at=timezone.now(),
        )

    del staff._perm_cache

    AdminScopeGrant.objects.create(
        staff=staff,
        codename=AdminScopeGrant.Codename.HIDE_REVIEW,
        target_review=review,
        granted_by=seller,
    )
    hidden = set_review_visibility(
        actor=staff,
        review_id=review.pk,
        kind=ReviewVisibilityAction.Kind.HIDE,
        reason="신고 확인 후 숨김 처리",
        idempotency_key=uuid4(),
        reauthenticated_at=timezone.now(),
    )

    assert hidden.created is True
    assert not public_reviews().filter(pk=review.pk).exists()
    assert AdminAudit.objects.filter(action="hide", target_id=review.pk, result="SUCCESS").count() == 1


def test_review_report_rejects_author_and_duplicate_reporter() -> None:
    seller = _user("report_seller")
    buyer = _user("report_buyer")
    reporter = _user("report_third_party")
    review = create_review(
        actor=buyer,
        trade_id=_completed_trade(seller, buyer).pk,
        rating=2,
        body="신고할 수 있는 후기",
    ).review

    with pytest.raises(ReportSubmissionError):
        submit_review_report(reporter=buyer, review_id=review.pk, reason="자기 후기 신고 시도")
    submit_review_report(reporter=reporter, review_id=review.pk, reason="첫 번째 정상 신고")
    with pytest.raises(ReportSubmissionError):
        submit_review_report(reporter=reporter, review_id=review.pk, reason="중복 신고 시도입니다")
    assert AbuseReport.objects.filter(target_review=review).count() == 1


def test_superuser_without_target_scope_cannot_apply_sanction() -> None:
    actor = _user("unscoped_superuser", is_staff=True, is_superuser=True)
    target = _user("sanction_target")

    with pytest.raises(ManagementNotFound):
        apply_sanction(
            actor=actor,
            target_type="USER",
            target_id=target.pk,
            reason="대상 범위 없이 권한 상승 시도",
            version=target.auth_epoch,
            reauthenticated_at=timezone.now(),
        )
    assert ModerationAction.objects.count() == 0
    assert AdminAudit.objects.filter(action="apply", result="DENIED").count() == 1


def test_staff_permission_and_scope_are_both_required_for_sanction() -> None:
    actor = _user("permissionless_staff", is_staff=True)
    target = _user("permission_target")
    AdminScopeGrant.objects.create(
        staff=actor,
        codename=AdminScopeGrant.Codename.APPLY_SANCTION,
        target_user=target,
        granted_by=target,
    )

    with pytest.raises(ManagementDenied):
        apply_sanction(
            actor=actor,
            target_type="USER",
            target_id=target.pk,
            reason="권한 없는 관리자 제재 시도",
            version=target.auth_epoch,
            reauthenticated_at=timezone.now(),
        )
    assert ModerationAction.objects.count() == 0
    assert AdminAudit.objects.filter(action="apply", result="DENIED").count() == 1


def test_stale_sanction_write_records_one_conflict_audit_without_mutation() -> None:
    actor = _user("stale_staff", is_staff=True)
    target = _user("stale_target")
    actor.user_permissions.add(_permission("apply_sanction"))
    AdminScopeGrant.objects.create(
        staff=actor,
        codename=AdminScopeGrant.Codename.APPLY_SANCTION,
        target_user=target,
        granted_by=target,
    )


    with pytest.raises(ManagementConflict):
        apply_sanction(
            actor=actor,
            target_type="USER",
            target_id=target.pk,
            reason="오래된 화면의 제재 요청 거부",
            version=target.auth_epoch + 1,
            reauthenticated_at=timezone.now(),
        )
    assert ModerationAction.objects.count() == 0
    assert AdminAudit.objects.filter(action="apply", result="CONFLICT").count() == 1


def test_unreported_review_cannot_be_hidden_even_with_permission_and_scope() -> None:
    seller = _user("unreported_seller")
    buyer = _user("unreported_buyer")
    staff = _user("unreported_staff", is_staff=True)
    review = create_review(
        actor=buyer,
        trade_id=_completed_trade(seller, buyer).pk,
        rating=3,
        body="신고가 없는 정상 후기",
    ).review
    staff.user_permissions.add(_permission("hide_review"))
    AdminScopeGrant.objects.create(
        staff=staff,
        codename=AdminScopeGrant.Codename.HIDE_REVIEW,
        target_review=review,
        granted_by=seller,
    )

    with pytest.raises(ManagementNotFound):
        set_review_visibility(
            actor=staff,
            review_id=review.pk,
            kind=ReviewVisibilityAction.Kind.HIDE,
            reason="신고 없이 숨김을 시도함",
            idempotency_key=uuid4(),
            reauthenticated_at=timezone.now(),
        )
    assert ReviewVisibilityAction.objects.count() == 0
    assert AdminAudit.objects.count() == 0
