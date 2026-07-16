from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Now
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Room",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("GLOBAL", "Global"), ("DIRECT", "Direct")], max_length=16)),
                ("created_at", models.DateTimeField(db_default=Now(), editable=False)),
            ],
        ),
        migrations.CreateModel(
            name="RoomParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("joined_at", models.DateTimeField(db_default=Now(), editable=False)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="chat.room")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("room", "user"), name="chat_unique_room_participant")],
            },
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("client_message_id", models.UUIDField()),
                ("body", models.TextField()),
                ("payload_sha256", models.CharField(editable=False, max_length=64)),
                ("accepted_at", models.DateTimeField(db_default=Now(), editable=False)),
                ("room", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="messages", to="chat.room")),
                ("sender", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["room", "id"], name="chat_room_cursor_idx")],
                "constraints": [models.UniqueConstraint(fields=("room", "sender", "client_message_id"), name="chat_unique_client_message")],
            },
        ),
    ]
