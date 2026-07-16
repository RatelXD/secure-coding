from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Now
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModerationAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("USER_DORMANCY", "User dormancy"), ("PRODUCT_HIDE", "Product hide")], max_length=24)),
                ("starts_at", models.DateTimeField(db_default=Now(), editable=False)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(db_default=Now(), editable=False)),
                ("target_product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="moderation_actions", to="catalog.product")),
                ("target_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="moderation_actions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("kind", "USER_DORMANCY"), ("target_product__isnull", True), ("target_user__isnull", False), _connector="OR") | models.Q(("kind", "PRODUCT_HIDE"), ("target_product__isnull", False), ("target_user__isnull", True)), name="moderation_action_target_matches_kind"),
                    models.CheckConstraint(condition=models.Q(("expires_at__gt", models.F("starts_at"))), name="moderation_action_positive_window"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AbuseReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_type", models.CharField(choices=[("USER", "User"), ("PRODUCT", "Product")], max_length=12)),
                ("context", models.CharField(choices=[("PROFILE", "Profile"), ("PRODUCT", "Product"), ("PRODUCT_INTERACTION", "Product interaction"), ("GLOBAL_CHAT", "Global chat"), ("DIRECT_CHAT", "Direct chat")], max_length=24)),
                ("created_at", models.DateTimeField(db_default=Now(), editable=False)),
                ("consumed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="consumed_reports", to="moderation.moderationaction")),
                ("reporter", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="abuse_reports", to=settings.AUTH_USER_MODEL)),
                ("target_product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="abuse_reports", to="catalog.product")),
                ("target_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="received_abuse_reports", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("target_product__isnull", True), ("target_type", "USER"), ("target_user__isnull", False), _connector="OR") | models.Q(("target_product__isnull", False), ("target_type", "PRODUCT"), ("target_user__isnull", True)), name="moderation_report_exactly_one_target"),
                    models.CheckConstraint(condition=models.Q(("context", "PRODUCT"), ("target_type", "PRODUCT"), _connector="OR") | (models.Q(("target_type", "USER")) & ~models.Q(("context", "PRODUCT"))), name="moderation_report_context_matches_target"),
                    models.UniqueConstraint(condition=models.Q(("target_user__isnull", False)), fields=("reporter", "target_user"), name="moderation_unique_reporter_user"),
                    models.UniqueConstraint(condition=models.Q(("target_product__isnull", False)), fields=("reporter", "target_product"), name="moderation_unique_reporter_product"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=64)),
                ("details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(db_default=Now(), editable=False)),
                ("action", models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audit_events", to="moderation.moderationaction")),
                ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
