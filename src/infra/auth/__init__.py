"""services.auth 包初始化。"""
from __future__ import annotations

import os
from enum import Enum


class UserRole(str, Enum):
    """Application-level user roles (JWT 'role' claim)."""
    doctor = "doctor"
    patient = "patient"


def is_production() -> bool:
    """Canonical production check — reads both APP_ENV and ENVIRONMENT."""
    _app_env = os.environ.get("APP_ENV", "").strip().lower()
    _env = os.environ.get("ENVIRONMENT", "").strip().lower()
    return _app_env in {"production", "prod"} or _env in {"production", "prod"}


# Submodule re-exports — MUST come after is_production() to avoid circular
# import (request_auth imports is_production from this package).
from infra.auth.access_code_hash import hash_access_code, verify_access_code  # noqa: E402
from infra.auth.rate_limit import enforce_doctor_rate_limit  # noqa: E402
from infra.auth.request_auth import require_admin_token, resolve_doctor_id_from_auth_or_fallback  # noqa: E402
from infra.auth.wechat_id_hash import hash_wechat_id  # noqa: E402

__all__ = [
    "UserRole",
    "enforce_doctor_rate_limit",
    "hash_access_code",
    "hash_wechat_id",
    "is_production",
    "require_admin_token",
    "resolve_doctor_id_from_auth_or_fallback",
    "verify_access_code",
]
