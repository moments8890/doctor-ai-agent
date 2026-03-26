"""
请求身份验证，失败关闭模式，可选降级标志。

Uses the unified JWT system for all doctor token verification.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Optional

from fastapi import HTTPException

from infra.auth import is_production
from infra.auth.unified import extract_token, verify_token


def _allow_insecure_doctor_id_fallback(flag_name: str) -> bool:
    if is_production():
        return False  # hard-disabled in production regardless of any flag
    return True  # always allow in dev/test — per-flag opt-in not needed


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
            token = extract_token(header)
            payload = verify_token(token)
            doctor_id = payload.get("doctor_id") or payload.get("sub") or ""
            if not doctor_id:
                raise HTTPException(status_code=401, detail="Token missing doctor_id")
            return str(doctor_id)
        except HTTPException as exc:
            if is_production():
                raise
            # non-production: JWT present but failed — log the reason
            logging.getLogger("auth").warning(
                "[Auth] JWT present but verification failed (dev): %s — falling back to candidate_doctor_id=%s",
                exc.detail, candidate_doctor_id,
            )

    if _allow_insecure_doctor_id_fallback(fallback_env_flag):
        resolved = (candidate_doctor_id or "").strip() or default_doctor_id
        logging.getLogger("auth").debug(
            "[Auth] dev fallback doctor_id=%s (flag=%s)",
            resolved,
            fallback_env_flag,
        )
        return resolved

    raise HTTPException(status_code=401, detail="Missing Authorization header")


def require_admin_token(
    provided_token: Optional[str],
    *,
    env_name: str = "UI_ADMIN_TOKEN",
) -> None:
    """Require a static admin token for sensitive non-doctor-scoped endpoints."""
    if not is_production():
        return

    expected = (os.environ.get(env_name) or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="{0} is not configured".format(env_name))

    candidate = (provided_token or "").strip()
    if not candidate or not hmac.compare_digest(candidate, expected):
        raise HTTPException(status_code=403, detail="Forbidden")
