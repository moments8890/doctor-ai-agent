"""Cross-doctor knowledge feed for the admin v3 知识 & AI page.

Endpoint:
  GET /api/admin/knowledge/recent

Returns a paginated, recency-sorted feed of `DoctorKnowledgeItem` rows
across every (non-test) doctor, joined to the doctor's display name.
Drives the RecentKnowledgeFeed cards on AiActivityPage so the "知识"
half of the page actually shows knowledge.

Auth: require_admin_role (super or viewer). Read-only.
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import Doctor, DoctorKnowledgeItem
from channels.web.doctor_dashboard.deps import require_admin_role
from channels.web.doctor_dashboard.filters import (
    _fmt_ts,
    apply_exclude_seeded,
    apply_exclude_test_doctors,
)


router = APIRouter(tags=["admin-knowledge"], include_in_schema=False)


# Snippet preview length — enough for two CSS lines on the card without
# blowing up the payload. Cards line-clamp anyway, so trimming server-side
# is a network optimization, not a correctness requirement.
_SNIPPET_MAX = 240
_LIMIT_DEFAULT = 24
_LIMIT_MAX = 200


def _unwrap(text: Optional[str]) -> str:
    """Knowledge content is sometimes JSON-wrapped (``{"text": "..."}``);
    return the inner text when we can so detail/snippet render the real content
    instead of the JSON envelope."""
    if not text:
        return ""
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                inner = obj.get("text") or obj.get("content") or obj.get("body")
                if isinstance(inner, str):
                    s = inner.strip()
        except (ValueError, json.JSONDecodeError):
            pass
    return s


def _snippet(text: Optional[str]) -> str:
    s = _unwrap(text)
    if len(s) <= _SNIPPET_MAX:
        return s
    return s[:_SNIPPET_MAX].rstrip() + "…"


@router.get("/api/admin/knowledge/recent")
async def admin_knowledge_recent(
    limit: int = Query(default=_LIMIT_DEFAULT, ge=1, le=_LIMIT_MAX),
    offset: int = Query(default=0, ge=0),
    doctor_id: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    include_seeded: bool = False,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_admin_role),
) -> dict:
    """Recent knowledge items across all doctors, newest-first by updated_at.

    Mirrors the filtering posture of /api/admin/suggestions/recent — exclude
    test doctors when no specific doctor filter is set, exclude seeded rows
    by default. Both behaviors flip off via `doctor_id=...` / `include_seeded=true`.
    """
    base = (
        select(
            DoctorKnowledgeItem.id,
            DoctorKnowledgeItem.title,
            DoctorKnowledgeItem.summary,
            DoctorKnowledgeItem.content,
            DoctorKnowledgeItem.category,
            DoctorKnowledgeItem.reference_count,
            DoctorKnowledgeItem.patient_safe,
            DoctorKnowledgeItem.created_at,
            DoctorKnowledgeItem.updated_at,
            DoctorKnowledgeItem.doctor_id,
            Doctor.name.label("doctor_name"),
        )
        .join(Doctor, Doctor.doctor_id == DoctorKnowledgeItem.doctor_id)
    )

    if doctor_id:
        base = base.where(DoctorKnowledgeItem.doctor_id == doctor_id)
    else:
        base = apply_exclude_test_doctors(base, DoctorKnowledgeItem.doctor_id)
    base = apply_exclude_seeded(
        base, DoctorKnowledgeItem, include_seeded=include_seeded
    )

    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                DoctorKnowledgeItem.title.ilike(like),
                DoctorKnowledgeItem.summary.ilike(like),
                DoctorKnowledgeItem.content.ilike(like),
            )
        )

    # Total for pagination
    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = (
        base.order_by(
            DoctorKnowledgeItem.updated_at.desc(),
            DoctorKnowledgeItem.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(paged)).all()

    items: List[dict] = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "title": r.title or "(无标题)",
                # Prefer summary for the snippet — that's what the doctor
                # wrote as the gist. Fall back to content's first ~240 chars
                # when summary is empty.
                "snippet": _snippet(r.summary or r.content),
                # Full unwrapped content + summary for the detail modal so
                # opening the card costs zero extra round-trips. Payload tax
                # is small at the page-size cap (24).
                "content": _unwrap(r.content),
                "summary": _unwrap(r.summary) if r.summary else "",
                "category": r.category,
                "reference_count": int(r.reference_count or 0),
                "patient_safe": bool(r.patient_safe),
                "doctor_id": r.doctor_id,
                "doctor_name": r.doctor_name or "(未命名医生)",
                "created_at": _fmt_ts(r.created_at),
                "updated_at": _fmt_ts(r.updated_at),
            }
        )

    return {
        "items": items,
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }
