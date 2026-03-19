"""Shared FastAPI dependencies for web channel endpoints."""
from __future__ import annotations

from fastapi import Header
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback


async def get_doctor_id(
    doctor_id: str = "",
    authorization: str | None = Header(default=None),
) -> str:
    """Resolve doctor ID from JWT or body field. Use as ``Depends(get_doctor_id)``."""
    return resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )


def rate_limit(scope: str):
    """Return a dependency that enforces rate limiting for the given scope."""
    async def _check(doctor_id: str = "") -> None:
        enforce_doctor_rate_limit(doctor_id, scope=scope)
    return _check
