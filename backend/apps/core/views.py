"""Operational endpoints.

Plain Django views rather than DRF ones: health must answer even when auth,
serializers or the JWT layer are broken — those are exactly the moments you
need it.
"""

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger("ft.core")


def _check_database() -> tuple[bool, str | None]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - health must report, not raise
        return False, str(exc)
    return True, None


def _check_redis() -> tuple[bool, str | None]:
    try:
        cache.set("health:ping", "1", timeout=5)
        if cache.get("health:ping") != "1":
            return False, "value did not round-trip"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, None


def health(request) -> JsonResponse:
    checks = {}
    for name, check in (("database", _check_database), ("redis", _check_redis)):
        ok, error = check()
        checks[name] = {"ok": ok}
        if error:
            checks[name]["error"] = error

    healthy = all(c["ok"] for c in checks.values())
    if not healthy:
        logger.error("health check failed", extra={"checks": checks})

    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )
