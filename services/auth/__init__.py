"""services.auth 包初始化。"""
from __future__ import annotations

import os


def is_production() -> bool:
    """Canonical production check — reads both APP_ENV and ENVIRONMENT."""
    _app_env = os.environ.get("APP_ENV", "").strip().lower()
    _env = os.environ.get("ENVIRONMENT", "").strip().lower()
    return _app_env in {"production", "prod"} or _env in {"production", "prod"}
