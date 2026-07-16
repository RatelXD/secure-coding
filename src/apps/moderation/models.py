from __future__ import annotations
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now


class ModerationAction(models.Model):
    class Kind(models.TextChoices):
        USER_DORMANCY = "USER_DORMANCY", "User dormancy"
        PRODUCT_HIDE = "PRODUCT_HIDE", "Product hide"

    kind = models.CharField(max_length=24, choices=Kind.choices)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="moderation_actions",
    )
    target_product = models.ForeignKey(
        "catalog.Product",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="moderation_actions",
    )
    starts_at = models.DateTimeField(db_default=Now(), editable=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(kind="USER_DORMANCY", target_user__isnull=False, target_product__isnull=True)
                    | Q(kind="PRODUCT_HIDE", target_user__isnull=True, target_product__isnull=False)
                ),
                name="moderation_action_target_matches_kind",
            ),
            models.CheckConstraint(
                condition=Q(expires_at=models.F("starts_at") + timedelta(days=7)),
                name="moderation_action_seven_day_window",
            ),
        ]


class AbuseReport(models.Model):
    class TargetType(models.TextChoices):
        USER = "USER", "User"
        PRODUCT = "PRODUCT", "Product"

    class Context(models.TextChoices):
        PROFILE = "PROFILE", "Profile"
        PRODUCT = "PRODUCT", "Product"
        PRODUCT_INTERACTION = "PRODUCT_INTERACTION", "Product interaction"
        GLOBAL_CHAT = "GLOBAL_CHAT", "Global chat"
        DIRECT_CHAT = "DIRECT_CHAT", "Direct chat"

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="abuse_reports")
    target_type = models.CharField(max_length=12, choices=TargetType.choices)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="received_abuse_reports",
    )
    target_product = models.ForeignKey(
        "catalog.Product",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="abuse_reports",
    )
    context = models.CharField(max_length=24, choices=Context.choices)
    reason = models.TextField(max_length=1_000)
    created_at = models.DateTimeField(db_default=Now(), editable=False)
    consumed_by = models.ForeignKey(
        ModerationAction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="consumed_reports",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(target_type="USER", target_user__isnull=False, target_product__isnull=True)
                    | Q(target_type="PRODUCT", target_user__isnull=True, target_product__isnull=False)
                ),
                name="moderation_report_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=(
                    Q(target_type="PRODUCT", context="PRODUCT")
                    | (Q(target_type="USER") & ~Q(context="PRODUCT"))
                ),
                name="moderation_report_context_matches_target",
            ),
            models.CheckConstraint(
                condition=~Q(reason=""),
                name="moderation_report_reason_required",
            ),
            models.CheckConstraint(
                condition=Q(target_user__isnull=True) | ~Q(target_user=models.F("reporter")),
                name="moderation_report_no_self_target",
            ),
            models.UniqueConstraint(
                fields=("reporter", "target_user"),
                condition=Q(target_user__isnull=False),
                name="moderation_unique_reporter_user",
            ),
            models.UniqueConstraint(
                fields=("reporter", "target_product"),
                condition=Q(target_product__isnull=False),
                name="moderation_unique_reporter_product",
            ),
        ]
        indexes = [
            models.Index(
                fields=("target_type", "target_user", "consumed_by", "-created_at"),
                name="mod_report_user_recent_idx",
            ),
            models.Index(
                fields=("target_type", "target_product", "consumed_by", "-created_at"),
                name="mod_report_product_recent_idx",
            ),
        ]


class AuditEvent(models.Model):
    event_type = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.ForeignKey(ModerationAction, null=True, on_delete=models.PROTECT, related_name="audit_events")
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("action",),
                condition=Q(action__isnull=False),
                name="moderation_one_audit_per_action",
            )
        ]
