"""Admin filters, date helpers, and test-doctor exclusion logic."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException

from utils.response_formatting import parse_tags as _parse_tags  # noqa: F401 — re-export


def _fmt_ts(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


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
