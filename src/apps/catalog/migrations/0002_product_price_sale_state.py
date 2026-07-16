import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="price",
            field=models.DecimalField(
                decimal_places=0,
                default=1,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="product",
            name="sale_state",
            field=models.CharField(
                choices=[("AVAILABLE", "판매 중"), ("SOLD", "판매 완료")],
                default="AVAILABLE",
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("price__gte", 1)),
                name="catalog_product_price_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(("sale_state__in", ("AVAILABLE", "SOLD"))),
                name="catalog_product_sale_state_valid",
            ),
        ),
    ]
