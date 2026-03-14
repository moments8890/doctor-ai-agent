"""
管理后台 UI 路由：提供患者列表、病历查看、系统提示和可观测性数据的 Web API。
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from db.crud import (
    get_system_prompt,
    get_all_patients,
    get_records_for_patient,
    get_all_records_for_doctor,
    upsert_system_prompt,
    create_label,
    get_labels_for_doctor,
    update_label,
    delete_label,
    assign_label,
    remove_label,
    get_pending_record,
    confirm_pending_record,
    abandon_pending_record,
    get_cvd_context_for_patient,
    delete_patient_for_doctor,
)
from db.crud.records import delete_record
from db.crud.patient import search_patients_nl
from services.patient.nl_search import extract_criteria
from db.engine import AsyncSessionLocal
from db.models import (
    Doctor,
    DoctorContext,
    DoctorTask,
    MedicalRecordDB,
    Patient,
    PatientLabel,
    SystemPrompt,
)
from services.patient.patient_timeline import build_patient_timeline
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.observability.audit import audit
from utils.log import safe_create_task
from services.runtime.context import load_context, save_context, clear_pending_draft_id
from utils.errors import DomainError
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from channels.web.ui.record_handlers import (
    manage_records_for_doctor as _manage_records_for_doctor_impl,
    manage_patients_for_doctor as _manage_patients_for_doctor_impl,
    manage_patients_grouped_for_doctor as _manage_patients_grouped_for_doctor_impl,
    CATEGORY_ORDER as _CATEGORY_ORDER,
)
from channels.web.ui.admin_handlers import (
    admin_db_view_logic as _admin_db_view_logic,
    admin_tables_logic as _admin_tables_logic,
    admin_seed_samples_logic as _admin_seed_samples_logic,
)
from channels.web.ui.admin_table_rows import admin_table_rows_logic as _admin_table_rows_logic
from channels.web.ui import debug_handlers as _debug_handlers
from channels.web.ui import invite_handlers as _invite_handlers
from channels.web.ui import admin_config as _admin_config
from channels.web.ui._utils import (
    _fmt_ts,
    _normalize_date_yyyy_mm_dd,
    _parse_tags,
    _normalize_query_str,
    _resolve_ui_doctor_id,
    _require_ui_admin_access,
)
from services.observability.observability import (
    add_span,
    add_trace,
    clear_traces,
    get_latency_summary_scoped,
    get_recent_spans_scoped,
    get_recent_traces_scoped,
    get_slowest_spans_scoped,
    get_trace_timeline,
)
from utils.runtime_config import (
    apply_runtime_config,
    load_runtime_config_dict,
    runtime_config_source_path,
    save_runtime_config_dict,
    validate_runtime_config,
)
from channels.web.ui.admin_config import (
    RuntimeConfigUpdate,
    admin_observability,
    admin_clear_observability_traces,
    admin_seed_observability_samples,
    admin_get_runtime_config,
    admin_update_runtime_config,
    admin_verify_runtime_config,
    admin_apply_runtime_config,
    admin_get_tunnel_url,
    admin_filter_options,
    admin_get_keywords,
    admin_routing_metrics,
    admin_routing_metrics_reset,
)

router = APIRouter(tags=["ui"])
router.include_router(_debug_handlers.router)
router.include_router(_invite_handlers.router)
router.include_router(_admin_config.router)


class PromptUpdate(BaseModel):
    content: str


# Prompt keys that are used as .format() templates at runtime.
# Map key → set of required placeholder names.
_TEMPLATE_PLACEHOLDERS: dict[str, set[str]] = {
    "memory.compress": {"today"},
    "report.extract": {"records_text"},
}


def _validate_prompt_template(key: str, content: str) -> None:
    """Raise HTTPException if content breaks required format() placeholders."""
    required = _TEMPLATE_PLACEHOLDERS.get(key)
    if not required:
        return
    # Check that .format() with dummy values succeeds and all placeholders exist.
    test_kwargs = {p: "__TEST__" for p in required}
    try:
        formatted = content.format(**test_kwargs)
    except (KeyError, ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Prompt template error: {exc}. "
            f"Required placeholders for '{key}': {sorted(required)}",
        )
    for p in required:
        if f"__TEST__" not in formatted:
            raise HTTPException(
                status_code=422,
                detail=f"Missing required placeholder {{{p}}} in prompt '{key}'.",
            )


@router.get("/api/manage/patients")
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


@router.get("/api/manage/patients/grouped")
async def manage_patients_grouped(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_patients_grouped_for_doctor_impl(doctor_id)


@router.get("/api/manage/patients/search")
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


@router.get("/api/manage/patients/{patient_id}/timeline")
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


@router.get("/api/manage/patients/{patient_id}/cvd-context")
async def manage_patient_cvd_context(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """Return the most recent neurosurgical CVD clinical context for a patient."""
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as db:
        row = await get_cvd_context_for_patient(db, doctor_id, patient_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No CVD context found")
    import json as _json
    data = _json.loads(row.raw_json or "{}") if row.raw_json else {}
    return {
        "patient_id": patient_id,
        "record_id": row.record_id,
        "source": row.source,
        "created_at": _fmt_ts(row.created_at),
        **data,
    }


@router.get("/api/manage/records")
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


@router.get("/api/manage/prompts")
async def manage_prompts(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as db:
        base = await get_system_prompt(db, "structuring")
        ext = await get_system_prompt(db, "structuring.extension")
    return {
        "structuring": base.content if base else "",
        "structuring_extension": ext.content if ext else "",
    }


@router.put("/api/manage/prompts/{key}")
async def update_prompt(
    key: str,
    body: PromptUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    if key not in {"structuring", "structuring.extension"}:
        raise HTTPException(status_code=400, detail="Only structuring and structuring.extension are editable.")
    _validate_prompt_template(key, body.content)
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, body.content, changed_by="admin")
    return {"ok": True, "key": key}


@router.get("/api/admin/prompts", include_in_schema=False)
async def admin_get_prompts(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(SystemPrompt).order_by(SystemPrompt.key))).scalars().all()
    return {
        "prompts": [
            {"key": p.key, "content": p.content or "", "updated_at": _fmt_ts(p.updated_at)}
            for p in rows
        ]
    }


@router.put("/api/admin/prompts/{key}", include_in_schema=False)
async def admin_update_prompt(
    key: str,
    body: PromptUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    _validate_prompt_template(key, body.content)
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, body.content, changed_by="admin")
    return {"ok": True, "key": key}


@router.get("/api/admin/prompts/{key}/versions", include_in_schema=False)
async def admin_get_prompt_versions(
    key: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    limit: int = 20,
):
    """Return version history for a prompt key, newest first."""
    _require_ui_admin_access(x_admin_token)
    from db.crud.system import list_system_prompt_versions
    async with AsyncSessionLocal() as db:
        versions = await list_system_prompt_versions(db, key, limit=limit)
    return {
        "key": key,
        "versions": [
            {
                "id": v.id,
                "content": v.content or "",
                "changed_by": v.changed_by,
                "changed_at": _fmt_ts(v.changed_at),
            }
            for v in versions
        ],
    }


class PromptRollback(BaseModel):
    version_id: int


@router.post("/api/admin/prompts/{key}/rollback", include_in_schema=False)
async def admin_rollback_prompt(
    key: str,
    body: PromptRollback,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Restore a prompt to the content of a specific version entry."""
    _require_ui_admin_access(x_admin_token)
    from db.crud.system import rollback_system_prompt
    async with AsyncSessionLocal() as db:
        result = await rollback_system_prompt(db, key, body.version_id, changed_by="admin:rollback")
    if result is None:
        raise HTTPException(status_code=404, detail="Version not found or key mismatch")
    from utils.prompt_loader import invalidate
    invalidate(key)
    return {"ok": True, "key": key, "restored_from_version": body.version_id}


# ── Label endpoints ───────────────────────────────────────────────────────────

class LabelCreate(BaseModel):
    doctor_id: str
    name: str
    color: Optional[str] = None


class LabelUpdate(BaseModel):
    doctor_id: str
    name: Optional[str] = None
    color: Optional[str] = None


@router.get("/api/manage/labels")
async def list_labels(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.list")
    async with AsyncSessionLocal() as db:
        labels = await get_labels_for_doctor(db, doctor_id)
    return {
        "items": [
            {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}
            for lbl in labels
        ]
    }


@router.post("/api/manage/labels")
async def create_label_endpoint(body: LabelCreate, authorization: str | None = Header(default=None)):
    doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.create")
    async with AsyncSessionLocal() as db:
        lbl = await create_label(db, doctor_id, body.name, body.color)
    safe_create_task(audit(doctor_id, "WRITE", "label", str(lbl.id)))
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}


@router.patch("/api/manage/labels/{label_id}")
async def update_label_endpoint(label_id: int, body: LabelUpdate, authorization: str | None = Header(default=None)):
    doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.update")
    async with AsyncSessionLocal() as db:
        lbl = await update_label(db, label_id, doctor_id, name=body.name, color=body.color)
    if lbl is None:
        raise HTTPException(status_code=404, detail="Label not found")
    safe_create_task(audit(doctor_id, "WRITE", "label", str(label_id)))
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color}


class RecordUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    record_type: Optional[str] = None


@router.patch("/api/manage/records/{record_id}")
async def update_record(
    record_id: int,
    body: RecordUpdate,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.id == record_id,
                MedicalRecordDB.doctor_id == resolved_doctor_id,
            ).limit(1)
        )).scalar_one_or_none()
        if rec is None:
            raise HTTPException(status_code=404, detail="Record not found")
        updates = body.model_dump(exclude_unset=True)
        if "tags" in updates and isinstance(updates["tags"], list):
            import json as _json
            updates["tags"] = _json.dumps(updates["tags"], ensure_ascii=False)
        for field, value in updates.items():
            setattr(rec, field, value)
        rec.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(rec)
    return {
        "id": rec.id,
        "patient_id": rec.patient_id,
        "doctor_id": rec.doctor_id,
        "record_type": rec.record_type or "visit",
        "content": rec.content,
        "tags": _parse_tags(rec.tags),
        "created_at": _fmt_ts(rec.created_at),
        "updated_at": _fmt_ts(rec.updated_at),
    }


@router.delete("/api/manage/records/{record_id}")
async def delete_record_endpoint(
    record_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as db:
        deleted = await delete_record(db, resolved_doctor_id, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")
    safe_create_task(audit(resolved_doctor_id, "DELETE", "record", str(record_id)))
    return {"ok": True, "record_id": record_id}


@router.patch("/api/admin/records/{record_id}", include_in_schema=False)
async def admin_update_record(
    record_id: int,
    body: RecordUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    _ADMIN_RECORD_ALLOWED_FIELDS = {"content", "tags", "record_type"}
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == record_id).limit(1)
        )).scalar_one_or_none()
        if rec is None:
            raise HTTPException(status_code=404, detail="Record not found")
        updates = body.model_dump(exclude_unset=True)
        disallowed = set(updates.keys()) - _ADMIN_RECORD_ALLOWED_FIELDS
        if disallowed:
            raise HTTPException(status_code=422, detail=f"Cannot update fields: {sorted(disallowed)}")
        if "tags" in updates and isinstance(updates["tags"], list):
            import json as _json
            updates["tags"] = _json.dumps(updates["tags"], ensure_ascii=False)
        # Snapshot before mutation so admin edits appear in correction history.
        from db.crud.records import save_record_version
        await save_record_version(db, rec, rec.doctor_id)
        for field, value in updates.items():
            setattr(rec, field, value)
        rec.updated_at = datetime.now(timezone.utc)
        owner_doctor_id = rec.doctor_id
        await db.commit()
        await db.refresh(rec)
    safe_create_task(audit(
        owner_doctor_id, "ADMIN_UPDATE", resource_type="record", resource_id=str(record_id),
    ))
    return {
        "id": rec.id,
        "patient_id": rec.patient_id,
        "doctor_id": rec.doctor_id,
        "record_type": rec.record_type or "visit",
        "content": rec.content,
        "tags": _parse_tags(rec.tags),
        "created_at": _fmt_ts(rec.created_at),
        "updated_at": _fmt_ts(rec.updated_at),
    }


@router.delete("/api/manage/labels/{label_id}")
async def delete_label_endpoint(
    label_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.delete")
    async with AsyncSessionLocal() as db:
        found = await delete_label(db, label_id, doctor_id)
    if not found:
        raise HTTPException(status_code=404, detail="Label not found")
    safe_create_task(audit(doctor_id, "DELETE", "label", str(label_id)))
    return {"ok": True}


@router.delete("/api/manage/patients/{patient_id}")
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


@router.post("/api/manage/patients/{patient_id}/labels/{label_id}")
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


@router.delete("/api/manage/patients/{patient_id}/labels/{label_id}")
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


@router.get("/api/admin/db-view", include_in_schema=False)
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


@router.get("/api/admin/tables", include_in_schema=False)
async def admin_tables(
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    return await _admin_tables_logic(doctor_id, patient_name, date_from, date_to)


@router.get("/api/admin/tables/{table_key}", include_in_schema=False)
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


# ---------------------------------------------------------------------------
# Doctor working context — single lightweight endpoint for the workbench header
# ---------------------------------------------------------------------------

@router.get("/api/manage/working-context")
async def get_working_context(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the current working context for the doctor workbench header.

    Combines current patient, pending draft, and next-step state into one
    response so the UI can render the context header without multiple calls.
    """
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    ctx = await load_context(resolved_id)

    # Current patient
    current_patient = None
    if ctx.workflow.patient_id is not None:
        current_patient = {
            "id": ctx.workflow.patient_id,
            "name": ctx.workflow.patient_name or "",
        }

    # Pending draft
    pending_draft = None
    pending_id = ctx.workflow.pending_draft_id
    if pending_id:
        async with AsyncSessionLocal() as session:
            pending = await get_pending_record(session, pending_id, resolved_id)
        now = datetime.now(timezone.utc)
        _exp = pending.expires_at if pending else None
        if _exp and _exp.tzinfo is None:
            _exp = _exp.replace(tzinfo=timezone.utc)
        if pending and pending.status == "awaiting" and (not _exp or _exp >= now):
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


@router.post("/api/manage/clear-context")
async def clear_context_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Clear all working context for a doctor: current patient, pending draft,
    blocked write, pending create, candidate patient, and conversation history.

    Called when the user clears the chat in the UI so all state resets.
    """
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    from services.runtime.models import DoctorCtx
    ctx = await load_context(resolved_id)

    # Abandon pending draft if one exists
    if ctx.workflow.pending_draft_id:
        try:
            async with AsyncSessionLocal() as session:
                await abandon_pending_record(session, ctx.workflow.pending_draft_id, doctor_id=resolved_id)
        except Exception:
            pass

    # Reset context to empty state
    from services.runtime.models import WorkflowState, MemoryState
    ctx.workflow = WorkflowState()
    ctx.memory = MemoryState()
    await save_context(ctx)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Pending record confirmation endpoints (web UI ↔ AI confirmation gate)
# ---------------------------------------------------------------------------

@router.get("/api/manage/pending-record")
async def get_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the current pending record draft for a doctor, or null if none."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    ctx = await load_context(resolved_id)
    pending_id = ctx.workflow.pending_draft_id
    if not pending_id:
        return None
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, resolved_id)
    if pending is None or pending.status != "awaiting":
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
        content_preview = raw_content[:100] + ("…" if len(raw_content) > 100 else "")
    except Exception:
        content_preview = ""
    return {
        "id": pending.id,
        "patient_name": pending.patient_name or "未关联",
        "content_preview": content_preview,
        "created_at": pending.created_at.isoformat() if pending.created_at else None,
        "expires_at": pending.expires_at.isoformat() if pending.expires_at else None,
    }


@router.post("/api/manage/pending-record/confirm")
async def confirm_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Confirm the pending record draft → save to medical_records."""
    from services.domain.intent_handlers import save_pending_record
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    ctx = await load_context(resolved_id)
    pending_id = ctx.workflow.pending_draft_id
    if not pending_id:
        raise HTTPException(status_code=404, detail="No pending record")
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, resolved_id)
    if pending is None or pending.status != "awaiting":
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


@router.post("/api/manage/pending-record/abandon")
async def abandon_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Abandon the pending record draft."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    ctx = await load_context(resolved_id)
    pending_id = ctx.workflow.pending_draft_id
    if not pending_id:
        raise HTTPException(status_code=404, detail="No pending record")
    async with AsyncSessionLocal() as session:
        await abandon_pending_record(session, pending_id, doctor_id=resolved_id)
    await clear_pending_draft_id(resolved_id)
    return {"ok": True}


# ─── Doctor profile ──────────────────────────────────────────────────────────

class DoctorProfileUpdate(BaseModel):
    name: str
    specialty: Optional[str] = None


@router.get("/api/manage/profile")
async def get_doctor_profile(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the doctor's display name, specialty, and onboarding status."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Doctor).where(Doctor.doctor_id == resolved_id))
        doctor = result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")

    name = doctor.name or ""
    specialty = getattr(doctor, "specialty", None) or ""
    onboarded = bool(name and name != resolved_id)
    return {
        "doctor_id": resolved_id,
        "name": name,
        "specialty": specialty,
        "onboarded": onboarded,
    }


@router.patch("/api/manage/profile")
async def patch_doctor_profile(
    body: DoctorProfileUpdate,
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Update the doctor's display name and specialty."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Doctor).where(Doctor.doctor_id == resolved_id))
        doctor = result.scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status_code=404, detail="Doctor not found")
        doctor.name = name
        try:
            doctor.specialty = body.specialty or None
        except Exception:
            pass  # specialty column not yet migrated — skip
        await db.commit()

    return {"ok": True, "name": name, "specialty": body.specialty or ""}
