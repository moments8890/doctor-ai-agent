"""Auth / session dependency helpers for the doctor dashboard."""

from __future__ import annotations

import hmac
import os
from typing import Literal

from fastapi import Header, HTTPException

from infra.auth import is_production
from infra.auth.request_auth import require_admin_token, resolve_doctor_id_from_auth_or_fallback


# Role returned by the role-aware admin dependencies.
AdminRole = Literal["super", "viewer"]


def _resolve_ui_doctor_id(candidate_doctor_id: str | None, authorization: str | None) -> str:
    return resolve_doctor_id_from_auth_or_fallback(
        candidate_doctor_id,
        authorization,
        fallback_env_flag="UI_ALLOW_QUERY_DOCTOR_ID",
        default_doctor_id="web_doctor",
    )


def _require_ui_admin_access(x_admin_token: str | None) -> None:
    require_admin_token(x_admin_token, env_name="UI_ADMIN_TOKEN")


def _require_ui_debug_access(x_debug_token: str | None) -> None:
    require_admin_token(x_debug_token, env_name="UI_DEBUG_TOKEN")


# ---------------------------------------------------------------------------
# Role-aware admin auth (Task 4.1 — viewer role)
# ---------------------------------------------------------------------------

def _resolve_admin_role(provided_token: str | None) -> AdminRole:
    """Return "super" or "viewer" for a valid admin token, else raise 401.

    Token resolution rules (checked in order):
      1. Matches ``UI_ADMIN_TOKEN`` env → "super".
      2. Matches ``UI_ADMIN_VIEWER_TOKEN`` env → "viewer".
      3. In non-production, the literal ``"dev"`` → "super".
      4. Otherwise raise HTTP 401.

    Unlike :func:`require_admin_token`, this check runs in **all** environments
    so that role-gated routes behave the same in dev tests as in prod.
    """
    candidate = (provided_token or "").strip()
    if not candidate:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Token")

    super_token = (os.environ.get("UI_ADMIN_TOKEN") or "").strip()
    viewer_token = (os.environ.get("UI_ADMIN_VIEWER_TOKEN") or "").strip()

    if super_token and hmac.compare_digest(candidate, super_token):
        return "super"
    if viewer_token and hmac.compare_digest(candidate, viewer_token):
        return "viewer"
    if not is_production() and hmac.compare_digest(candidate, "dev"):
        return "super"

    raise HTTPException(status_code=401, detail="Invalid X-Admin-Token")


def require_admin_role(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> AdminRole:
    """FastAPI dependency: validate token and return the caller's admin role."""
    return _resolve_admin_role(x_admin_token)


def require_admin_super(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> AdminRole:
    """FastAPI dependency: require ``super`` admin role; viewers get 403."""
    role = _resolve_admin_role(x_admin_token)
    if role != "super":
        raise HTTPException(status_code=403, detail="Super admin role required")
    return role
