from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_loginthrottle'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='loginthrottle',
            index=models.Index(fields=['updated_at'], name='accounts_login_updated_idx'),
        ),
    ]
