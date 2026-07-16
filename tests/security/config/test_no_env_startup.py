from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

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
