from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

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
    withdrawn_at = models.DateTimeField(null=True, blank=True, editable=False)

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


class UserSessionIndex(models.Model):
    """Durable index from an authenticated user to a Django session."""

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="indexed_sessions",
    )
    session_key = models.CharField(max_length=40, unique=True)
    auth_epoch = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("user", "revoked_at"),
                name="accounts_session_user_rev_idx",
            )
        ]


class RevocationTask(models.Model):
    """Retryable transactional outbox entry for invalidating user sessions."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        RETRY = "retry", "Retry"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="revocation_tasks",
    )
    event_key = models.CharField(max_length=128, unique=True)
    auth_epoch = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "auth_epoch"),
                name="accounts_revocation_user_epoch_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(auth_epoch__gt=0),
                name="accounts_revocation_epoch_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="processing",
                        lease_expires_at__isnull=False,
                        heartbeat_at__isnull=False,
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        status__in=("pending", "retry"),
                        lease_expires_at__isnull=True,
                        heartbeat_at__isnull=True,
                        completed_at__isnull=True,
                    )
                    | models.Q(
                        status="completed",
                        lease_expires_at__isnull=True,
                        heartbeat_at__isnull=True,
                        completed_at__isnull=False,
                    )
                ),
                name="accounts_revocation_status_state_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        lease_expires_at__isnull=True,
                        heartbeat_at__isnull=True,
                    )
                    | models.Q(lease_expires_at__gte=models.F("heartbeat_at"))
                ),
                name="accounts_revocation_lease_after_heartbeat",
            ),
        ]
        indexes = [
            models.Index(
                fields=("status", "available_at"),
                name="accounts_revocation_ready_idx",
            ),
            models.Index(
                fields=("status", "lease_expires_at"),
                name="accounts_revocation_lease_idx",
            ),
        ]


class RevocationWorkerHeartbeat(models.Model):
    """Liveness record for a revocation outbox consumer."""

    worker_key = models.CharField(max_length=64, primary_key=True)
    heartbeat_at = models.DateTimeField()
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class LoginThrottle(models.Model):
    """Database-authoritative failure window for one opaque login identity."""

    class Scope(models.TextChoices):
        ACCOUNT = "account", "Account"
        IP = "ip", "IP"

    scope = models.CharField(max_length=8, choices=Scope.choices)
    identifier_digest = models.CharField(max_length=64)
    window_started_at = models.DateTimeField()
    failure_count = models.PositiveIntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("scope", "identifier_digest"),
                name="accounts_login_throttle_identity_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=("scope", "blocked_until"),
                name="accounts_login_block_idx",
            ),
            models.Index(
                fields=("updated_at",),
                name="accounts_login_updated_idx",
            ),
        ]
