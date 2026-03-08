"""
UI 路由共享工具：日期解析、记录格式化和分页辅助函数。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from services.auth.request_auth import require_admin_token, resolve_doctor_id_from_auth_or_fallback


def _extract_tunnel_url_from_log(content: str) -> str | None:
    quick = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", content or "")
    if quick:
        return quick[-1]

    generic = re.findall(r"https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s|]*)?", content or "")
    for url in reversed(generic):
        if "127.0.0.1" in url or "localhost" in url:
            continue
        if "cloudflare.com" in url and "trycloudflare.com" not in url:
            continue
        return url.rstrip(" .|")
    return None


def _fmt_ts(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_tags(raw: str | None) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception as exc:
        logging.getLogger("ui").warning("[UI] invalid category/risk tags json: %s", exc)
        return []


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None or not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _is_risk_stale(risk_computed_at: datetime | None, hours: int = 24) -> bool:
    if risk_computed_at is None:
        return True
    if risk_computed_at.tzinfo is None:
        risk_computed_at = risk_computed_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - risk_computed_at
    return delta.total_seconds() >= hours * 3600


def _normalize_query_str(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return value


def _normalize_date_yyyy_mm_dd(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from/date_to must be YYYY-MM-DD")
    return value


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


def _parse_admin_filters(
    doctor_id: str | None,
    patient_name: str | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str | None, str | None, str | None, str | None, datetime | None, datetime | None]:
    doctor_id = _normalize_query_str(doctor_id)
    patient_name = _normalize_query_str(patient_name)
    date_from = _normalize_date_yyyy_mm_dd(date_from)
    date_to = _normalize_date_yyyy_mm_dd(date_to)
    dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt_to_exclusive = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1) if date_to else None
    return doctor_id, patient_name, date_from, date_to, dt_from, dt_to_exclusive


def _apply_created_at_filters(stmt, model, dt_from: datetime | None, dt_to_exclusive: datetime | None):
    if dt_from is not None and hasattr(model, "created_at"):
        stmt = stmt.where(model.created_at >= dt_from)
    if dt_to_exclusive is not None and hasattr(model, "created_at"):
        stmt = stmt.where(model.created_at < dt_to_exclusive)
    return stmt


# ---------------------------------------------------------------------------
# E2E / integration-test doctor ID filtering
# ---------------------------------------------------------------------------

# doctor_id prefixes used exclusively by automated tests.
# Rows belonging to these doctors are hidden from production UI views by default
# so test noise never appears alongside real clinical data.
E2E_DOCTOR_PREFIXES: tuple[str, ...] = ("inttest_", "chatlog_e2e_")


def _is_test_doctor_id(doctor_id: str) -> bool:
    return any(doctor_id.startswith(p) for p in E2E_DOCTOR_PREFIXES)


def apply_exclude_test_doctors(stmt, doctor_id_col):
    """Exclude test doctor rows when no specific doctor filter is active.

    Pass the SQLAlchemy column expression that holds doctor_id, e.g.
    ``Doctor.doctor_id`` or ``Patient.doctor_id``.
    """
    from sqlalchemy import and_, not_

    conditions = [not_(doctor_id_col.like(f"{prefix}%")) for prefix in E2E_DOCTOR_PREFIXES]
    if len(conditions) == 1:
        return stmt.where(conditions[0])
    return stmt.where(and_(*conditions))
