from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import LoginThrottle, User
from apps.accounts.services import account_login_identifier, client_ip_identifier

pytestmark = pytest.mark.django_db


def create_user(username: str = "test_user", password: str = "Correct-Horse-987!") -> User:
    return User.objects.create_user(username=username, password=password)


def force_login_with_epoch(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def test_signup_canonicalizes_username_and_uses_password_hash() -> None:
    client = Client()
    raw_password = "Correct-Horse-987!"

    response = client.post(
        reverse("accounts:signup"),
        {"username": "  New_User  ", "password1": raw_password, "password2": raw_password},
    )

    user = User.objects.get(username="new_user")
    assert response.status_code == 302
    assert response.url == reverse("accounts:profile")
    assert user.password != raw_password
    assert user.check_password(raw_password)
    assert client.session.get("_auth_user_id") == str(user.pk)


@pytest.mark.parametrize(
    "password",
    ["short-pass", "x" * 129, "safe-password\x00suffix"],
)
def test_signup_rejects_password_policy_boundaries(password: str) -> None:
    response = Client().post(
        reverse("accounts:signup"),
        {"username": "new_user", "password1": password, "password2": password},
    )

    assert response.status_code == 200
    assert not User.objects.filter(username="new_user").exists()


def test_login_failure_is_generic_for_known_and_unknown_accounts() -> None:
    create_user()
    client = Client()

    known = client.post(
        reverse("accounts:login"),
        {"username": "test_user", "password": "wrong-password"},
    )
    unknown = client.post(
        reverse("accounts:login"),
        {"username": "missing_user", "password": "wrong-password"},
    )

    expected = "아이디 또는 비밀번호를 확인해 주세요. 잠시 후 다시 시도할 수 있습니다."
    assert known.status_code == unknown.status_code == 200
    assert expected in known.content.decode()
    assert expected in unknown.content.decode()


def test_fifth_account_failure_blocks_correct_password() -> None:
    password = "Correct-Horse-987!"
    create_user(password=password)
    client = Client(REMOTE_ADDR="192.0.2.10")

    for _ in range(5):
        response = client.post(
            reverse("accounts:login"),
            {"username": "test_user", "password": "wrong-password"},
        )
        assert response.status_code == 200

    blocked = client.post(
        reverse("accounts:login"),
        {"username": "test_user", "password": password},
    )
    throttle = LoginThrottle.objects.get(
        scope=LoginThrottle.Scope.ACCOUNT,
        identifier_digest=account_login_identifier("test_user"),
    )
    assert blocked.status_code == 200
    assert "_auth_user_id" not in client.session
    assert throttle.failure_count == 5
    assert throttle.blocked_until is not None
    assert throttle.blocked_until > timezone.now()


def test_twentieth_ip_failure_sets_thirty_minute_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.accounts.services.authenticate", lambda **kwargs: None)
    client = Client(REMOTE_ADDR="203.0.113.30")

    for number in range(20):
        response = client.post(
            reverse("accounts:login"),
            {"username": f"unknown_{number}", "password": "wrong-password-value"},
        )
        assert response.status_code == 200

    request = client.get(reverse("accounts:login")).wsgi_request
    throttle = LoginThrottle.objects.get(
        scope=LoginThrottle.Scope.IP,
        identifier_digest=client_ip_identifier(request),
    )
    assert throttle.failure_count == 20
    assert throttle.blocked_until is not None
    remaining = throttle.blocked_until - timezone.now()
    assert timedelta(minutes=29) < remaining <= timedelta(minutes=30)
    row_count_at_block = LoginThrottle.objects.count()
    for number in range(20, 30):
        response = client.post(
            reverse("accounts:login"),
            {"username": f"unknown_{number}", "password": "wrong-password-value"},
        )
        assert response.status_code == 200
    assert LoginThrottle.objects.count() == row_count_at_block


@pytest.mark.parametrize("username,password", [("bad\x00name", "wrong-password-value"), ("test_user", "bad\x00password")])
def test_login_rejects_nul_input_with_generic_response(username: str, password: str) -> None:
    response = Client().post(
        reverse("accounts:login"),
        {"username": username, "password": password},
    )

    assert response.status_code == 200
    assert "아이디 또는 비밀번호를 확인해 주세요." in response.content.decode()


def test_success_resets_account_failures_but_not_ip_failures() -> None:
    password = "Correct-Horse-987!"
    create_user(password=password)
    client = Client(REMOTE_ADDR="198.51.100.20")

    client.post(
        reverse("accounts:login"),
        {"username": "test_user", "password": "wrong-password"},
    )
    request = client.get(reverse("accounts:login")).wsgi_request
    ip_digest = client_ip_identifier(request)
    response = client.post(
        reverse("accounts:login"),
        {"username": "test_user", "password": password},
    )

    account = LoginThrottle.objects.get(
        scope=LoginThrottle.Scope.ACCOUNT,
        identifier_digest=account_login_identifier("test_user"),
    )
    ip = LoginThrottle.objects.get(
        scope=LoginThrottle.Scope.IP,
        identifier_digest=ip_digest,
    )
    assert response.status_code == 302
    assert account.failure_count == 0
    assert ip.failure_count == 1
    assert "198.51.100.20" not in ip.identifier_digest


def test_expired_account_cooldown_starts_a_new_window() -> None:
    password = "Correct-Horse-987!"
    create_user(password=password)
    client = Client()
    digest = account_login_identifier("test_user")
    LoginThrottle.objects.create(
        scope=LoginThrottle.Scope.ACCOUNT,
        identifier_digest=digest,
        window_started_at=timezone.now() - timedelta(minutes=31),
        failure_count=5,
        blocked_until=timezone.now() - timedelta(seconds=1),
    )

    response = client.post(
        reverse("accounts:login"),
        {"username": "test_user", "password": password},
    )

    assert response.status_code == 302
    throttle = LoginThrottle.objects.get(identifier_digest=digest)
    assert throttle.failure_count == 0
    assert throttle.blocked_until is None


def test_login_requires_csrf_and_logout_requires_post() -> None:
    csrf_client = Client(enforce_csrf_checks=True)
    assert csrf_client.post(
        reverse("accounts:login"),
        {"username": "test_user", "password": "not-a-secret"},
    ).status_code == 403
    assert Client().get(reverse("accounts:logout")).status_code == 405


def test_public_profile_allowlist_escapes_bio_and_excludes_sensitive_fields() -> None:
    user = create_user()
    user.email = "private@example.test"
    user.bio = '<script>alert("x")</script>'
    user.save(update_fields=("email", "bio"))

    response = Client().get(reverse("accounts:user_detail", args=[user.username]))
    content = response.content.decode()

    assert response.status_code == 200
    assert "private@example.test" not in content
    assert user.password not in content
    assert "auth_epoch" not in content
    assert "&lt;script&gt;" in content
    assert '<script>alert("x")</script>' not in content


def test_bio_edit_updates_only_authenticated_actor() -> None:
    actor = create_user("actor_user")
    other = create_user("other_user")
    client = Client()
    force_login_with_epoch(client, actor)

    response = client.post(
        reverse("accounts:bio_edit"),
        {"bio": "내 소개", "username": other.username, "is_staff": "true"},
    )

    actor.refresh_from_db()
    other.refresh_from_db()
    assert response.status_code == 302
    assert actor.bio == "내 소개"
    assert not actor.is_staff
    assert other.bio == ""


def test_password_change_rotates_password_without_ending_session() -> None:
    actor = create_user()
    client = Client()
    force_login_with_epoch(client, actor)
    new_password = "Another-Horse-654!"

    response = client.post(
        reverse("accounts:password_change"),
        {
            "old_password": "Correct-Horse-987!",
            "new_password1": new_password,
            "new_password2": new_password,
        },
    )

    actor.refresh_from_db()
    assert response.status_code == 302
    assert actor.check_password(new_password)
    assert client.session.get("_auth_user_id") == str(actor.pk)


def test_auth_epoch_change_flushes_existing_session() -> None:
    actor = create_user()
    client = Client()
    force_login_with_epoch(client, actor)
    session = client.session
    session["account_auth_epoch"] = actor.auth_epoch
    session.save()
    User.objects.filter(pk=actor.pk).update(auth_epoch=actor.auth_epoch + 1)

    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 403
    assert response.content == b"Account unavailable."
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("session_epoch", [None, "0", True])
def test_missing_or_malformed_auth_epoch_flushes_session(session_epoch: object) -> None:
    actor = create_user()
    client = Client()
    client.force_login(actor)
    if session_epoch is not None:
        session = client.session
        session["account_auth_epoch"] = session_epoch
        session.save()

    response = client.get(reverse("accounts:profile"))

    assert response.status_code == 403
    assert response.content == b"Account unavailable."
    assert "_auth_user_id" not in client.session
