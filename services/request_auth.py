from __future__ import annotations

import hmac
import logging
import os
from typing import Optional

from fastapi import HTTPException

from services.miniprogram_auth import MiniProgramAuthError, parse_bearer_token, verify_miniprogram_token


def _allow_insecure_doctor_id_fallback(flag_name: str) -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return (os.environ.get(flag_name) or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_doctor_id_from_auth_or_fallback(
    candidate_doctor_id: Optional[str],
    authorization: Optional[str],
    *,
    fallback_env_flag: str,
    default_doctor_id: str = "test_doctor",
) -> str:
    header = authorization if isinstance(authorization, str) else None
    if header and header.strip():
        try:
            token = parse_bearer_token(header)
            principal = verify_miniprogram_token(token)
            return principal.doctor_id
        except MiniProgramAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc))

    if _allow_insecure_doctor_id_fallback(fallback_env_flag):
        resolved = (candidate_doctor_id or "").strip() or default_doctor_id
        logging.getLogger("auth").warning(
            "[Auth] insecure doctor_id fallback used flag=%s resolved_doctor_id=%s",
            fallback_env_flag,
            resolved,
        )
        return resolved

    raise HTTPException(status_code=401, detail="Missing Authorization header")


def require_admin_token(
    provided_token: Optional[str],
    *,
    env_name: str = "UI_ADMIN_TOKEN",
) -> None:
    """Require a static admin token for sensitive non-doctor-scoped endpoints."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    expected = (os.environ.get(env_name) or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="{0} is not configured".format(env_name))

    candidate = (provided_token or "").strip()
    if not candidate or not hmac.compare_digest(candidate, expected):
        raise HTTPException(status_code=403, detail="Forbidden")
