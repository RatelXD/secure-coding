from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol

from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from .models import LoginThrottle, User
from .validators import canonicalize_username
PROFILE_MUTABLE_FIELDS = frozenset({"bio"})
IDENTITY_IMMUTABLE_FIELDS = frozenset({"id", "username", "auth_epoch", "is_staff", "is_superuser"})
SESSION_AUTH_EPOCH_KEY = "account_auth_epoch"


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

    with transaction.atomic():
        account_throttle = _locked_throttle(
            scope=LoginThrottle.Scope.ACCOUNT,
            identifier_digest=account_digest,
            now=now,
        )
        ip_throttle = _locked_throttle(
            scope=LoginThrottle.Scope.IP,
            identifier_digest=ip_digest,
            now=now,
        )
        if _is_blocked(account_throttle, now) or _is_blocked(ip_throttle, now):
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

        if effective_user_status(user_id=user.pk) is not EffectiveUserStatus.ACTIVE:
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
    """Apply the canonical moderation status and auth epoch at the HTTP boundary."""

    user = request.user
    if not user.is_authenticated:
        return None

    session_epoch = request.session.get(SESSION_AUTH_EPOCH_KEY)
    if session_epoch is None:
        request.session[SESSION_AUTH_EPOCH_KEY] = user.auth_epoch
    elif session_epoch != user.auth_epoch:
        logout(request)
        return HttpResponse("Account unavailable.", status=403, content_type="text/plain")

    # Lazy import keeps account identity independent from moderation persistence.
    from apps.moderation.services import EffectiveUserStatus, effective_user_status

    if user.is_active and effective_user_status(user_id=user.pk) is EffectiveUserStatus.ACTIVE:
        return None

    logout(request)
    return HttpResponse("Account unavailable.", status=403, content_type="text/plain")
