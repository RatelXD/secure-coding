import sys
from enum import StrEnum
from types import ModuleType

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import RequestFactory, override_settings

from apps.accounts.models import User
from apps.accounts.services import (
    IDENTITY_IMMUTABLE_FIELDS,
    PROFILE_MUTABLE_FIELDS,
    enforce_http_user_status,
)
from apps.accounts.validators import canonicalize_username

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Alice_01 ", "alice_01"),
        ("user", "user"),
        ("a" * 30, "a" * 30),
    ],
)
def test_pol_id_001_canonical_username_accepts_boundaries(raw: str, expected: str) -> None:
    """TEST-ID ACCT-USERNAME-001: trim/lower ASCII usernames at 4 and 30 chars."""
    assert canonicalize_username(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["abc", "a" * 31, "with space", "café", "name!", "\x00user"],
)
def test_pol_id_001_canonical_username_rejects_invalid_values(raw: str) -> None:
    """TEST-ID ACCT-USERNAME-002: reject short, long, Unicode, space and control input."""
    with pytest.raises(ValidationError):
        canonicalize_username(raw)


def test_pol_id_001_persists_only_canonical_unique_username() -> None:
    """TEST-ID ACCT-USERNAME-003: case variants collide on the canonical DB identity."""
    first = User.objects.create_user(username="Example_User", password="not-a-real-secret-123")
    assert first.username == "example_user"

    with pytest.raises(IntegrityError):
        User.objects.create_user(username=" example_USER ", password="not-a-real-secret-456")


def test_password_is_stored_as_a_one_way_hash() -> None:
    """TEST-ID ACCT-PASSWORD-001: the raw password is never persisted."""
    raw_password = "not-a-real-secret-789"
    user = User.objects.create_user(username="password_user", password=raw_password)

    assert user.password != raw_password
    assert raw_password not in user.password
    assert user.check_password(raw_password)



def test_profile_service_boundary_excludes_identity_and_authority_fields() -> None:
    """TEST-ID ACCT-PROFILE-001: self-service profile input cannot mutate authority fields."""
    assert PROFILE_MUTABLE_FIELDS == {"bio"}
    assert {"id", "username", "auth_epoch", "is_staff", "is_superuser"} <= IDENTITY_IMMUTABLE_FIELDS
    assert PROFILE_MUTABLE_FIELDS.isdisjoint(IDENTITY_IMMUTABLE_FIELDS)


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies")
def test_pol_status_001_http_boundary_uses_moderation_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    """TEST-ID POL-STATUS-001-HTTP-001: dormant HTTP sessions flush and fail generically."""

    class EffectiveUserStatus(StrEnum):
        ACTIVE = "active"
        DORMANT = "dormant"

    moderation_services = ModuleType("apps.moderation.services")
    moderation_services.EffectiveUserStatus = EffectiveUserStatus
    moderation_services.effective_user_status = lambda *, user_id: EffectiveUserStatus.DORMANT
    monkeypatch.setitem(sys.modules, "apps.moderation.services", moderation_services)

    user = User.objects.create_user(username="status_user", password="not-a-real-secret-123")
    request = RequestFactory().get("/account")
    SessionMiddleware(lambda incoming: None).process_request(request)
    request.session["authenticated"] = True
    request.user = user

    response = enforce_http_user_status(request)

    assert response is not None
    assert response.status_code == 403
    assert response.content == b"Account unavailable."
    assert not request.user.is_authenticated
    assert request.session.is_empty()
