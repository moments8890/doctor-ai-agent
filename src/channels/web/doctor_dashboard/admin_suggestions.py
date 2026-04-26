"""Admin cross-doctor AI suggestions API.

Endpoint:
  GET /api/admin/suggestions/recent

Returns a flat list of recent AI suggestions across every (non-test) doctor on
the platform. Powers the v3 admin "知识 & AI" page used by the read-only
partner doctor — useful for gauging how the AI is being used platform-wide.

Filters:
  filter    = all | accept | edit | reject | pending
  doctor_id (exact match)
  q         (case-insensitive substring of patient name OR suggestion content)
  limit     (1..200, default 50)
  offset    (>=0, default 0)

Filter mapping (matches the SuggestionDecision enum values):
  accept  → decision == "confirmed"
  edit    → decision == "edited"
  reject  → decision == "rejected"
  pending → decision IS NULL OR decision == "generated"

Each item includes a short content preview (the doctor's edit takes precedence
when the suggestion was edited; otherwise the AI draft) and a count of cited
knowledge items so the list row can show 引用 badges without a second fetch.
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import (
    AISuggestion,
    Doctor,
    MedicalRecordDB,
    Patient,
)
from channels.web.doctor_dashboard.deps import require_admin_role
from channels.web.doctor_dashboard.filters import _fmt_ts, apply_exclude_test_doctors

router = APIRouter(tags=["admin-suggestions"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LIMIT_MAX = 200
LIMIT_DEFAULT = 50

# How long the content preview can be before we ellipsize it. The list row
# only renders one line so this is just a defensive cap on payload size.
PREVIEW_MAX_CHARS = 240


def _preview(text: Optional[str]) -> str:
    if not text:
        return ""
    s = str(text).replace("\r", "").replace("\n", " ").strip()
    if len(s) <= PREVIEW_MAX_CHARS:
        return s
    return s[:PREVIEW_MAX_CHARS].rstrip() + "…"


def _count_cited_ids(raw: Optional[str]) -> int:
    """Count cited knowledge ids stored as a JSON string on the row.

    Tolerant of legacy variants (CSV, single int, malformed) — never raises.
    """
    if not raw:
        return 0
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        # Legacy CSV fallback: e.g. "12, 34"
        parts = [p.strip() for p in str(raw).split(",") if p.strip()]
        return len(parts)
    if isinstance(parsed, list):
        return len(parsed)
    if isinstance(parsed, (int, str)):
        return 1
    return 0


# ---------------------------------------------------------------------------
# GET /api/admin/suggestions/recent
# ---------------------------------------------------------------------------

@router.get("/api/admin/suggestions/recent")
async def admin_suggestions_recent(
    limit: int = Query(default=LIMIT_DEFAULT, ge=1, le=LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    filter: str = Query(default="all"),
    doctor_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    role: str = Depends(require_admin_role),  # noqa: ARG001 — auth gate only
) -> dict:
    """Cross-doctor AI suggestion feed with light filtering + pagination."""

    # ── Base query — join Doctor + MedicalRecord + Patient for names. ─────
    base = (
        select(
            AISuggestion.id,
            AISuggestion.section,
            AISuggestion.decision,
            AISuggestion.content,
            AISuggestion.edited_text,
            AISuggestion.cited_knowledge_ids,
            AISuggestion.created_at,
            AISuggestion.doctor_id,
            Doctor.name.label("doctor_name"),
            MedicalRecordDB.patient_id.label("patient_id"),
            Patient.name.label("patient_name"),
        )
        .join(Doctor, Doctor.doctor_id == AISuggestion.doctor_id)
        .join(MedicalRecordDB, MedicalRecordDB.id == AISuggestion.record_id)
        .outerjoin(Patient, Patient.id == MedicalRecordDB.patient_id)
    )

    # ── Filters ────────────────────────────────────────────────────────────
    if doctor_id:
        base = base.where(AISuggestion.doctor_id == doctor_id)
    else:
        base = apply_exclude_test_doctors(base, AISuggestion.doctor_id)

    f = (filter or "all").strip().lower()
    if f == "accept":
        base = base.where(AISuggestion.decision == "confirmed")
    elif f == "edit":
        base = base.where(AISuggestion.decision == "edited")
    elif f == "reject":
        base = base.where(AISuggestion.decision == "rejected")
    elif f == "pending":
        # "generated" is the legacy pending decision string; NULL is the
        # default for never-decided rows. Either should map to pending.
        base = base.where(
            or_(
                AISuggestion.decision.is_(None),
                AISuggestion.decision == "generated",
            )
        )
    # "all" → no extra decision filter

    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                Patient.name.ilike(like),
                AISuggestion.content.ilike(like),
            )
        )

    # ── Total count (mirrors filters above) ───────────────────────────────
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # ── Page (newest first) ────────────────────────────────────────────────
    paged = (
        base.order_by(AISuggestion.created_at.desc(), AISuggestion.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(paged)).all()

    items: List[dict] = []
    for r in rows:
        # Preview prefers the doctor's edited text (what was actually used)
        # but falls back to the AI draft for confirmed/rejected/pending rows
        # where edited_text is empty.
        preview_source = r.edited_text or r.content
        items.append(
            {
                "id": r.id,
                "section": r.section,
                "decision": r.decision,
                # patient_id is needed by the V3 admin so a row click can
                # drill straight into the patient detail page where this
                # suggestion is rendered inline under its parent record.
                "patient_id": r.patient_id,
                "patient_name": r.patient_name or "",
                "doctor_id": r.doctor_id,
                # See admin_patients.py — fall back to a sentinel rather than
                # leaking the raw doctor_id when the name column is null.
                "doctor_name": r.doctor_name or "(未命名医生)",
                "content_preview": _preview(preview_source),
                "cited_knowledge_count": _count_cited_ids(r.cited_knowledge_ids),
                "created_at": _fmt_ts(r.created_at),
            }
        )

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }
