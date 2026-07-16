from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_NAMES = {
    "APP_ENV",
    "DJANGO_DEBUG",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_SSLMODE",
    "REDIS_URL",
}


def _clean_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in _CONFIG_NAMES}


def test_compose_resolves_local_defaults_without_env_file() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker is required for Compose configuration verification")

    result = subprocess.run(
        ["docker", "compose", "--env-file", "/dev/null", "config", "--format", "json"],
        cwd=REPOSITORY_ROOT,
        env=_clean_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    environment = json.loads(result.stdout)["services"]["app"]["environment"]
    assert environment["APP_ENV"] == "development"
    assert environment["DJANGO_DEBUG"] == "true"
    assert environment["POSTGRES_HOST"] == "db"
    assert environment["POSTGRES_SSLMODE"] == "disable"
    assert environment["REDIS_URL"] == "redis://redis:6379/0"


def test_compose_defaults_load_django_settings_without_env_file() -> None:
    env = _clean_environment()
    env.update(
        {
            "APP_ENV": "development",
            "DJANGO_DEBUG": "true",
            "DJANGO_SECRET_KEY": "development-only-change-me-before-any-shared-deployment-000000",
            "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "http://localhost:8000",
            "POSTGRES_DB": "marketplace",
            "POSTGRES_USER": "marketplace",
            "POSTGRES_PASSWORD": "development-only-database-password",
            "POSTGRES_HOST": "db",
            "POSTGRES_PORT": "5432",
            "POSTGRES_SSLMODE": "disable",
            "REDIS_URL": "redis://redis:6379/0",
            "PYTHONPATH": "src",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup(); print('startup-ok')"],
        cwd=REPOSITORY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "startup-ok"


def test_database_options_bound_readiness_failure_time() -> None:
    env = _clean_environment()
    env.update(
        {
            "APP_ENV": "development",
            "DJANGO_DEBUG": "true",
            "DJANGO_SECRET_KEY": "development-only-change-me-before-any-shared-deployment-000000",
            "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "http://localhost:8000",
            "POSTGRES_DB": "marketplace",
            "POSTGRES_USER": "marketplace",
            "POSTGRES_PASSWORD": "development-only-database-password",
            "POSTGRES_HOST": "db",
            "POSTGRES_PORT": "5432",
            "POSTGRES_SSLMODE": "disable",
            "REDIS_URL": "redis://redis:6379/0",
            "PYTHONPATH": "src",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; import django; django.setup(); "
                "from django.conf import settings; "
                "print(json.dumps(settings.DATABASES['default']['OPTIONS']))"
            ),
        ],
        cwd=REPOSITORY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    options = json.loads(result.stdout)
    assert options["connect_timeout"] == 2
    assert options["tcp_user_timeout"] == 2_000


def test_database_address_resolution_is_bounded_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def resolve(*args: object, **kwargs: object) -> SimpleNamespace:
        observed["args"] = args
        observed["kwargs"] = kwargs
        return SimpleNamespace(
            stdout=(
                "192.0.2.10 STREAM db\n"
                "192.0.2.10 DGRAM db\n"
                "192.0.2.11 STREAM db\n"
            )
        )

    monkeypatch.setattr("config.health.run", resolve)

    from config.health import _database_addresses

    assert _database_addresses("db") == ("192.0.2.10", "192.0.2.11")
    assert observed["args"] == (["getent", "ahosts", "db"],)
    assert observed["kwargs"] == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 0.25,
    }


def test_database_probe_tries_all_resolved_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_addresses: list[str] = []

    class Cursor:
        async def __aenter__(self) -> "Cursor":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, _query: str) -> None:
            return None

        async def fetchone(self) -> tuple[int]:
            return (1,)

    class Connection:
        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def cursor(self) -> Cursor:
            return Cursor()

    class Driver:
        @classmethod
        async def connect(cls, **kwargs: object) -> Connection:
            host_address = str(kwargs["hostaddr"])
            attempted_addresses.append(host_address)
            if host_address == "192.0.2.10":
                raise OSError("first address unavailable")
            return Connection()

    monkeypatch.setattr(
        "config.health._database_addresses",
        lambda _host: ("192.0.2.10", "192.0.2.11"),
    )
    monkeypatch.setattr("config.health.AsyncConnection", Driver)

    from config.health import _database_ready

    database = {
        "NAME": "marketplace",
        "USER": "marketplace",
        "PASSWORD": "local-test-password",
        "HOST": "db",
        "PORT": "5432",
        "OPTIONS": {},
    }

    assert asyncio.run(_database_ready(database))
    assert attempted_addresses == ["192.0.2.10", "192.0.2.11"]


def test_readiness_returns_503_when_database_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(_database: object) -> bool:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("config.health._database_ready", unavailable)

    from config.health import readiness
    from django.test import RequestFactory

    response = readiness(RequestFactory().get("/readyz/"))

    assert response.status_code == 503
    assert json.loads(response.content) == {
        "status": "unavailable",
        "database": "unavailable",
    }


def test_readiness_returns_200_for_successful_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def available(_database: object) -> bool:
        return True

    monkeypatch.setattr("config.health._database_ready", available)

    from config.health import readiness
    from django.test import RequestFactory

    response = readiness(RequestFactory().get("/readyz/"))

    assert response.status_code == 200
    assert json.loads(response.content) == {
        "status": "ready",
        "database": "ok",
        "redis": "non-authoritative",
    }


def test_readiness_bounds_complete_database_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def stalled(_database: object) -> bool:
        await asyncio.sleep(0.1)
        return True

    monkeypatch.setattr("config.health._database_ready", stalled)
    monkeypatch.setattr("config.health._READINESS_TIMEOUT_SECONDS", 0.01)

    from config.health import readiness
    from django.test import RequestFactory

    started_at = time.monotonic()
    response = readiness(RequestFactory().get("/readyz/"))
    elapsed = time.monotonic() - started_at

    assert response.status_code == 503
    assert elapsed < 0.1


def test_production_without_explicit_environment_fails_closed() -> None:
    env = _clean_environment()
    env.update({"APP_ENV": "production", "PYTHONPATH": "src"})
    result = subprocess.run(
        [sys.executable, "-c", "from config import settings"],
        cwd=REPOSITORY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is required" in result.stderr
