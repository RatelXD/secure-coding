"""Minimal orchestration probes with explicit dependency semantics."""

from django.db import connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def liveness(_request: HttpRequest) -> JsonResponse:
    """Report process responsiveness without consulting external services."""
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
def readiness(_request: HttpRequest) -> JsonResponse:
    """Require PostgreSQL, the persistent authority; Redis may degrade fan-out."""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
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
