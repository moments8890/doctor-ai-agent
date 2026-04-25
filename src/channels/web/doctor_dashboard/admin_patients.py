"""
Admin cross-doctor patients API.

Endpoint:
  GET /api/admin/patients

Returns a flat list of patients across every (non-test) doctor on the
platform. Powers the v3 admin "全体患者" page used by the read-only partner
doctor. Read-only — accessible to viewer-role tokens.

Filters:
  filter   = all | danger | warn | silent | postop
  doctor_id (exact match)
  q        (case-insensitive name substring)
  limit    (1..200, default 100)
  offset   (>=0, default 0)

`silent`  → no patient message in the last 7 days
`postop`  → patient has at least one ``MedicalRecordDB`` whose record_type
            or content matches a post-op heuristic
`danger`/`warn` → not yet derivable from existing tables; returns no rows
            (TODO: surface real risk once the suggestion → risk pipeline
            lands; v1 keeps every row's `risk` as null).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import (
    Doctor,
    MedicalRecordDB,
    Patient,
    PatientMessage,
)
from channels.web.doctor_dashboard.deps import require_admin_role
from channels.web.doctor_dashboard.filters import _fmt_ts, apply_exclude_test_doctors

router = APIRouter(tags=["admin-patients"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIMIT_MAX = 200
LIMIT_DEFAULT = 100

POSTOP_KEYWORDS = ("术后", "post-op", "post op", "postop", "postoperative")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# GET /api/admin/patients
# ---------------------------------------------------------------------------

@router.get("/api/admin/patients")
async def admin_patients(
    limit: int = Query(default=LIMIT_DEFAULT, ge=1, le=LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    filter: str = Query(default="all"),
    doctor_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    role: str = Depends(require_admin_role),  # noqa: ARG001 — auth gate only
) -> dict:
    """Cross-doctor patient list with light filtering + pagination."""
    cutoff_30d = _now_utc() - timedelta(days=30)
    cutoff_7d = _now_utc() - timedelta(days=7)

    # ── Per-patient aggregates as scalar subqueries ────────────────────────
    last_msg_sq = (
        select(func.max(PatientMessage.created_at))
        .where(PatientMessage.patient_id == Patient.id)
        .correlate(Patient)
        .scalar_subquery()
    )
    msg_30d_sq = (
        select(func.count())
        .select_from(PatientMessage)
        .where(
            and_(
                PatientMessage.patient_id == Patient.id,
                PatientMessage.created_at >= cutoff_30d,
            )
        )
        .correlate(Patient)
        .scalar_subquery()
    )
    record_count_sq = (
        select(func.count())
        .select_from(MedicalRecordDB)
        .where(MedicalRecordDB.patient_id == Patient.id)
        .correlate(Patient)
        .scalar_subquery()
    )

    # ── Base query (joins Doctor for the name column) ──────────────────────
    base = (
        select(
            Patient.id,
            Patient.name,
            Patient.gender,
            Patient.year_of_birth,
            Patient.doctor_id,
            Doctor.name.label("doctor_name"),
            last_msg_sq.label("last_message_at"),
            msg_30d_sq.label("message_count_30d"),
            record_count_sq.label("record_count"),
        )
        .join(Doctor, Doctor.doctor_id == Patient.doctor_id)
    )

    # ── Filters ────────────────────────────────────────────────────────────
    if doctor_id:
        base = base.where(Patient.doctor_id == doctor_id)
    else:
        base = apply_exclude_test_doctors(base, Patient.doctor_id)

    if q:
        like = f"%{q.strip()}%"
        base = base.where(Patient.name.ilike(like))

    if filter == "silent":
        # silent: no message in last 7 days (either never messaged or last_msg < 7d ago)
        base = base.where(
            or_(last_msg_sq.is_(None), last_msg_sq < cutoff_7d)
        )
    elif filter == "postop":
        # postop: has any record whose record_type or content hints post-op
        keyword_clauses = []
        for kw in POSTOP_KEYWORDS:
            kw_like = f"%{kw}%"
            keyword_clauses.append(MedicalRecordDB.record_type.ilike(kw_like))
            keyword_clauses.append(MedicalRecordDB.content.ilike(kw_like))
        postop_exists = (
            select(MedicalRecordDB.id)
            .where(
                and_(
                    MedicalRecordDB.patient_id == Patient.id,
                    or_(*keyword_clauses),
                )
            )
            .correlate(Patient)
            .exists()
        )
        base = base.where(postop_exists)
    elif filter in ("danger", "warn"):
        # TODO: derive once a per-patient risk signal exists. v1 returns no rows.
        base = base.where(False)
    # "all" → no extra filter

    # ── Total count (mirrors filters above) ───────────────────────────────
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # ── Page ──────────────────────────────────────────────────────────────
    paged = (
        base.order_by(last_msg_sq.desc().nullslast(), Patient.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(paged)).all()

    items: List[dict] = []
    for r in rows:
        last_at = r.last_message_at
        if last_at and last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        items.append(
            {
                "id": r.id,
                "name": r.name,
                "gender": r.gender,
                "year_of_birth": r.year_of_birth,
                "doctor_id": r.doctor_id,
                # Falls back to a sentinel rather than the raw doctor_id when
                # Doctor.name is null — leaking IDs into the UI looks broken
                # to non-developer viewers (admin self-eval 2026-04-25).
                "doctor_name": r.doctor_name or "(未命名医生)",
                "last_message_at": _fmt_ts(last_at) if last_at else None,
                "message_count_30d": int(r.message_count_30d or 0),
                "record_count": int(r.record_count or 0),
                "risk": None,
            }
        )

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }
