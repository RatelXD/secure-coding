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
        database_environment = config["services"]["db"]["environment"]
        self.assertEqual(app_environment["APP_ENV"], "development")
        self.assertEqual(app_environment["POSTGRES_HOST"], "db")
        self.assertEqual(app_environment["REDIS_URL"], "redis://redis:6379/0")
        self.assertEqual(database_environment["POSTGRES_DB"], "marketplace")
        self.assertTrue(database_environment["POSTGRES_PASSWORD"])

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
