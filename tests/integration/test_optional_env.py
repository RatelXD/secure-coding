from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPLICIT_ENV_KEYS = {
    "APP_ENV",
    "DJANGO_DEBUG",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "DJANGO_TRUST_PROXY_HEADERS",
    "DJANGO_TRUSTED_PROXY_IPS",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_SSLMODE",
    "REDIS_URL",
}
TEST_OVERLAY_ENV_KEYS = {"TEST_DB_PASSWORD", "TEST_DB_PORT", "TEST_REDIS_PORT"}



class OptionalDotEnvRegressionTests(unittest.TestCase):
    def test_compose_resolves_safe_development_defaults_without_dotenv(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker Compose is unavailable")

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            compose_copy = temporary_root / "compose.yaml"
            compose_copy.write_bytes((REPOSITORY_ROOT / "compose.yaml").read_bytes())
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in EXPLICIT_ENV_KEYS and key != "COMPOSE_FILE"
            }
            result = subprocess.run(
                [
                    docker,
                    "compose",
                    "--project-directory",
                    temporary_directory,
                    "-f",
                    str(compose_copy),
                    "config",
                    "--format",
                    "json",
                ],
                cwd=temporary_directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

        config = json.loads(result.stdout)
        app_environment = config["services"]["app"]["environment"]
        app_volumes = config["services"]["app"]["volumes"]
        database_environment = config["services"]["db"]["environment"]
        self.assertEqual(app_environment["APP_ENV"], "development")
        self.assertEqual(app_environment["POSTGRES_HOST"], "db")
        self.assertEqual(app_environment["REDIS_URL"], "redis://redis:6379/0")
        self.assertEqual(database_environment["POSTGRES_DB"], "marketplace")
        self.assertTrue(database_environment["POSTGRES_PASSWORD"])
        self.assertTrue(
            any(
                volume["source"] == "media-data"
                and volume["target"] == "/app/media"
                and volume["type"] == "volume"
                for volume in app_volumes
            )
        )

    def test_runtime_image_prepares_writable_media_directory(self) -> None:
        dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("install -d -m 0750 -o app -g app /app/media", dockerfile)

    def test_test_overlay_exposes_dependencies_on_loopback_without_dotenv(self) -> None:
        docker = shutil.which("docker")
        if docker is None:
            self.skipTest("Docker Compose is unavailable")

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            compose_copy = temporary_root / "compose.yaml"
            overlay_copy = temporary_root / "compose.test.yaml"
            compose_copy.write_bytes((REPOSITORY_ROOT / "compose.yaml").read_bytes())
            overlay_copy.write_bytes((REPOSITORY_ROOT / "compose.test.yaml").read_bytes())
            environment = {
                key: value
                for key, value in os.environ.items()
                if key not in EXPLICIT_ENV_KEYS
                and key not in TEST_OVERLAY_ENV_KEYS
                and key != "COMPOSE_FILE"
            }
            compose_command = [
                docker,
                "compose",
                "--project-directory",
                temporary_directory,
                "-p",
                "secure-coding-test",
                "-f",
                str(compose_copy),
                "-f",
                str(overlay_copy),
                "config",
                "--format",
                "json",
            ]
            result = subprocess.run(
                compose_command,
                cwd=temporary_directory,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            custom_environment = environment | {
                "TEST_DB_PASSWORD": "custom-local-test-password",
                "TEST_DB_PORT": "55433",
                "TEST_REDIS_PORT": "56380",
            }
            custom_result = subprocess.run(
                compose_command,
                cwd=temporary_directory,
                env=custom_environment,
                check=True,
                capture_output=True,
                text=True,
            )

        config = json.loads(result.stdout)
        database = config["services"]["db"]
        redis = config["services"]["redis"]
        self.assertEqual(database["environment"]["POSTGRES_DB"], "marketplace")
        self.assertEqual(database["environment"]["POSTGRES_USER"], "marketplace")
        self.assertEqual(database["ports"], [
            {
                "mode": "ingress",
                "host_ip": "127.0.0.1",
                "target": 5432,
                "published": "55432",
                "protocol": "tcp",
            }
        ])
        self.assertEqual(redis["ports"], [
            {
                "mode": "ingress",
                "host_ip": "127.0.0.1",
                "target": 6379,
                "published": "56379",
                "protocol": "tcp",
            }
        ])
        self.assertEqual(config["volumes"]["postgres-data"]["name"], "secure-coding-test_postgres-data")
        custom_config = json.loads(custom_result.stdout)
        custom_database = custom_config["services"]["db"]
        custom_redis = custom_config["services"]["redis"]
        self.assertEqual(
            custom_database["environment"]["POSTGRES_PASSWORD"],
            "custom-local-test-password",
        )
        self.assertEqual(custom_database["ports"][0]["host_ip"], "127.0.0.1")
        self.assertEqual(custom_database["ports"][0]["published"], "55433")
        self.assertEqual(custom_redis["ports"][0]["host_ip"], "127.0.0.1")
        self.assertEqual(custom_redis["ports"][0]["published"], "56380")
        self.assertEqual(
            custom_config["volumes"]["postgres-data"]["name"],
            "secure-coding-test_postgres-data",
        )

    def test_development_routes_static_assets_without_dotenv(self) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in EXPLICIT_ENV_KEYS
        }
        environment.update(
            {
                "APP_ENV": "development",
                "DJANGO_DEBUG": "true",
                "PYTHONPATH": str(REPOSITORY_ROOT / "src"),
                "POSTGRES_DB": "marketplace",
                "POSTGRES_USER": "marketplace",
                "POSTGRES_PASSWORD": "development-only-database-password",
                "POSTGRES_HOST": "db",
                "POSTGRES_PORT": "5432",
                "POSTGRES_SSLMODE": "disable",
                "REDIS_URL": "redis://redis:6379/0",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import django; django.setup(); "
                    "from django.urls import resolve; "
                    "print(resolve('/static/chat/chat.js').url_name)"
                ),
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_settings_still_reject_missing_explicit_values(self) -> None:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in EXPLICIT_ENV_KEYS
        }
        environment.update(
            {
                "APP_ENV": "production",
                "PYTHONPATH": str(REPOSITORY_ROOT / "src"),
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY is required", result.stderr)
