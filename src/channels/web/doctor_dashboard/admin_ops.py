"""
Admin 运营 (operations) API — pilot progress + partner weekly report.

Endpoints (Phase 3 of admin v3 port):
  GET /api/admin/ops/pilot-progress
  GET /api/admin/ops/partner-report?week=YYYY-Wxx

Both are read-only and accessible to viewer-role tokens (the read-only
"partner doctor" role from Task 4.1). Values are derived from existing tables
so no new DB columns / migrations are needed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import (
    AISuggestion,
    Doctor,
    Patient,
    PatientMessage,
    SuggestionDecision,
)
from channels.web.doctor_dashboard.deps import require_admin_role
from channels.web.doctor_dashboard.filters import apply_exclude_test_doctors

router = APIRouter(tags=["admin-ops"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Pilot config (synthetic — would move to a settings table later)
# ---------------------------------------------------------------------------

PILOT_START = date(2026, 1, 1)
PILOT_TOTAL_WEEKS = 24
PILOT_DOCTORS_TARGET = 20

PILOT_MILESTONES: list[dict] = [
    {"date": "2026-01-15", "label": "试点启动 · 首批医生加入"},
    {"date": "2026-02-28", "label": "首月数据回顾"},
    {"date": "2026-04-30", "label": "阶段汇报"},
    {"date": "2026-06-15", "label": "期中评估"},
    {"date": "2026-08-30", "label": "试点收官 · 转正式部署"},
]


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _iso_week_bounds(today: date) -> tuple[date, date, str]:
    """Return (monday, next_monday, "YYYY-Wxx") for the ISO week of ``today``."""
    iso_year, iso_week, _ = today.isocalendar()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=7), f"{iso_year}-W{iso_week:02d}"


def _parse_week(week_param: str) -> tuple[date, date, str]:
    """Parse 'YYYY-Wxx' → (monday, next_monday, normalized_label).

    Falls back to the current ISO week if parsing fails — the endpoint is
    a partner-facing read-only view, so we prefer always-show-something over
    422-ing a malformed query.
    """
    try:
        year_str, week_str = week_param.split("-W")
        year = int(year_str)
        week = int(week_str)
        # ISO calendar: week 1 contains the first Thursday of the year.
        # Use date.fromisocalendar (Py 3.8+).
        monday = date.fromisocalendar(year, week, 1)
    except (ValueError, IndexError):
        return _iso_week_bounds(_today_utc())
    return monday, monday + timedelta(days=7), f"{year}-W{week:02d}"


# ---------------------------------------------------------------------------
# GET /api/admin/ops/pilot-progress
# ---------------------------------------------------------------------------


@router.get("/api/admin/ops/pilot-progress")
async def pilot_progress(
    db: AsyncSession = Depends(get_db),
    role: str = Depends(require_admin_role),  # noqa: ARG001 — auth gate only
) -> dict:
    """Pilot rollout progress: weeks elapsed, milestones, doctor count."""
    today = _today_utc()
    days_elapsed = max((today - PILOT_START).days, 0)
    current_week = min(days_elapsed // 7 + 1, PILOT_TOTAL_WEEKS)

    milestones = []
    for m in PILOT_MILESTONES:
        m_date = date.fromisoformat(m["date"])
        milestones.append(
            {
                "date": m["date"],
                "label": m["label"],
                "done": m_date <= today,
            }
        )

    doctors_active = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(Doctor),
                Doctor.doctor_id,
            )
        )
    ).scalar() or 0

    return {
        "start_date": PILOT_START.isoformat(),
        "current_week": current_week,
        "total_weeks": PILOT_TOTAL_WEEKS,
        "milestones": milestones,
        "doctors_active": int(doctors_active),
        "doctors_target": PILOT_DOCTORS_TARGET,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/ops/partner-report?week=YYYY-Wxx
# ---------------------------------------------------------------------------


@router.get("/api/admin/ops/partner-report")
async def partner_report(
    week: Optional[str] = Query(default=None, description="ISO week, e.g. 2026-W17"),
    db: AsyncSession = Depends(get_db),
    role: str = Depends(require_admin_role),  # noqa: ARG001 — auth gate only
) -> dict:
    """Weekly snapshot for partner-facing report.

    All counts cover the requested ISO week (Mon 00:00 UTC – next Mon 00:00).
    """
    today = _today_utc()
    if week:
        start_d, end_d, week_label = _parse_week(week)
    else:
        start_d, end_d, week_label = _iso_week_bounds(today)
    start_dt = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_d, datetime.min.time(), tzinfo=timezone.utc)

    # ── Adoption: confirmed / total decided AI suggestions in the week ──
    decided_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(AISuggestion.decision, func.count())
                .where(
                    and_(
                        AISuggestion.decided_at >= start_dt,
                        AISuggestion.decided_at < end_dt,
                        AISuggestion.decision.isnot(None),
                    )
                )
                .group_by(AISuggestion.decision),
                AISuggestion.doctor_id,
            )
        )
    ).all()
    decision_counts: dict[str, int] = {}
    for d, c in decided_rows:
        decision_counts[d] = decision_counts.get(d, 0) + int(c)
    confirmed = decision_counts.get(SuggestionDecision.confirmed, 0) + decision_counts.get(
        "confirmed", 0
    )
    total_decided = sum(decision_counts.values())
    adoption_rate = round(confirmed / total_decided, 2) if total_decided else 0.0

    # ── Patient active: distinct patients with messages in the week ──
    patient_active_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count(func.distinct(PatientMessage.patient_id))).where(
                    and_(
                        PatientMessage.created_at >= start_dt,
                        PatientMessage.created_at < end_dt,
                    )
                ),
                PatientMessage.doctor_id,
            )
        )
    ).scalar() or 0
    patient_active = int(patient_active_rows)

    # ── Danger signals triggered ──
    # AISuggestion has no dedicated "danger_signal" section yet; keep at 0
    # so the UI tile renders cleanly. TODO: once a danger-signal section/flag
    # lands on AISuggestion, count rows where section == "danger_signal" within
    # the [start_dt, end_dt) window.
    danger_signals_triggered = 0

    # ── Top doctors: top 3 by adoption rate within the week (min 3 decided) ──
    top_doctors: list[dict] = []
    per_doctor_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(
                    AISuggestion.doctor_id,
                    AISuggestion.decision,
                    func.count(),
                )
                .where(
                    and_(
                        AISuggestion.decided_at >= start_dt,
                        AISuggestion.decided_at < end_dt,
                        AISuggestion.decision.isnot(None),
                    )
                )
                .group_by(AISuggestion.doctor_id, AISuggestion.decision),
                AISuggestion.doctor_id,
            )
        )
    ).all()
    per_doctor: dict[str, dict[str, int]] = {}
    for did, dec, cnt in per_doctor_rows:
        bucket = per_doctor.setdefault(did, {})
        bucket[dec] = bucket.get(dec, 0) + int(cnt)

    for did, buckets in per_doctor.items():
        n_confirmed = buckets.get(SuggestionDecision.confirmed, 0) + buckets.get(
            "confirmed", 0
        )
        n_total = sum(buckets.values())
        if n_total < 3:
            continue
        rate = round(n_confirmed / n_total, 2)

        # Doctor name + patient count
        doc_row = (
            await db.execute(select(Doctor).where(Doctor.doctor_id == did))
        ).scalars().first()
        if doc_row is None:
            continue
        pcount = (
            await db.execute(
                select(func.count()).select_from(Patient).where(Patient.doctor_id == did)
            )
        ).scalar() or 0
        top_doctors.append(
            {
                "doctor_id": did,
                "name": doc_row.name or did,
                "adoption_rate": rate,
                "patient_count": int(pcount),
            }
        )

    top_doctors.sort(key=lambda r: r["adoption_rate"], reverse=True)
    top_doctors = top_doctors[:3]

    return {
        "week": week_label,
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "adoption": {"rate": adoption_rate, "total": total_decided},
        "patient_active": patient_active,
        "danger_signals_triggered": danger_signals_triggered,
        "top_doctors": top_doctors,
    }
