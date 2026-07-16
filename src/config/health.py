"""Minimal orchestration probes with explicit dependency semantics."""

import asyncio
from collections.abc import Mapping
from ipaddress import ip_address
from subprocess import run
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe
from psycopg import AsyncConnection


@require_safe
def liveness(_request: HttpRequest) -> JsonResponse:
    """Report process responsiveness without consulting external services."""
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response


_READINESS_TIMEOUT_SECONDS = 1.5
_RESOLUTION_TIMEOUT_SECONDS = 0.25


def _database_addresses(host: str) -> tuple[str, ...]:
    try:
        return (str(ip_address(host)),)
    except ValueError:
        result = run(
            ["getent", "ahosts", host],
            check=True,
            capture_output=True,
            text=True,
            timeout=_RESOLUTION_TIMEOUT_SECONDS,
        )
        addresses = tuple(
            dict.fromkeys(
                str(ip_address(line.split()[0]))
                for line in result.stdout.splitlines()
                if line.split()
            )
        )
        if not addresses:
            raise ConnectionError("PostgreSQL hostname did not resolve")
        return addresses



async def _database_ready(database: Mapping[str, Any]) -> bool:
    options = dict(database.get("OPTIONS", {}))
    host = str(database["HOST"])
    for host_address in _database_addresses(host):
        try:
            async with await AsyncConnection.connect(
                dbname=database["NAME"],
                user=database["USER"],
                password=database["PASSWORD"],
                host=host,
                hostaddr=host_address,
                port=database["PORT"],
                **options,
            ) as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    if await cursor.fetchone() == (1,):
                        return True
        except Exception:
            continue
    return False


@require_safe
def readiness(_request: HttpRequest) -> JsonResponse:
    """Require PostgreSQL, the persistent authority; Redis may degrade fan-out."""
    database = settings.DATABASES["default"]
    try:
        ready = asyncio.run(
            asyncio.wait_for(
                _database_ready(database),
                timeout=_READINESS_TIMEOUT_SECONDS,
            )
        )
        if not ready:
            raise ConnectionError("PostgreSQL readiness query returned an unexpected result")
    except Exception:
        response = JsonResponse(
            {"status": "unavailable", "database": "unavailable"}, status=503
        )
    else:
        response = JsonResponse(
            {"status": "ready", "database": "ok", "redis": "non-authoritative"}
        )
    response["Cache-Control"] = "no-store"
    return response
