from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
        ('moderation', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='abusereport',
            name='reason',
            field=models.TextField(default='legacy report', max_length=1000),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name='abusereport',
            index=models.Index(fields=['target_type', 'target_user', 'consumed_by', '-created_at'], name='mod_report_user_recent_idx'),
        ),
        migrations.AddIndex(
            model_name='abusereport',
            index=models.Index(fields=['target_type', 'target_product', 'consumed_by', '-created_at'], name='mod_report_product_recent_idx'),
        ),
        migrations.AddConstraint(
            model_name='abusereport',
            constraint=models.CheckConstraint(condition=models.Q(('reason', ''), _negated=True), name='moderation_report_reason_required'),
        ),
        migrations.AddConstraint(
            model_name='auditevent',
            constraint=models.UniqueConstraint(condition=models.Q(('action__isnull', False)), fields=('action',), name='moderation_one_audit_per_action'),
        ),
    ]
