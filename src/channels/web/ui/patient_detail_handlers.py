"""
Patient detail routes: listing, search, timeline, delete, label assignment,
working context, clear context, pending record confirmation, record listing,
and admin DB-view delegation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import func, select

from db.models.pending import PendingRecordStatus

from db.crud import (
    get_all_patients,
    get_records_for_patient,
    get_all_records_for_doctor,
    get_pending_record,
    confirm_pending_record,
    abandon_pending_record,
    delete_patient_for_doctor,
    assign_label,
    remove_label,
)
from db.crud.patient import search_patients_nl
from domain.patients.nl_search import extract_criteria
from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB, Patient
from domain.patients.timeline import build_patient_timeline
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit
from utils.log import safe_create_task
from agent.pending import get_pending_draft_id, clear_pending_draft_id
from utils.errors import DomainError
from channels.web.ui.record_handlers import (
    manage_records_for_doctor as _manage_records_for_doctor_impl,
    manage_patients_for_doctor as _manage_patients_for_doctor_impl,
    manage_patients_grouped_for_doctor as _manage_patients_grouped_for_doctor_impl,
)
from channels.web.ui.admin_handlers import (
    admin_db_view_logic as _admin_db_view_logic,
    admin_tables_logic as _admin_tables_logic,
)
from channels.web.ui.admin_table_rows import admin_table_rows_logic as _admin_table_rows_logic
from channels.web.ui._utils import (
    _fmt_ts,
    _parse_tags,
    _resolve_ui_doctor_id,
    _require_ui_admin_access,
)

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
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_patients_for_doctor_impl(
        resolved_doctor_id, category=category, cursor=cursor, limit=limit, offset=offset,
    )


@router.get("/api/manage/patients/grouped", include_in_schema=True)
async def manage_patients_grouped(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_patients_grouped_for_doctor_impl(doctor_id)


@router.get("/api/manage/patients/search", include_in_schema=True)
async def search_patients_endpoint(
    q: str = Query(..., min_length=1, max_length=200),
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor_id, scope="ui.search_patients")
    criteria = extract_criteria(q)
    _SEARCH_LIMIT = 20
    async with AsyncSessionLocal() as db:
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

    items = [
        {
            "id": p.id,
            "name": p.name,
            "gender": p.gender,
            "year_of_birth": p.year_of_birth,
            "created_at": _fmt_ts(p.created_at),
            "record_count": int(count_map.get(p.id, 0)),
            "primary_category": p.primary_category,
            "category_tags": _parse_tags(p.category_tags),
            "labels": [{"id": lbl.id, "name": lbl.name, "color": lbl.color} for lbl in (p.labels or [])],
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
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patient_timeline")
    async with AsyncSessionLocal() as db:
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
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_records_for_doctor(
        resolved_doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


async def _manage_records_for_doctor(
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
        doctor_id,
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
):
    """Delete a patient and all their records/tasks."""
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.patients.delete")
    async with AsyncSessionLocal() as db:
        deleted = await delete_patient_for_doctor(db, doctor_id, patient_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    safe_create_task(audit(doctor_id, "DELETE", "patient", str(patient_id)))
    return {"ok": True, "patient_id": patient_id}


# ── Assign / remove labels on patients ────────────────────────────────────────

@router.post("/api/manage/patients/{patient_id}/labels/{label_id}", include_in_schema=True)
async def assign_label_endpoint(
    patient_id: int,
    label_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.assign")
    async with AsyncSessionLocal() as db:
        try:
            await assign_label(db, patient_id, label_id, doctor_id)
        except DomainError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)
    safe_create_task(audit(doctor_id, "WRITE", "label", f"{patient_id}:{label_id}"))
    return {"ok": True}


@router.delete("/api/manage/patients/{patient_id}/labels/{label_id}", include_in_schema=True)
async def remove_label_endpoint(
    patient_id: int,
    label_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.remove")
    async with AsyncSessionLocal() as db:
        try:
            await remove_label(db, patient_id, label_id, doctor_id)
        except DomainError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)
    safe_create_task(audit(doctor_id, "DELETE", "label", f"{patient_id}:{label_id}"))
    return {"ok": True}


# ── Working context / clear context ───────────────────────────────────────────

@router.get("/api/manage/working-context", include_in_schema=True)
async def get_working_context(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the current working context for the doctor workbench header.

    Combines current patient, pending draft, and next-step state into one
    response so the UI can render the context header without multiple calls.
    """
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)

    # Current patient — no longer tracked in ctx; return None
    current_patient = None

    # Pending draft
    pending_draft = None
    pending_id = await get_pending_draft_id(resolved_id)
    if pending_id:
        async with AsyncSessionLocal() as session:
            pending = await get_pending_record(session, pending_id, resolved_id)
        now = datetime.now(timezone.utc)
        _exp = pending.expires_at if pending else None
        if _exp and _exp.tzinfo is None:
            _exp = _exp.replace(tzinfo=timezone.utc)
        if pending and pending.status == PendingRecordStatus.awaiting and (not _exp or _exp >= now):
            try:
                draft = json.loads(pending.draft_json)
                preview = draft.get("content", "")[:60]
            except Exception:
                preview = ""
            pending_draft = {
                "id": pending.id,
                "patient_name": pending.patient_name or "",
                "preview": preview,
                "expires_at": pending.expires_at.isoformat() if pending.expires_at else None,
            }
        else:
            await clear_pending_draft_id(resolved_id)

    # Next step
    next_step = None
    if pending_draft:
        next_step = "confirm or abandon pending draft"
    elif current_patient is None:
        next_step = "describe a patient or dictate a record"

    return {
        "current_patient": current_patient,
        "pending_draft": pending_draft,
        "next_step": next_step,
    }


@router.post("/api/manage/clear-context", include_in_schema=True)
async def clear_context_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Clear all working context for a doctor: current patient, pending draft,
    blocked write, pending create, candidate patient, conversation history,
    chat archive, and in-memory caches.

    Called when the user clears the chat in the UI so all state resets.
    """
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)

    # Abandon any pending drafts
    try:
        from db.models.pending import PendingRecord
        from sqlalchemy import select, update as sa_update
        async with AsyncSessionLocal() as session:
            await session.execute(
                sa_update(PendingRecord).where(
                    PendingRecord.doctor_id == resolved_id,
                    PendingRecord.status == PendingRecordStatus.awaiting,
                ).values(status=PendingRecordStatus.abandoned)
            )
            await session.commit()
    except Exception:
        pass

    # Delete chat_archive rows for this doctor
    try:
        from db.models.doctor import ChatArchive
        from sqlalchemy import delete
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(ChatArchive).where(ChatArchive.doctor_id == resolved_id)
            )
            await session.commit()
    except Exception:
        pass

    # Clear in-memory agent session if it exists
    try:
        from agent.session import _agents
        _agents.pop(resolved_id, None)
    except Exception:
        pass

    return {"ok": True}


# ── Pending record confirmation ───────────────────────────────────────────────

@router.get("/api/manage/pending-record", include_in_schema=True)
async def get_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the current pending record draft for a doctor, or null if none."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    pending_id = await get_pending_draft_id(resolved_id)
    if not pending_id:
        return None
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, resolved_id)
    if pending is None or pending.status != PendingRecordStatus.awaiting:
        await clear_pending_draft_id(resolved_id)
        return None
    now = datetime.now(timezone.utc)
    _exp = pending.expires_at
    if _exp and _exp.tzinfo is None:
        _exp = _exp.replace(tzinfo=timezone.utc)
    if _exp and _exp < now:
        await clear_pending_draft_id(resolved_id)
        return None
    try:
        draft = json.loads(pending.draft_json)
        raw_content = draft.get("content", "")
        content_preview = raw_content[:100] + ("\u2026" if len(raw_content) > 100 else "")
    except Exception:
        content_preview = ""
    return {
        "id": pending.id,
        "patient_name": pending.patient_name or "\u672a\u5173\u8054",
        "content_preview": content_preview,
        "created_at": pending.created_at.isoformat() if pending.created_at else None,
        "expires_at": pending.expires_at.isoformat() if pending.expires_at else None,
    }


@router.post("/api/manage/pending-record/confirm", include_in_schema=True)
async def confirm_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Confirm the pending record draft -> save to medical_records."""
    from domain.records.confirm_pending import save_pending_record
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    pending_id = await get_pending_draft_id(resolved_id)
    if not pending_id:
        raise HTTPException(status_code=404, detail="No pending record")
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, resolved_id)
    if pending is None or pending.status != PendingRecordStatus.awaiting:
        await clear_pending_draft_id(resolved_id)
        raise HTTPException(status_code=404, detail="Pending record not found or already processed")
    from datetime import datetime, timezone as _tz
    if pending.expires_at:
        _exp = pending.expires_at if pending.expires_at.tzinfo else pending.expires_at.replace(tzinfo=_tz.utc)
        if _exp <= datetime.now(_tz.utc):
            await clear_pending_draft_id(resolved_id)
            raise HTTPException(status_code=410, detail="Pending record has expired")
    result = await save_pending_record(resolved_id, pending)
    await clear_pending_draft_id(resolved_id)
    patient_name = result[0] if result else None
    return {"ok": True, "patient_name": patient_name or ""}


@router.post("/api/manage/pending-record/abandon", include_in_schema=True)
async def abandon_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Abandon the pending record draft."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    pending_id = await get_pending_draft_id(resolved_id)
    if not pending_id:
        raise HTTPException(status_code=404, detail="No pending record")
    async with AsyncSessionLocal() as session:
        await abandon_pending_record(session, pending_id, doctor_id=resolved_id)
    await clear_pending_draft_id(resolved_id)
    return {"ok": True}


# ── Admin DB-view delegation ──────────────────────────────────────────────────

@router.get("/api/admin/db-view")
async def admin_db_view(
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_db_view_logic(doctor_id, patient_name, date_from, date_to, limit)


@router.get("/api/admin/tables")
async def admin_tables(
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_tables_logic(doctor_id, patient_name, date_from, date_to)


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
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_table_rows_logic(
        table_key, doctor_id, patient_name, date_from, date_to, limit, offset
    )
