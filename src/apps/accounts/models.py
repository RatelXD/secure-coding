from django.contrib.auth.models import AbstractUser
from django.db import models

from .validators import canonicalize_username, validate_canonical_username


class User(AbstractUser):
    """Persistent identity; username is canonical before it reaches the database."""

    username = models.CharField(
        "username",
        max_length=30,
        unique=True,
        validators=[validate_canonical_username],
        help_text="4-30 lowercase ASCII letters, digits, or underscores.",
        error_messages={"unique": "A user with that username already exists."},
    )
    bio = models.CharField(max_length=500, blank=True)
    auth_epoch = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(username__regex=r"^[a-z0-9_]{4,30}$"),
                name="accounts_user_username_canonical",
            )
        ]

    def clean(self) -> None:
        super().clean()
        self.username = canonicalize_username(self.username)

    def save(self, *args: object, **kwargs: object) -> None:
        self.username = canonicalize_username(self.username)
        super().save(*args, **kwargs)
