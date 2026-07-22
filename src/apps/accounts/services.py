from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from django.conf import settings
from django.contrib.auth import authenticate, logout, update_session_auth_hash
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.db.models import F

from .models import LoginThrottle, User, UserSessionIndex
from .validators import canonicalize_username
PROFILE_MUTABLE_FIELDS = frozenset({"bio"})
IDENTITY_IMMUTABLE_FIELDS = frozenset(
    {"id", "username", "auth_epoch", "withdrawn_at", "is_staff", "is_superuser"}
)
SESSION_AUTH_EPOCH_KEY = "account_auth_epoch"
SESSION_INDEX_TOUCH_INTERVAL = timedelta(minutes=5)
WITHDRAWAL_ACTIVATION_ENABLED = True

if TYPE_CHECKING:
    from .models import RevocationTask


class EffectiveAccountStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


WITHDRAWN_ACCOUNT_LABEL = "탈퇴한 회원"


@dataclass(frozen=True, slots=True)
class AccountIdentityProjection:
    user_id: int | None
    display_name: str
    status: EffectiveAccountStatus

    @property
    def is_tombstone(self) -> bool:
        return self.status is EffectiveAccountStatus.WITHDRAWN


@dataclass(frozen=True, slots=True)
class RevocationPreparation:
    task: "RevocationTask"
    created: bool


class RevocationPreparationError(ValueError):
    """Revocation preparation rejected stale or non-withdrawn account state."""


def effective_account_status(*, user: User | None) -> EffectiveAccountStatus:
    """Project withdrawal state, treating absent identities as withdrawn."""
    if user is None or user.pk is None or user.withdrawn_at is not None:
        return EffectiveAccountStatus.WITHDRAWN
    return EffectiveAccountStatus.ACTIVE


def project_account_identity(*, user: User | None) -> AccountIdentityProjection:
    """Return a public identity projection that never exposes a withdrawn username."""
    status = effective_account_status(user=user)
    if user is None or status is EffectiveAccountStatus.WITHDRAWN or not user.username:
        return AccountIdentityProjection(
            user_id=None if user is None else user.pk,
            display_name=WITHDRAWN_ACCOUNT_LABEL,
            status=EffectiveAccountStatus.WITHDRAWN,
        )
    return AccountIdentityProjection(
        user_id=user.pk,
        display_name=user.username,
        status=EffectiveAccountStatus.ACTIVE,
    )


def withdrawal_event_key(*, user_id: int, auth_epoch: int) -> str:
    return f"withdrawal:{user_id}:auth-epoch:{auth_epoch}"


class AccountSessionService:
    """Internal boundary for durable authenticated-session indexing."""

    @staticmethod
    def _session_key(request: HttpRequest) -> str:
        if request.session.session_key is None:
            request.session.save()
        session_key = request.session.session_key
        if not session_key:
            raise RuntimeError("authenticated session has no session key")
        return session_key

    @classmethod
    def start(cls, *, request: HttpRequest, user: User) -> UserSessionIndex:
        """Index the current Django session after login or session-key rotation."""
        session_key = cls._session_key(request)
        request.session[SESSION_AUTH_EPOCH_KEY] = user.auth_epoch
        now = timezone.now()
        session_index, created = UserSessionIndex.objects.get_or_create(
            session_key=session_key,
            defaults={
                "user": user,
                "auth_epoch": user.auth_epoch,
                "last_seen_at": now,
            },
        )
        if not created:
            if session_index.user_id != user.pk:
                raise RuntimeError("session key is already indexed to another user")
            if session_index.revoked_at is not None:
                raise RuntimeError("authenticated session is revoked")
            if session_index.auth_epoch != user.auth_epoch:
                session_index.auth_epoch = user.auth_epoch
                session_index.last_seen_at = now
                session_index.save(update_fields=("auth_epoch", "last_seen_at"))
        return session_index

    @classmethod
    def rotate_after_password_change(
        cls, *, request: HttpRequest, user: User
    ) -> UserSessionIndex:
        """Advance the auth epoch, revoke the old key, and index Django's new key."""
        cls.end(request=request, flush=False)
        User.objects.filter(pk=user.pk).update(auth_epoch=F("auth_epoch") + 1)
        user.refresh_from_db(fields=("auth_epoch",))
        update_session_auth_hash(request, user)
        return cls.start(request=request, user=user)

    @classmethod
    def end(cls, *, request: HttpRequest, flush: bool = True) -> None:
        """Revoke the indexed key before Django discards its session."""
        session_key = request.session.session_key
        if session_key:
            UserSessionIndex.objects.filter(
                session_key=session_key,
                revoked_at__isnull=True,
            ).update(revoked_at=timezone.now())
        if flush:
            logout(request)

    @classmethod
    def validate_request(cls, *, request: HttpRequest, user: User) -> bool:
        """Backfill rolling-upgrade sessions and lazily update indexed last-seen time."""
        session_epoch = request.session.get(SESSION_AUTH_EPOCH_KEY)
        if (
            isinstance(session_epoch, bool)
            or not isinstance(session_epoch, int)
            or session_epoch != user.auth_epoch
        ):
            return False

        session_key = cls._session_key(request)
        try:
            session_index = UserSessionIndex.objects.get(session_key=session_key)
        except UserSessionIndex.DoesNotExist:
            try:
                cls.start(request=request, user=user)
            except RuntimeError:
                return False
            return True

        if (
            session_index.user_id != user.pk
            or session_index.auth_epoch != user.auth_epoch
            or session_index.revoked_at is not None
        ):
            return False
        now = timezone.now()
        if session_index.last_seen_at <= now - SESSION_INDEX_TOUCH_INTERVAL:
            UserSessionIndex.objects.filter(
                pk=session_index.pk,
                last_seen_at__lte=now - SESSION_INDEX_TOUCH_INTERVAL,
            ).update(last_seen_at=now)
        return True


def prepare_withdrawal_revocation(
    *,
    user_id: int,
    auth_epoch: int,
) -> RevocationPreparation:
    """Create the durable revocation task without changing or deleting account data."""

    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
        or isinstance(auth_epoch, bool)
        or not isinstance(auth_epoch, int)
        or auth_epoch <= 0
    ):
        raise RevocationPreparationError("revocation state is invalid")

    # Lazy import lets the read-side projector remain usable during rolling deploys.
    from .models import RevocationTask

    with transaction.atomic():
        try:
            user = User.objects.select_for_update().get(pk=user_id)
        except User.DoesNotExist as exc:
            raise RevocationPreparationError("revocation state is invalid") from exc

        if (
            effective_account_status(user=user) is not EffectiveAccountStatus.WITHDRAWN
            or user.withdrawn_at is None
            or user.is_active
            or user.has_usable_password()
            or user.auth_epoch != auth_epoch
        ):
            raise RevocationPreparationError("revocation state is invalid")

        event_key = withdrawal_event_key(user_id=user.pk, auth_epoch=auth_epoch)
        task, created = RevocationTask.objects.get_or_create(
            user=user,
            auth_epoch=auth_epoch,
            defaults={"event_key": event_key},
        )
        if task.event_key != event_key:
            raise RevocationPreparationError("revocation replay is invalid")
        return RevocationPreparation(task=task, created=created)


class ProfileService(Protocol):
    """Cycle 1 boundary: a user may update only their own profile bio."""

    def update_own_profile(self, *, actor: User, changes: Mapping[str, object]) -> User: ...


class PasswordChangeService(Protocol):
    """Password changes belong behind Django password validation and session rotation."""

    def change_own_password(
        self,
        *,
        actor: User,
        current_password: str,
        new_password: str,
    ) -> None: ...


LOGIN_WINDOW = timedelta(minutes=15)
_ACCOUNT_THRESHOLD = 5
_IP_THRESHOLD = 20
_ACCOUNT_COOLDOWN = timedelta(minutes=15)
_IP_COOLDOWN = timedelta(minutes=30)
_THROTTLE_RETENTION = timedelta(hours=24)


def _opaque_identifier(scope: LoginThrottle.Scope, value: str) -> str:
    key = str(settings.SECRET_KEY).encode("utf-8")
    message = f"login-throttle:{scope}:{value}".encode("utf-8", errors="replace")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def client_ip_identifier(request: HttpRequest) -> str:
    """Return an opaque, keyed identifier; raw network addresses are never persisted."""

    return _opaque_identifier(LoginThrottle.Scope.IP, request.META.get("REMOTE_ADDR", ""))


def account_login_identifier(username: str) -> str:
    canonical_candidate = username.strip().lower()
    return _opaque_identifier(LoginThrottle.Scope.ACCOUNT, canonical_candidate)


def _locked_throttle(
    *,
    scope: LoginThrottle.Scope,
    identifier_digest: str,
    now: datetime,
) -> LoginThrottle:
    try:
        return LoginThrottle.objects.select_for_update().get(
            scope=scope,
            identifier_digest=identifier_digest,
        )
    except LoginThrottle.DoesNotExist:
        try:
            with transaction.atomic():
                return LoginThrottle.objects.create(
                    scope=scope,
                    identifier_digest=identifier_digest,
                    window_started_at=now,
                )
        except IntegrityError:
            return LoginThrottle.objects.select_for_update().get(
                scope=scope,
                identifier_digest=identifier_digest,
            )

def _prune_expired_throttles(now: datetime) -> None:
    LoginThrottle.objects.filter(updated_at__lt=now - _THROTTLE_RETENTION).delete()



def _is_blocked(throttle: LoginThrottle, now: datetime) -> bool:
    return throttle.blocked_until is not None and throttle.blocked_until > now


def _record_failure(
    throttle: LoginThrottle,
    *,
    now: datetime,
    threshold: int,
    cooldown: timedelta,
) -> None:
    if now - throttle.window_started_at >= LOGIN_WINDOW:
        throttle.window_started_at = now
        throttle.failure_count = 0
        throttle.blocked_until = None

    throttle.failure_count += 1
    if throttle.failure_count >= threshold:
        throttle.blocked_until = now + cooldown
    throttle.save(
        update_fields=(
            "window_started_at",
            "failure_count",
            "blocked_until",
            "updated_at",
        )
    )


def authenticate_login(
    *,
    request: HttpRequest,
    username: str,
    password: str,
) -> User | None:
    """Authenticate under locked account/IP throttle rows and return no failure detail."""

    now = timezone.now()
    account_digest = account_login_identifier(username)
    ip_digest = client_ip_identifier(request)

    _prune_expired_throttles(now)
    with transaction.atomic():
        ip_throttle = _locked_throttle(
            scope=LoginThrottle.Scope.IP,
            identifier_digest=ip_digest,
            now=now,
        )
        if _is_blocked(ip_throttle, now):
            return None
        account_throttle = _locked_throttle(
            scope=LoginThrottle.Scope.ACCOUNT,
            identifier_digest=account_digest,
            now=now,
        )
        if _is_blocked(account_throttle, now):
            return None

        try:
            canonical_candidate = canonicalize_username(username)
        except ValidationError:
            canonical_candidate = f"invalid_{account_digest[:12]}"
        password_candidate = password
        if "\x00" in password or not 12 <= len(password) <= 128:
            canonical_candidate = f"invalid_{account_digest[:12]}"
            password_candidate = "invalid-password-input"

        user = authenticate(
            request=request,
            username=canonical_candidate,
            password=password_candidate,
        )
        if user is None:
            _record_failure(
                account_throttle,
                now=now,
                threshold=_ACCOUNT_THRESHOLD,
                cooldown=_ACCOUNT_COOLDOWN,
            )
            _record_failure(
                ip_throttle,
                now=now,
                threshold=_IP_THRESHOLD,
                cooldown=_IP_COOLDOWN,
            )
            return None

        from apps.moderation.services import EffectiveUserStatus, effective_user_status

        if (
            effective_account_status(user=user) is not EffectiveAccountStatus.ACTIVE
            or effective_user_status(user_id=user.pk) is not EffectiveUserStatus.ACTIVE
        ):
            return None

        account_throttle.window_started_at = now
        account_throttle.failure_count = 0
        account_throttle.blocked_until = None
        account_throttle.save(
            update_fields=(
                "window_started_at",
                "failure_count",
                "blocked_until",
                "updated_at",
            )
        )
        return user


def enforce_http_user_status(request: HttpRequest) -> HttpResponse | None:
    """Apply withdrawal, moderation, and auth-epoch status at the HTTP boundary."""

    user = request.user
    if not user.is_authenticated:
        return None

    if not AccountSessionService.validate_request(request=request, user=user):
        AccountSessionService.end(request=request)
        return HttpResponse("Account unavailable.", status=403, content_type="text/plain")

    # Lazy import keeps account identity independent from moderation persistence.
    from apps.moderation.services import EffectiveUserStatus, effective_user_status

    if (
        user.is_active
        and effective_account_status(user=user) is EffectiveAccountStatus.ACTIVE
        and effective_user_status(user_id=user.pk) is EffectiveUserStatus.ACTIVE
    ):
        return None

    AccountSessionService.end(request=request)
    return HttpResponse("Account unavailable.", status=403, content_type="text/plain")
