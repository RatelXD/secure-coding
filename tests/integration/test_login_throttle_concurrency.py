from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import close_old_connections, connections
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.models import LoginThrottle
from apps.accounts.services import account_login_identifier, authenticate_login, client_ip_identifier

pytestmark = pytest.mark.django_db(transaction=True)


def _failed_login(*, username: str, remote_addr: str, barrier: Barrier) -> None:
    close_old_connections()
    try:
        request = RequestFactory().post("/login/", REMOTE_ADDR=remote_addr)
        barrier.wait(timeout=10)
        assert (
            authenticate_login(
                request=request,
                username=username,
                password="wrong-password-value",
            )
            is None
        )
    finally:
        connections.close_all()


def test_concurrent_failures_reach_account_threshold_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.accounts.services.authenticate", lambda **kwargs: None)
    attempts = 5
    barrier = Barrier(attempts)

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        futures = [
            executor.submit(
                _failed_login,
                username="shared_user",
                remote_addr=f"192.0.2.{number + 1}",
                barrier=barrier,
            )
            for number in range(attempts)
        ]
        for future in futures:
            future.result(timeout=20)

    throttle = LoginThrottle.objects.get(
        scope=LoginThrottle.Scope.ACCOUNT,
        identifier_digest=account_login_identifier("shared_user"),
    )
    assert throttle.failure_count == attempts
    assert throttle.blocked_until is not None
    assert throttle.blocked_until > timezone.now()


def test_concurrent_failures_are_serialized_per_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.accounts.services.authenticate", lambda **kwargs: None)
    attempts = 10
    barrier = Barrier(attempts)
    remote_addr = "198.51.100.77"

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        futures = [
            executor.submit(
                _failed_login,
                username=f"parallel_{number}",
                remote_addr=remote_addr,
                barrier=barrier,
            )
            for number in range(attempts)
        ]
        for future in futures:
            future.result(timeout=20)

    request = RequestFactory().get("/login/", REMOTE_ADDR=remote_addr)
    throttle = LoginThrottle.objects.get(
        scope=LoginThrottle.Scope.IP,
        identifier_digest=client_ip_identifier(request),
    )
    assert throttle.failure_count == attempts
    assert throttle.blocked_until is None
