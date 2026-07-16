from collections.abc import Mapping
from typing import Protocol

from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse

from .models import User

PROFILE_MUTABLE_FIELDS = frozenset({"bio"})
IDENTITY_IMMUTABLE_FIELDS = frozenset({"id", "username", "auth_epoch", "is_staff", "is_superuser"})


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


def enforce_http_user_status(request: HttpRequest) -> HttpResponse | None:
    """Apply the canonical moderation status at the authenticated HTTP boundary."""
    user = request.user
    if not user.is_authenticated:
        return None

    # Lazy import keeps account identity independent from moderation persistence.
    from apps.moderation.services import EffectiveUserStatus, effective_user_status

    if effective_user_status(user_id=user.pk) is EffectiveUserStatus.ACTIVE:
        return None

    logout(request)
    return HttpResponse("Account unavailable.", status=403, content_type="text/plain")
