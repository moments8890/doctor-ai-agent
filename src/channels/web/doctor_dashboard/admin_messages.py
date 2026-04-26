"""
Admin cross-doctor messages API.

Endpoint:
  GET /api/admin/messages/recent

Returns one row per (patient_id, doctor_id) thread — the latest message in
each thread plus an unread heuristic. Powers the v3 admin "沟通中心" page used
by the read-only partner doctor.

Filters:
  filter   = all | unread | today
  doctor_id (exact match)
  q        (case-insensitive: matches patient name OR last message content)
  limit    (1..200, default 50)
  offset   (>=0, default 0)

Unread heuristic:
  ``PatientMessage.read_at`` exists on the schema (since ADR 0020) but is not
  yet populated reliably by the inbound pipeline, so we fall back to:
  count of inbound messages in the thread whose ``created_at`` is later than
  the thread's most recent outbound ``created_at`` (or all inbound messages
  if no outbound exists yet).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import Doctor, Patient, PatientMessage
from channels.web.doctor_dashboard.deps import require_admin_role
from channels.web.doctor_dashboard.filters import _fmt_ts, apply_exclude_test_doctors

router = APIRouter(tags=["admin-messages"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIMIT_MAX = 200
LIMIT_DEFAULT = 50


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_start_utc() -> datetime:
    now = _now_utc()
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# GET /api/admin/messages/recent
# ---------------------------------------------------------------------------


@router.get("/api/admin/messages/recent")
async def admin_messages_recent(
    limit: int = Query(default=LIMIT_DEFAULT, ge=1, le=LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    filter: str = Query(default="all"),
    doctor_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    role: str = Depends(require_admin_role),  # noqa: ARG001 — auth gate only
) -> dict:
    """Cross-doctor recent-message inbox grouped by (patient, doctor) thread."""
    today_cutoff = _today_start_utc()

    # ── Per-thread latest message — pick the row with no later sibling in
    #    the same (patient_id, doctor_id) thread. Portable across SQLite +
    #    MySQL (no window functions required). M0 is the candidate "latest"
    #    row; M1 is any later row in the same thread.
    M0 = aliased(PatientMessage, name="m0")
    M1 = aliased(PatientMessage, name="m1")
    is_latest = ~(
        select(M1.id)
        .where(
            and_(
                M1.patient_id == M0.patient_id,
                M1.doctor_id == M0.doctor_id,
                or_(
                    M1.created_at > M0.created_at,
                    and_(M1.created_at == M0.created_at, M1.id > M0.id),
                ),
            )
        )
        .correlate(M0)
        .exists()
    )

    # ── Per-thread thread_message_count + unread_count, as scalar subqueries.
    MC = aliased(PatientMessage, name="mc")
    thread_count_sq = (
        select(func.count())
        .select_from(MC)
        .where(
            and_(
                MC.patient_id == M0.patient_id,
                MC.doctor_id == M0.doctor_id,
            )
        )
        .correlate(M0)
        .scalar_subquery()
    )

    MO = aliased(PatientMessage, name="mo")
    last_outbound_sq = (
        select(func.max(MO.created_at))
        .where(
            and_(
                MO.patient_id == M0.patient_id,
                MO.doctor_id == M0.doctor_id,
                MO.direction == "outbound",
            )
        )
        .correlate(M0)
        .scalar_subquery()
    )

    MU = aliased(PatientMessage, name="mu")
    unread_sq = (
        select(func.count())
        .select_from(MU)
        .where(
            and_(
                MU.patient_id == M0.patient_id,
                MU.doctor_id == M0.doctor_id,
                MU.direction == "inbound",
                or_(
                    last_outbound_sq.is_(None),
                    MU.created_at > last_outbound_sq,
                ),
            )
        )
        .correlate(M0)
        .scalar_subquery()
    )

    # ── Base query joining the latest-message row to its Patient + Doctor.
    base = (
        select(
            M0.id.label("msg_id"),
            M0.patient_id,
            M0.doctor_id,
            M0.direction,
            M0.content,
            M0.created_at,
            Patient.name.label("patient_name"),
            Doctor.name.label("doctor_name"),
            thread_count_sq.label("thread_message_count"),
            unread_sq.label("unread_count"),
        )
        .join(Patient, Patient.id == M0.patient_id)
        .join(Doctor, Doctor.doctor_id == M0.doctor_id)
        .where(is_latest)
    )

    # ── Filters ────────────────────────────────────────────────────────────
    if doctor_id:
        base = base.where(M0.doctor_id == doctor_id)
    else:
        base = apply_exclude_test_doctors(base, M0.doctor_id)

    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Patient.name.ilike(like), M0.content.ilike(like)))

    if filter == "today":
        base = base.where(M0.created_at >= today_cutoff)
    elif filter == "unread":
        base = base.where(unread_sq > 0)
    # "all" → no extra filter

    # ── Total count (mirrors filters above) ───────────────────────────────
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # ── Page ──────────────────────────────────────────────────────────────
    paged = base.order_by(M0.created_at.desc(), M0.id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(paged)).all()

    items: List[dict] = []
    for r in rows:
        created_at = r.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        items.append(
            {
                "patient_id": r.patient_id,
                "patient_name": r.patient_name or "",
                "doctor_id": r.doctor_id,
                # See admin_patients.py — fall back to a sentinel rather than
                # leaking the raw doctor_id when the name column is null.
                "doctor_name": r.doctor_name or "(未命名医生)",
                "last_message": {
                    "id": r.msg_id,
                    "direction": r.direction,
                    "content": r.content or "",
                    "created_at": _fmt_ts(created_at) if created_at else None,
                },
                "unread_count": int(r.unread_count or 0),
                "thread_message_count": int(r.thread_message_count or 0),
            }
        )

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/messages/thread
# ---------------------------------------------------------------------------


_THREAD_LIMIT_DEFAULT = 500
_THREAD_LIMIT_MAX = 1000


@router.get("/api/admin/messages/thread")
async def admin_messages_thread(
    patient_id: int = Query(..., description="Patient row id"),
    doctor_id: str = Query(..., description="Doctor id (string PK)"),
    limit: int = Query(default=_THREAD_LIMIT_DEFAULT, ge=1, le=_THREAD_LIMIT_MAX),
    db: AsyncSession = Depends(get_db),
    role: str = Depends(require_admin_role),  # noqa: ARG001 — auth gate only
) -> dict:
    """Full message timeline for one (patient, doctor) thread, ascending by ts.

    Powers the WeChat-style chat history modal on 沟通中心. Returns the patient
    + doctor display names alongside the bubbles so the modal header doesn't
    need a second round-trip.
    """
    pat_row = (
        await db.execute(
            select(
                Patient.id,
                Patient.name,
                Patient.gender,
                Patient.year_of_birth,
            ).where(Patient.id == patient_id)
        )
    ).first()
    doc_row = (
        await db.execute(
            select(Doctor.doctor_id, Doctor.name).where(Doctor.doctor_id == doctor_id)
        )
    ).first()

    msgs = (
        await db.execute(
            select(
                PatientMessage.id,
                PatientMessage.direction,
                PatientMessage.content,
                PatientMessage.created_at,
            )
            .where(
                and_(
                    PatientMessage.patient_id == patient_id,
                    PatientMessage.doctor_id == doctor_id,
                )
            )
            .order_by(PatientMessage.created_at.asc(), PatientMessage.id.asc())
            .limit(limit)
        )
    ).all()

    items = []
    for m in msgs:
        created_at = m.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        items.append(
            {
                "id": m.id,
                "direction": m.direction,
                "content": m.content or "",
                "created_at": _fmt_ts(created_at) if created_at else None,
            }
        )

    yob = pat_row.year_of_birth if pat_row else None
    age = (_now_utc().year - yob) if yob else None

    return {
        "patient": {
            "id": pat_row.id if pat_row else patient_id,
            "name": (pat_row.name if pat_row else None) or "",
            "gender": pat_row.gender if pat_row else None,
            "age": age,
        },
        "doctor": {
            "doctor_id": doc_row.doctor_id if doc_row else doctor_id,
            "name": (doc_row.name if doc_row else None) or "(未命名医生)",
        },
        "items": items,
        "total": len(items),
    }
