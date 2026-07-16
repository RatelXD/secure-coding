from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.catalog.models import Product
from apps.moderation.models import AbuseReport, AuditEvent, ModerationAction
from apps.moderation.policies import ReportContext, TargetType
from apps.moderation.services import submit_report


User = get_user_model()


class ConcurrentModerationIntegrationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        joined_at = timezone.now() - timedelta(days=8)
        self.owner = User.objects.create_user(
            username="threshold_owner",
            password="Correct-Horse-Battery-47!",
        )
        self.reporters = [
            User.objects.create_user(
                username=f"reporter_{index}",
                password="Correct-Horse-Battery-47!",
            )
            for index in range(5)
        ]
        User.objects.filter(pk__in=[user.pk for user in self.reporters]).update(
            date_joined=joined_at
        )
        product_values: dict[str, object] = {
            "owner": self.owner,
            "title": "신고 대상 상품",
            "description": "설명",
            "image": "product-images/concurrency.png",
        }
        product_fields = {field.name for field in Product._meta.get_fields()}
        if "price" in product_fields:
            product_values["price"] = 1000
        if "sale_state" in product_fields:
            product_values["sale_state"] = Product.SaleState.AVAILABLE
        self.product = Product.objects.create(**product_values)

    def test_simultaneous_threshold_creates_exactly_one_complete_action(self) -> None:
        barrier = Barrier(len(self.reporters))

        def report(reporter_id: int) -> int | None:
            close_old_connections()
            try:
                reporter = User.objects.get(pk=reporter_id)
                barrier.wait(timeout=10)
                submission = submit_report(
                    reporter=reporter,
                    target_type=TargetType.PRODUCT,
                    target_id=self.product.pk,
                    context=ReportContext.PRODUCT,
                    reason="동시성 검증 신고",
                )
                return submission.action.pk if submission.action else None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(self.reporters)) as executor:
            results = list(executor.map(report, [user.pk for user in self.reporters]))

        actions = ModerationAction.objects.filter(
            kind=ModerationAction.Kind.PRODUCT_HIDE,
            target_product=self.product,
        )
        self.assertEqual(actions.count(), 1)
        action = actions.get()
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(AbuseReport.objects.filter(consumed_by=action).count(), 5)
        self.assertEqual(AuditEvent.objects.filter(action=action).count(), 1)
        self.assertEqual(action.expires_at - action.starts_at, timedelta(days=7))
