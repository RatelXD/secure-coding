from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

import pytest
from django.test import RequestFactory, override_settings

from config.middleware import TrustedProxyHeadersMiddleware


def _load_production_settings(overrides: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "production",
            "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": "production-test-secret-key-that-is-longer-than-fifty-characters-0001",
            "DJANGO_ALLOWED_HOSTS": "market.example",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://market.example",
            "DJANGO_TRUST_PROXY_HEADERS": "false",
            "DJANGO_TRUSTED_PROXY_IPS": "",
            "POSTGRES_DB": "marketplace",
            "POSTGRES_USER": "marketplace",
            "POSTGRES_PASSWORD": "not-a-real-database-secret",
            "POSTGRES_HOST": "db",
            "POSTGRES_SSLMODE": "require",
            "REDIS_URL": "rediss://redis.example:6379/0",
            "PYTHONPATH": "src",
        }
    )
    env.update(overrides or {})
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from config import settings; "
            "print(settings.USE_X_FORWARDED_HOST); "
            "print(','.join(sorted(settings.TRUSTED_PROXY_IPS)))",
        ],
        check=False,
        capture_output=True,
        cwd=os.fspath(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))),
        env=env,
        text=True,
    )


def test_production_requires_explicit_https_csrf_origin() -> None:
    result = _load_production_settings({"DJANGO_CSRF_TRUSTED_ORIGINS": ""})

    assert result.returncode != 0
    assert "production requires explicit DJANGO_CSRF_TRUSTED_ORIGINS" in result.stderr


def test_production_rejects_postgresql_tls_downgrade() -> None:
    for sslmode in ("disable", "allow", "prefer"):
        result = _load_production_settings({"POSTGRES_SSLMODE": sslmode})

        assert result.returncode != 0
        assert "production POSTGRES_SSLMODE must require TLS" in result.stderr



def test_proxy_trust_requires_explicit_ip_literals() -> None:
    missing = _load_production_settings({"DJANGO_TRUST_PROXY_HEADERS": "true"})
    invalid = _load_production_settings(
        {
            "DJANGO_TRUST_PROXY_HEADERS": "true",
            "DJANGO_TRUSTED_PROXY_IPS": "proxy.internal",
        }
    )

    assert missing.returncode != 0
    assert "DJANGO_TRUSTED_PROXY_IPS is required" in missing.stderr
    assert invalid.returncode != 0
    assert "DJANGO_TRUSTED_PROXY_IPS must contain IP literals" in invalid.stderr


def test_production_never_trusts_forwarded_host() -> None:
    result = _load_production_settings(
        {
            "DJANGO_TRUST_PROXY_HEADERS": "true",
            "DJANGO_TRUSTED_PROXY_IPS": "127.0.0.1,2001:0db8::1",
        }
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["False", "127.0.0.1,2001:db8::1"]


@override_settings(
    TRUST_PROXY_HEADERS=True,
    TRUSTED_PROXY_IPS=frozenset({"127.0.0.1"}),
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
)
def test_trusted_proxy_accepts_only_single_https_assertion() -> None:
    request = RequestFactory().get(
        "/readyz/",
        REMOTE_ADDR="127.0.0.1",
        HTTP_X_FORWARDED_PROTO="https",
        HTTP_X_FORWARDED_FOR="198.51.100.10",
        HTTP_X_FORWARDED_HOST="attacker.example",
    )
    response = TrustedProxyHeadersMiddleware(lambda incoming: incoming)(request)

    assert response is request
    assert request.is_secure()
    assert "HTTP_X_FORWARDED_FOR" not in request.META
    assert "HTTP_X_FORWARDED_HOST" not in request.META


@pytest.mark.parametrize(
    ("remote_addr", "forwarded_proto"),
    [
        ("198.51.100.10", "https"),
        ("127.0.0.1", "http"),
        ("127.0.0.1", "https,http"),
        ("not-an-ip", "https"),
    ],
)
@override_settings(
    TRUST_PROXY_HEADERS=True,
    TRUSTED_PROXY_IPS=frozenset({"127.0.0.1"}),
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
)
def test_untrusted_proxy_assertions_are_rejected(remote_addr: str, forwarded_proto: str) -> None:
    request = RequestFactory().get(
        "/readyz/",
        REMOTE_ADDR=remote_addr,
        HTTP_X_FORWARDED_PROTO=forwarded_proto,
    )
    response = TrustedProxyHeadersMiddleware(lambda incoming: incoming)(request)

    assert response.status_code == 400
    assert response.content == b"Invalid proxy headers."
