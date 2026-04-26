"""
Patient detail routes: listing, search, timeline, delete,
working context, clear context, record listing,
and admin DB-view delegation.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud import (
    delete_patient_for_doctor,
)
from db.crud.patient import get_patient_for_doctor, search_patients_nl
from domain.patients.nl_search import extract_criteria
from db.engine import get_db
from db.models import MedicalRecordDB
from db.models.patient_message import PatientMessage
from domain.patients.timeline import build_patient_timeline
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit
from utils.log import safe_create_task
from channels.web.doctor_dashboard.record_handlers import (
    manage_records_for_doctor as _manage_records_for_doctor_impl,
    manage_patients_for_doctor as _manage_patients_for_doctor_impl,
    manage_patients_grouped_for_doctor as _manage_patients_grouped_for_doctor_impl,
    _fetch_latest_triage_map,
)
from channels.web.doctor_dashboard.admin_handlers import (
    admin_db_view_logic as _admin_db_view_logic,
    admin_tables_logic as _admin_tables_logic,
)
from channels.web.doctor_dashboard.admin_table_rows import admin_table_rows_logic as _admin_table_rows_logic
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id, _require_ui_admin_access
from channels.web.doctor_dashboard.filters import _fmt_ts

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Patient list / search / timeline ──────────────────────────────────────────

@router.get("/api/manage/patients", include_in_schema=True)
async def manage_patients(
    doctor_id: str = Query(default="web_doctor"),
    category: Optional[str] = Query(default=None),
    cursor: Optional[str] = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_patients_for_doctor_impl(
        db, resolved_doctor_id, category=category, cursor=cursor, limit=limit, offset=offset,
    )


@router.get("/api/manage/patients/grouped", include_in_schema=True)
async def manage_patients_grouped(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_patients_grouped_for_doctor_impl(db, doctor_id)


@router.get("/api/manage/patients/search", include_in_schema=True)
async def search_patients_endpoint(
    q: str = Query(..., min_length=1, max_length=200),
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor_id, scope="ui.search_patients")
    criteria = extract_criteria(q)
    _SEARCH_LIMIT = 20
    # Fetch limit+1 to detect truncation
    patients = await search_patients_nl(db, resolved_doctor_id, criteria, limit=_SEARCH_LIMIT + 1)
    has_more = len(patients) > _SEARCH_LIMIT
    if has_more:
        patients = patients[:_SEARCH_LIMIT]
    pids = [p.id for p in patients]
    if pids:
        counts_result = await db.execute(
            select(MedicalRecordDB.patient_id, func.count(MedicalRecordDB.id))
            .where(
                MedicalRecordDB.doctor_id == resolved_doctor_id,
                MedicalRecordDB.patient_id.in_(pids),
            )
            .group_by(MedicalRecordDB.patient_id)
        )
        count_map = {pid: count for pid, count in counts_result.all()}
    else:
        count_map = {}
    triage_map = await _fetch_latest_triage_map(db, resolved_doctor_id, pids)

    items = [
        {
            "id": p.id,
            "name": p.name,
            "gender": p.gender,
            "year_of_birth": p.year_of_birth,
            "created_at": _fmt_ts(p.created_at),
            "last_activity_at": _fmt_ts(getattr(p, "last_activity_at", None)),
            "record_count": int(count_map.get(p.id, 0)),
            "latest_triage_category": triage_map.get(p.id),
        }
        for p in patients
    ]
    return {
        "items": items,
        "total": len(items),
        "has_more": has_more,
        "criteria": {
            "surname": criteria.surname,
            "gender": criteria.gender,
            "age_min": criteria.age_min,
            "age_max": criteria.age_max,
            "keywords": criteria.keywords,
            "days_since_visit": criteria.days_since_visit,
        },
    }


@router.get("/api/manage/patients/{patient_id}/timeline", include_in_schema=True)
async def manage_patient_timeline(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patient_timeline")
    data = await build_patient_timeline(db, doctor_id=doctor_id, patient_id=patient_id, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"doctor_id": doctor_id, **data}


# ── Record listing ────────────────────────────────────────────────────────────

@router.get("/api/manage/records", include_in_schema=True)
async def manage_records(
    doctor_id: str = Query(default="web_doctor"),
    patient_id: int | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_records_for_doctor(
        db, resolved_doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


async def _manage_records_for_doctor(
    db,
    doctor_id: str,
    *,
    patient_id: int | None = None,
    patient_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    return await _manage_records_for_doctor_impl(
        db, doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


# ── Delete patient ────────────────────────────────────────────────────────────

@router.delete("/api/manage/patients/{patient_id}", include_in_schema=True)
async def delete_patient_endpoint(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Delete a patient and all their records/tasks."""
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patients.delete")
    deleted = await delete_patient_for_doctor(db, doctor_id, patient_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    safe_create_task(audit(doctor_id, "DELETE", "patient", str(patient_id)))
    return {"ok": True, "patient_id": patient_id}


@router.post(
    "/api/manage/patients/{patient_id}/ai-summary/refresh",
    include_in_schema=True,
)
async def refresh_patient_ai_summary(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate the AI summary for one patient synchronously so the UI can
    reflect the new summary on the next patient list refresh."""
    from db.models.patient import Patient as _Patient
    from domain.briefing.patient_summary import regenerate_patient_summary

    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patients.ai_summary.refresh")

    # Ownership check — never regenerate a summary for a patient owned by a
    # different doctor.
    stmt = select(_Patient).where(
        _Patient.id == patient_id, _Patient.doctor_id == doctor_id
    )
    res = await db.execute(stmt)
    patient = res.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    summary = await regenerate_patient_summary(patient_id=patient_id, db=db)
    await db.commit()
    await db.refresh(patient)
    return {
        "ok": True,
        "patient_id": patient_id,
        "ai_summary": patient.ai_summary,
        "ai_summary_at": _fmt_ts(patient.ai_summary_at),
    }


# ── Assign / remove labels on patients ────────────────────────────────────────

# ── Working context / clear context ───────────────────────────────────────────

@router.get("/api/manage/working-context", include_in_schema=True)
async def get_working_context(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the current working context for the doctor workbench header."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)

    return {
        "current_patient": None,
        "pending_draft": None,
        "next_step": "describe a patient or dictate a record",
    }


@router.post("/api/manage/clear-context", include_in_schema=True)
async def clear_context_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Clear all working context for a doctor: conversation history,
    chat archive, and in-memory caches.

    Called when the user clears the chat in the UI so all state resets.
    """
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)

    # Clear conversation context (not history — DB rows are permanent logs).
    # Resets the in-memory cache and generates a new session_id so the LLM
    # starts fresh without loading old messages back from DB.
    # Chat session cleared (routing layer removed — no-op)

    return {"ok": True}


# ── Patient chat (doctor side) ─────────────────────────────────────────────────

@router.get("/api/manage/patients/{patient_id}/chat", include_in_schema=True)
async def get_patient_chat(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return the full conversation thread for a patient (doctor view)."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.patient_chat")
    from db.crud.patient_message import list_patient_messages
    messages = await list_patient_messages(db, patient_id, resolved, limit=200)
    safe_create_task(audit(resolved, "READ", "patient_chat", str(patient_id)))
    return {
        "messages": [
            {
                "id": m.id,
                "content": m.content,
                "direction": m.direction,
                "source": m.source or ("patient" if m.direction == "inbound" else "ai"),
                "sender_id": m.sender_id,
                "triage_category": m.triage_category,
                "ai_handled": m.ai_handled,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in reversed(messages)  # newest-first → oldest-first for display
        ],
    }


@router.post("/api/manage/patients/{patient_id}/reply", include_in_schema=True)
async def reply_to_patient(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    body: dict = {},
    db: AsyncSession = Depends(get_db),
):
    """Doctor sends a direct reply to a patient."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.patient_reply")
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Reply text is required")

    # Same response for "no such patient" and "patient owned by another doctor"
    # so the caller cannot enumerate patient_ids across tenants.
    if await get_patient_for_doctor(db, resolved, patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    from domain.patient_lifecycle.reply import send_doctor_reply
    msg_id = await send_doctor_reply(
        doctor_id=resolved,
        patient_id=patient_id,
        text=text,
    )

    safe_create_task(audit(resolved, "WRITE", "patient_reply", str(patient_id)))
    return {
        "ok": True,
        "message_id": msg_id,
    }


# ── Admin DB-view delegation ──────────────────────────────────────────────────

@router.get("/api/admin/db-view")
async def admin_db_view(
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: AsyncSession = Depends(get_db),
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_db_view_logic(db, doctor_id, patient_name, date_from, date_to, limit)


@router.get("/api/admin/tables")
async def admin_tables(
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: AsyncSession = Depends(get_db),
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_tables_logic(db, doctor_id, patient_name, date_from, date_to)


@router.get("/api/admin/tables/{table_key}")
async def admin_table_rows(
    table_key: str,
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    # TODO: replace with keyset pagination (cursor-based) for large result sets
    # (see /api/manage/patients for the reference implementation)
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = 0,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: AsyncSession = Depends(get_db),
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_table_rows_logic(
        db, table_key, doctor_id, patient_name, date_from, date_to, limit, offset
    )
