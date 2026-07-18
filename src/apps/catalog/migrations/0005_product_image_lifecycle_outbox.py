from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0004_freeze_legacy_product_authority")]

    operations = [
        migrations.AddField(
            model_name="productimage",
            name="owned_key",
            field=models.CharField(default="", editable=False, max_length=255),
        ),
        migrations.AddField(
            model_name="productimage",
            name="promotion_state",
            field=models.CharField(
                choices=[("PENDING", "Pending"), ("PROMOTED", "Promoted")],
                default="PROMOTED",
                editable=False,
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="ProductImageDeletionIntent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("storage_key", models.CharField(max_length=255, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ("pk",)},
        ),
    ]
