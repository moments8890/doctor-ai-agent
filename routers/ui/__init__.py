"""
管理后台 UI 路由：提供患者列表、病历查看、系统提示和可观测性数据的 Web API。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from db.crud import (
    get_all_records_for_doctor,
    get_system_prompt,
    get_records_for_patient,
    get_all_patients,
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
)
from db.engine import AsyncSessionLocal
from db.models import (
    AuditLog,
    ChatArchive,
    Doctor,
    DoctorContext,
    DoctorKnowledgeItem,
    DoctorSessionState,
    DoctorTask,
    InviteCode,
    MedicalRecordDB,
    MedicalRecordExport,
    MedicalRecordVersion,
    NeuroCaseDB,
    NeuroCVDContext,
    Patient,
    PatientLabel,
    PendingMessage,
    PendingRecord,
    SpecialtyScore,
    SystemPrompt,
    SystemPromptVersion,
    patient_label_assignments,
)
from services.patient.patient_timeline import build_patient_timeline
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
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.session import get_session, clear_pending_record_id
from utils.errors import DomainError
from utils.runtime_config import (
    apply_runtime_config,
    load_runtime_config_dict,
    runtime_config_categories,
    runtime_config_source_path,
    save_runtime_config_dict,
    validate_runtime_config,
)
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from routers.ui._utils import (
    _extract_tunnel_url_from_log,
    _fmt_ts,
    _parse_tags,
    _parse_bool,
    _normalize_query_str,
    _normalize_date_yyyy_mm_dd,
    _resolve_ui_doctor_id,
    _require_ui_admin_access,
    _require_ui_debug_access,
    _parse_admin_filters,
    _apply_created_at_filters,
    apply_exclude_test_doctors,
)

router = APIRouter(tags=["ui"])


class PromptUpdate(BaseModel):
    content: str


class RuntimeConfigUpdate(BaseModel):
    config: dict


@router.get("/api/manage/patients")
async def manage_patients(
    doctor_id: str = Query(default="web_doctor"),
    category: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    authorization: str | None = Header(default=None),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    return await _manage_patients_for_doctor(
        resolved_doctor_id,
        category=category,
        limit=limit,
        offset=offset,
    )


async def _manage_patients_for_doctor(
    doctor_id: str,
    *,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_patients")
    category = _normalize_query_str(category)

    async with AsyncSessionLocal() as db:
        patients = await get_all_patients(db, doctor_id)
        counts_result = await db.execute(
            select(MedicalRecordDB.patient_id, func.count(MedicalRecordDB.id))
            .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id.is_not(None))
            .group_by(MedicalRecordDB.patient_id)
        )
        count_map = {pid: count for pid, count in counts_result.all()}

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

    if category is not None:
        items = [item for item in items if item["primary_category"] == category]

    total = len(items)
    return {"doctor_id": doctor_id, "items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}


_CATEGORY_ORDER = ["high_risk", "active_followup", "stable", "new", "uncategorized"]


@router.get("/api/manage/patients/grouped")
async def manage_patients_grouped(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_patients_grouped")
    async with AsyncSessionLocal() as db:
        patients = await get_all_patients(db, doctor_id)
        counts_result = await db.execute(
            select(MedicalRecordDB.patient_id, func.count(MedicalRecordDB.id))
            .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id.is_not(None))
            .group_by(MedicalRecordDB.patient_id)
        )
        count_map = {pid: count for pid, count in counts_result.all()}

    all_items = [
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

    bucket: dict = {cat: [] for cat in _CATEGORY_ORDER}
    for item in all_items:
        cat = item["primary_category"] or "uncategorized"
        if cat not in bucket:
            cat = "uncategorized"
        bucket[cat].append(item)

    groups = [
        {"group": cat, "count": len(bucket[cat]), "items": bucket[cat]}
        for cat in _CATEGORY_ORDER
    ]

    return {"doctor_id": doctor_id, "groups": groups}



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
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_records")
    patient_name = _normalize_query_str(patient_name)
    date_from = _normalize_date_yyyy_mm_dd(date_from)
    date_to = _normalize_date_yyyy_mm_dd(date_to)

    async with AsyncSessionLocal() as db:
        if patient_id is not None:
            records = await get_records_for_patient(db, doctor_id, patient_id, limit=limit)
            patient_name = None
            patients = await get_all_patients(db, doctor_id)
            for p in patients:
                if p.id == patient_id:
                    patient_name = p.name
                    break
            items = [
                {
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "doctor_id": r.doctor_id,
                    "patient_name": patient_name,
                    "record_type": r.record_type or "visit",
                    "content": r.content,
                    "tags": _parse_tags(r.tags),
                    "encounter_type": r.encounter_type or "unknown",
                    "created_at": _fmt_ts(r.created_at),
                    "updated_at": _fmt_ts(r.updated_at),
                }
                for r in records
            ]
        else:
            records = await get_all_records_for_doctor(db, doctor_id, limit=limit)
            items = [
                {
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "doctor_id": r.doctor_id,
                    "patient_name": r.patient.name if r.patient else None,
                    "record_type": r.record_type or "visit",
                    "content": r.content,
                    "tags": _parse_tags(r.tags),
                    "encounter_type": r.encounter_type or "unknown",
                    "created_at": _fmt_ts(r.created_at),
                    "updated_at": _fmt_ts(r.updated_at),
                }
                for r in records
            ]

    if patient_name:
        needle = patient_name.strip().lower()
        items = [item for item in items if item.get("patient_name") and needle in str(item["patient_name"]).lower()]

    if date_from:
        items = [item for item in items if item.get("created_at") and str(item["created_at"])[:10] >= date_from]

    if date_to:
        items = [item for item in items if item.get("created_at") and str(item["created_at"])[:10] <= date_to]

    total = len(items)
    return {"doctor_id": doctor_id, "items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}


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
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, body.content)
    return {"ok": True, "key": key}


@router.get("/api/admin/prompts")
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


@router.put("/api/admin/prompts/{key}")
async def admin_update_prompt(
    key: str,
    body: PromptUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, body.content)
    return {"ok": True, "key": key}


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
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}


@router.patch("/api/manage/labels/{label_id}")
async def update_label_endpoint(label_id: int, body: LabelUpdate, authorization: str | None = Header(default=None)):
    doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.update")
    async with AsyncSessionLocal() as db:
        lbl = await update_label(db, label_id, doctor_id, name=body.name, color=body.color)
    if lbl is None:
        raise HTTPException(status_code=404, detail="Label not found")
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


@router.patch("/api/admin/records/{record_id}")
async def admin_update_record(
    record_id: int,
    body: RecordUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(
            select(MedicalRecordDB).where(MedicalRecordDB.id == record_id).limit(1)
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
    return {"ok": True}


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
            raise HTTPException(status_code=exc.status_code, detail=str(exc))
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
            raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return {"ok": True}


@router.get("/api/admin/observability")
async def admin_observability(
    trace_limit: int = 100,
    summary_limit: int = 500,
    span_limit: int = 200,
    slow_span_limit: int = 30,
    scope: str = "all",
    trace_id: str | None = None,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    safe_scope = scope if scope in {"all", "public", "internal"} else "all"
    payload = {
        "scope": safe_scope,
        "summary": get_latency_summary_scoped(limit=summary_limit, scope=safe_scope),
        "recent_traces": get_recent_traces_scoped(limit=trace_limit, scope=safe_scope),
        "recent_spans": get_recent_spans_scoped(limit=span_limit, trace_id=trace_id, scope=safe_scope),
        "slow_spans": get_slowest_spans_scoped(limit=slow_span_limit, scope=safe_scope),
        "split": {
            "public": get_latency_summary_scoped(limit=summary_limit, scope="public"),
            "internal": get_latency_summary_scoped(limit=summary_limit, scope="internal"),
        },
    }
    if trace_id:
        payload["trace_timeline"] = get_trace_timeline(trace_id=trace_id, limit=span_limit)
    return payload


@router.delete("/api/admin/observability/traces")
async def admin_clear_observability_traces(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    clear_traces()
    return {"ok": True}


@router.get("/api/admin/routing-metrics")
async def admin_routing_metrics(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Fast-router vs LLM hit counts since last process start."""
    _require_ui_admin_access(x_admin_token)
    from services.observability.routing_metrics import get_metrics
    return get_metrics()


@router.post("/api/admin/routing-metrics/reset")
async def admin_routing_metrics_reset(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Reset routing counters to zero."""
    _require_ui_admin_access(x_admin_token)
    from services.observability.routing_metrics import reset
    reset()
    return {"ok": True}


@router.post("/api/admin/observability/sample")
async def admin_seed_observability_samples(
    count: int = Query(default=3, ge=1, le=20),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    now = datetime.now(timezone.utc)
    created: list[str] = []
    for i in range(count):
        trace_id = str(uuid.uuid4())
        created.append(trace_id)
        started = now - timedelta(seconds=(count - i))
        total_ms = 1200.0 + i * 180.0
        llm_ms = max(200.0, total_ms - 180.0)
        status_code = 200 if i % 4 != 3 else 500
        add_trace(
            trace_id=trace_id,
            started_at=started,
            method="POST",
            path="/api/records/chat",
            status_code=status_code,
            latency_ms=total_ms,
        )
        root_span_id = uuid.uuid4().hex[:12]
        add_span(
            trace_id=trace_id,
            span_id=root_span_id,
            parent_span_id=None,
            layer="router",
            name="records.chat.agent_dispatch",
            started_at=started,
            latency_ms=llm_ms + 12.0,
            status="ok" if status_code < 500 else "error",
            meta={"sample": True},
        )
        add_span(
            trace_id=trace_id,
            parent_span_id=root_span_id,
            layer="llm",
            name="agent.chat_completion",
            started_at=started + timedelta(milliseconds=6),
            latency_ms=llm_ms,
            status="ok" if status_code < 500 else "error",
            meta={"provider": "sample"},
        )
        persist_span_id = uuid.uuid4().hex[:12]
        add_span(
            trace_id=trace_id,
            span_id=persist_span_id,
            parent_span_id=None,
            layer="router",
            name="records.chat.persist_record",
            started_at=started + timedelta(milliseconds=llm_ms + 20),
            latency_ms=56.0,
            status="ok",
            meta={"sample": True},
        )
        add_span(
            trace_id=trace_id,
            parent_span_id=persist_span_id,
            layer="db",
            name="crud.save_record",
            started_at=started + timedelta(milliseconds=llm_ms + 26),
            latency_ms=18.0,
            status="ok",
            meta={"sample": True},
        )
    return {"ok": True, "count": len(created), "trace_ids": created}


@router.get("/api/admin/config")
async def admin_get_runtime_config(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    config = await load_runtime_config_dict()
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(config)
    return {"source": source, "config": config, "categories": categories}


@router.put("/api/admin/config")
async def admin_update_runtime_config(
    body: RuntimeConfigUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    if not isinstance(body.config, dict):
        raise HTTPException(status_code=400, detail="config must be a JSON object")
    saved = await save_runtime_config_dict(body.config)
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(saved)
    return {"ok": True, "applied": False, "source": source, "config": saved, "categories": categories}


@router.post("/api/admin/config/verify")
async def admin_verify_runtime_config(
    body: RuntimeConfigUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    result = validate_runtime_config(body.config)
    categories = runtime_config_categories(result.get("sanitized", {}))
    return {
        "ok": result.get("ok", False),
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
        "config": result.get("sanitized", {}),
        "categories": categories,
    }


@router.post("/api/admin/config/apply")
async def admin_apply_runtime_config(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    saved = await load_runtime_config_dict()
    await apply_runtime_config(saved)
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(saved)
    return {"ok": True, "applied": True, "source": source, "config": saved, "categories": categories}


@router.get("/api/admin/dev/tunnel-url")
async def admin_get_tunnel_url(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    _app_root = Path(__file__).resolve().parents[1]
    log_path_raw = (
        os.environ.get("CLOUDFLARED_LOG_PATH")
        or os.environ.get("TUNNEL_LOG_PATH")
        or str(_app_root / "logs" / "tunnel.log")
    )
    log_path = Path(log_path_raw).expanduser()
    if not log_path.exists():
        return {"ok": False, "url": None, "source": str(log_path), "detail": "log file not found"}

    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return {"ok": False, "url": None, "source": str(log_path), "detail": "read failed"}

    url = _extract_tunnel_url_from_log(content)
    mtime = datetime.fromtimestamp(log_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "ok": bool(url),
        "url": url,
        "source": str(log_path),
        "updated_at": mtime,
        "detail": None if url else "no public tunnel url found in log",
    }


@router.get("/api/admin/filter-options")
async def admin_filter_options(
    doctor_id: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    doctor_id = _normalize_query_str(doctor_id)

    async with AsyncSessionLocal() as db:
        doctor_candidates = set()
        doctor_sources = [
            Doctor.doctor_id,
            Patient.doctor_id,
            MedicalRecordDB.doctor_id,
            DoctorTask.doctor_id,
            NeuroCaseDB.doctor_id,
            DoctorContext.doctor_id,
            PatientLabel.doctor_id,
        ]
        for col in doctor_sources:
            stmt = select(col).where(col.is_not(None))
            stmt = apply_exclude_test_doctors(stmt, col)
            rows = (await db.execute(stmt)).scalars().all()
            for value in rows:
                if isinstance(value, str) and value.strip():
                    doctor_candidates.add(value.strip())

        patient_stmt = select(Patient.name).where(Patient.name.is_not(None))
        if doctor_id:
            patient_stmt = patient_stmt.where(Patient.doctor_id == doctor_id)
        else:
            patient_stmt = apply_exclude_test_doctors(patient_stmt, Patient.doctor_id)
        patient_rows = (await db.execute(patient_stmt)).scalars().all()

    return {
        "doctor_ids": sorted(doctor_candidates),
        "patient_names": sorted({p.strip() for p in patient_rows if isinstance(p, str) and p.strip()}),
        "selected_doctor_id": doctor_id,
    }


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
    doctor_id = _normalize_query_str(doctor_id)
    patient_name = _normalize_query_str(patient_name)
    date_from = _normalize_date_yyyy_mm_dd(date_from)
    date_to = _normalize_date_yyyy_mm_dd(date_to)

    dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt_to_exclusive = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1) if date_to else None

    patient_stmt = select(Patient).order_by(Patient.created_at.desc()).limit(limit)
    record_stmt = (
        select(MedicalRecordDB, Patient.name.label("patient_name"))
        .outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit)
    )

    if doctor_id:
        patient_stmt = patient_stmt.where(Patient.doctor_id == doctor_id)
        record_stmt = record_stmt.where(MedicalRecordDB.doctor_id == doctor_id)
    else:
        patient_stmt = apply_exclude_test_doctors(patient_stmt, Patient.doctor_id)
        record_stmt = apply_exclude_test_doctors(record_stmt, MedicalRecordDB.doctor_id)
    if patient_name:
        needle = f"%{patient_name.strip()}%"
        patient_stmt = patient_stmt.where(Patient.name.ilike(needle))
        record_stmt = record_stmt.where(Patient.name.ilike(needle))
    if dt_from is not None:
        record_stmt = record_stmt.where(MedicalRecordDB.created_at >= dt_from)
    if dt_to_exclusive is not None:
        record_stmt = record_stmt.where(MedicalRecordDB.created_at < dt_to_exclusive)

    async with AsyncSessionLocal() as db:
        patients = (await db.execute(patient_stmt)).scalars().all()
        records = (await db.execute(record_stmt)).all()

    patient_items = [
        {
            "id": p.id,
            "doctor_id": p.doctor_id,
            "name": p.name,
            "gender": p.gender,
            "year_of_birth": p.year_of_birth,
            "created_at": _fmt_ts(p.created_at),
        }
        for p in patients
    ]
    record_items = [
        {
            "id": record.id,
            "patient_id": record.patient_id,
            "doctor_id": record.doctor_id,
            "patient_name": patient_name_value,
            "record_type": record.record_type or "visit",
            "content": record.content,
            "tags": _parse_tags(record.tags),
            "encounter_type": record.encounter_type or "unknown",
            "created_at": _fmt_ts(record.created_at),
            "updated_at": _fmt_ts(record.updated_at),
        }
        for record, patient_name_value in records
    ]

    return {
        "filters": {
            "doctor_id": doctor_id,
            "patient_name": patient_name,
            "date_from": date_from,
            "date_to": date_to,
            "limit": limit,
        },
        "counts": {"patients": len(patient_items), "records": len(record_items)},
        "patients": patient_items,
        "records": record_items,
    }


@router.get("/api/admin/tables")
async def admin_tables(
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    doctor_id, patient_name, _, _, dt_from, dt_to_exclusive = _parse_admin_filters(
        doctor_id, patient_name, date_from, date_to
    )
    needle = f"%{patient_name.strip()}%" if patient_name and patient_name.strip() else None

    counts = {
        "doctors": 0, "patients": 0, "medical_records": 0, "doctor_tasks": 0,
        "neuro_cases": 0, "neuro_cvd_context": 0, "specialty_scores": 0,
        "medical_record_versions": 0, "medical_record_exports": 0,
        "pending_records": 0, "pending_messages": 0, "audit_log": 0,
        "doctor_knowledge_items": 0, "patient_labels": 0,
        "patient_label_assignments": 0, "system_prompts": 0,
        "system_prompt_versions": 0, "doctor_contexts": 0,
        "doctor_session_states": 0, "chat_archive": 0,
    }

    async with AsyncSessionLocal() as db:
        doctors_stmt = select(func.count(Doctor.doctor_id))
        if doctor_id:
            doctors_stmt = doctors_stmt.where(Doctor.doctor_id == doctor_id)
        else:
            doctors_stmt = apply_exclude_test_doctors(doctors_stmt, Doctor.doctor_id)
        counts["doctors"] = int((await db.execute(doctors_stmt)).scalar() or 0)

        patients_stmt = select(func.count(Patient.id))
        patients_stmt = _apply_created_at_filters(patients_stmt, Patient, dt_from, dt_to_exclusive)
        if doctor_id:
            patients_stmt = patients_stmt.where(Patient.doctor_id == doctor_id)
        else:
            patients_stmt = apply_exclude_test_doctors(patients_stmt, Patient.doctor_id)
        if needle:
            patients_stmt = patients_stmt.where(Patient.name.ilike(needle))
        counts["patients"] = int((await db.execute(patients_stmt)).scalar() or 0)

        records_stmt = select(func.count(MedicalRecordDB.id)).outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
        records_stmt = _apply_created_at_filters(records_stmt, MedicalRecordDB, dt_from, dt_to_exclusive)
        if doctor_id:
            records_stmt = records_stmt.where(MedicalRecordDB.doctor_id == doctor_id)
        else:
            records_stmt = apply_exclude_test_doctors(records_stmt, MedicalRecordDB.doctor_id)
        if needle:
            records_stmt = records_stmt.where(Patient.name.ilike(needle))
        counts["medical_records"] = int((await db.execute(records_stmt)).scalar() or 0)

        tasks_stmt = select(func.count(DoctorTask.id)).outerjoin(Patient, DoctorTask.patient_id == Patient.id)
        tasks_stmt = _apply_created_at_filters(tasks_stmt, DoctorTask, dt_from, dt_to_exclusive)
        if doctor_id:
            tasks_stmt = tasks_stmt.where(DoctorTask.doctor_id == doctor_id)
        else:
            tasks_stmt = apply_exclude_test_doctors(tasks_stmt, DoctorTask.doctor_id)
        if needle:
            tasks_stmt = tasks_stmt.where(Patient.name.ilike(needle))
        counts["doctor_tasks"] = int((await db.execute(tasks_stmt)).scalar() or 0)

        neuro_stmt = select(func.count(NeuroCaseDB.id))
        neuro_stmt = _apply_created_at_filters(neuro_stmt, NeuroCaseDB, dt_from, dt_to_exclusive)
        if doctor_id:
            neuro_stmt = neuro_stmt.where(NeuroCaseDB.doctor_id == doctor_id)
        else:
            neuro_stmt = apply_exclude_test_doctors(neuro_stmt, NeuroCaseDB.doctor_id)
        if needle:
            neuro_stmt = neuro_stmt.where(NeuroCaseDB.patient_name.ilike(needle))
        counts["neuro_cases"] = int((await db.execute(neuro_stmt)).scalar() or 0)

        labels_stmt = select(func.count(PatientLabel.id))
        labels_stmt = _apply_created_at_filters(labels_stmt, PatientLabel, dt_from, dt_to_exclusive)
        if doctor_id:
            labels_stmt = labels_stmt.where(PatientLabel.doctor_id == doctor_id)
        else:
            labels_stmt = apply_exclude_test_doctors(labels_stmt, PatientLabel.doctor_id)
        counts["patient_labels"] = int((await db.execute(labels_stmt)).scalar() or 0)

        assignments_stmt = (
            select(func.count())
            .select_from(patient_label_assignments)
            .join(PatientLabel, patient_label_assignments.c.label_id == PatientLabel.id)
            .join(Patient, patient_label_assignments.c.patient_id == Patient.id)
        )
        if doctor_id:
            assignments_stmt = assignments_stmt.where(PatientLabel.doctor_id == doctor_id)
        else:
            assignments_stmt = apply_exclude_test_doctors(assignments_stmt, PatientLabel.doctor_id)
        if needle:
            assignments_stmt = assignments_stmt.where(Patient.name.ilike(needle))
        counts["patient_label_assignments"] = int((await db.execute(assignments_stmt)).scalar() or 0)

        prompts_stmt = select(func.count(SystemPrompt.key))
        counts["system_prompts"] = int((await db.execute(prompts_stmt)).scalar() or 0)

        context_stmt = select(func.count(DoctorContext.doctor_id))
        if doctor_id:
            context_stmt = context_stmt.where(DoctorContext.doctor_id == doctor_id)
        else:
            context_stmt = apply_exclude_test_doctors(context_stmt, DoctorContext.doctor_id)
        counts["doctor_contexts"] = int((await db.execute(context_stmt)).scalar() or 0)

        # new tables
        for model, key, col in [
            (NeuroCVDContext, "neuro_cvd_context", NeuroCVDContext.doctor_id),
            (SpecialtyScore, "specialty_scores", SpecialtyScore.doctor_id),
            (MedicalRecordVersion, "medical_record_versions", MedicalRecordVersion.doctor_id),
            (MedicalRecordExport, "medical_record_exports", MedicalRecordExport.doctor_id),
            (PendingRecord, "pending_records", PendingRecord.doctor_id),
            (PendingMessage, "pending_messages", PendingMessage.doctor_id),
            (AuditLog, "audit_log", AuditLog.doctor_id),
            (DoctorKnowledgeItem, "doctor_knowledge_items", DoctorKnowledgeItem.doctor_id),
            (DoctorSessionState, "doctor_session_states", DoctorSessionState.doctor_id),
            (ChatArchive, "chat_archive", ChatArchive.doctor_id),
        ]:
            s = select(func.count()).select_from(model)
            if doctor_id:
                s = s.where(col == doctor_id)
            else:
                s = apply_exclude_test_doctors(s, col)
            counts[key] = int((await db.execute(s)).scalar() or 0)

        spv_s = select(func.count(SystemPromptVersion.id))
        counts["system_prompt_versions"] = int((await db.execute(spv_s)).scalar() or 0)

    ordered = [
        "doctors", "patients", "medical_records", "medical_record_versions",
        "medical_record_exports", "doctor_tasks", "neuro_cases", "neuro_cvd_context",
        "specialty_scores", "pending_records", "pending_messages", "audit_log",
        "doctor_knowledge_items", "patient_labels", "patient_label_assignments",
        "system_prompts", "system_prompt_versions", "doctor_contexts",
        "doctor_session_states", "chat_archive",
    ]
    return {"items": [{"key": key, "count": counts[key]} for key in ordered]}


@router.get("/api/admin/tables/{table_key}")
async def admin_table_rows(
    table_key: str,
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    doctor_id, patient_name, _, _, dt_from, dt_to_exclusive = _parse_admin_filters(
        doctor_id, patient_name, date_from, date_to
    )
    needle = f"%{patient_name.strip()}%" if patient_name and patient_name.strip() else None

    async with AsyncSessionLocal() as db:
        if table_key == "doctors":
            stmt = select(Doctor).order_by(Doctor.updated_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(Doctor.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, Doctor.doctor_id)
            items = [
                {
                    "doctor_id": d.doctor_id,
                    "name": d.name,
                    "created_at": _fmt_ts(d.created_at),
                    "updated_at": _fmt_ts(d.updated_at),
                }
                for d in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "patients":
            stmt = select(Patient).order_by(Patient.created_at.desc()).limit(limit)
            stmt = _apply_created_at_filters(stmt, Patient, dt_from, dt_to_exclusive)
            if doctor_id:
                stmt = stmt.where(Patient.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, Patient.doctor_id)
            if needle:
                stmt = stmt.where(Patient.name.ilike(needle))
            items = [
                {
                    "id": p.id,
                    "doctor_id": p.doctor_id,
                    "name": p.name,
                    "gender": p.gender,
                    "year_of_birth": p.year_of_birth,
                    "created_at": _fmt_ts(p.created_at),
                }
                for p in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "medical_records":
            stmt = (
                select(MedicalRecordDB, Patient.name.label("patient_name"))
                .outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
                .order_by(MedicalRecordDB.created_at.desc())
                .limit(limit)
            )
            stmt = _apply_created_at_filters(stmt, MedicalRecordDB, dt_from, dt_to_exclusive)
            if doctor_id:
                stmt = stmt.where(MedicalRecordDB.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, MedicalRecordDB.doctor_id)
            if needle:
                stmt = stmt.where(Patient.name.ilike(needle))
            items = [
                {
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "doctor_id": r.doctor_id,
                    "patient_name": pname,
                    "record_type": r.record_type or "visit",
                    "content": r.content,
                    "tags": _parse_tags(r.tags),
                    "created_at": _fmt_ts(r.created_at),
                }
                for r, pname in (await db.execute(stmt)).all()
            ]
        elif table_key == "doctor_tasks":
            stmt = (
                select(DoctorTask, Patient.name.label("patient_name"))
                .outerjoin(Patient, DoctorTask.patient_id == Patient.id)
                .order_by(DoctorTask.created_at.desc())
                .limit(limit)
            )
            stmt = _apply_created_at_filters(stmt, DoctorTask, dt_from, dt_to_exclusive)
            if doctor_id:
                stmt = stmt.where(DoctorTask.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, DoctorTask.doctor_id)
            if needle:
                stmt = stmt.where(Patient.name.ilike(needle))
            items = [
                {
                    "id": t.id,
                    "doctor_id": t.doctor_id,
                    "patient_id": t.patient_id,
                    "patient_name": pname,
                    "task_type": t.task_type,
                    "title": t.title,
                    "status": t.status,
                    "due_at": _fmt_ts(t.due_at),
                    "record_id": t.record_id,
                    "updated_at": _fmt_ts(t.updated_at),
                    "created_at": _fmt_ts(t.created_at),
                }
                for t, pname in (await db.execute(stmt)).all()
            ]
        elif table_key == "neuro_cases":
            stmt = select(NeuroCaseDB).order_by(NeuroCaseDB.created_at.desc()).limit(limit)
            stmt = _apply_created_at_filters(stmt, NeuroCaseDB, dt_from, dt_to_exclusive)
            if doctor_id:
                stmt = stmt.where(NeuroCaseDB.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, NeuroCaseDB.doctor_id)
            if needle:
                stmt = stmt.where(NeuroCaseDB.patient_name.ilike(needle))
            items = [
                {
                    "id": n.id,
                    "doctor_id": n.doctor_id,
                    "patient_id": n.patient_id,
                    "patient_name": n.patient_name,
                    "nihss": n.nihss,
                    "created_at": _fmt_ts(n.created_at),
                }
                for n in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "patient_labels":
            stmt = select(PatientLabel).order_by(PatientLabel.created_at.desc()).limit(limit)
            stmt = _apply_created_at_filters(stmt, PatientLabel, dt_from, dt_to_exclusive)
            if doctor_id:
                stmt = stmt.where(PatientLabel.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, PatientLabel.doctor_id)
            items = [
                {
                    "id": l.id,
                    "doctor_id": l.doctor_id,
                    "name": l.name,
                    "color": l.color,
                    "created_at": _fmt_ts(l.created_at),
                }
                for l in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "patient_label_assignments":
            stmt = (
                select(
                    patient_label_assignments.c.patient_id,
                    patient_label_assignments.c.label_id,
                    Patient.name.label("patient_name"),
                    PatientLabel.name.label("label_name"),
                    PatientLabel.doctor_id.label("doctor_id"),
                )
                .select_from(patient_label_assignments)
                .join(Patient, patient_label_assignments.c.patient_id == Patient.id)
                .join(PatientLabel, patient_label_assignments.c.label_id == PatientLabel.id)
                .limit(limit)
            )
            if doctor_id:
                stmt = stmt.where(PatientLabel.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, PatientLabel.doctor_id)
            if needle:
                stmt = stmt.where(Patient.name.ilike(needle))
            items = [
                {
                    "patient_id": pid,
                    "label_id": lid,
                    "patient_name": pname,
                    "label_name": lname,
                    "doctor_id": did,
                }
                for pid, lid, pname, lname, did in (await db.execute(stmt)).all()
            ]
        elif table_key == "system_prompts":
            stmt = select(SystemPrompt).order_by(SystemPrompt.updated_at.desc()).limit(limit)
            items = [
                {
                    "key": p.key,
                    "content": p.content,
                    "updated_at": _fmt_ts(p.updated_at),
                }
                for p in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "doctor_contexts":
            stmt = select(DoctorContext).order_by(DoctorContext.updated_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(DoctorContext.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, DoctorContext.doctor_id)
            items = [
                {"doctor_id": c.doctor_id, "summary": c.summary, "updated_at": _fmt_ts(c.updated_at)}
                for c in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "neuro_cvd_context":
            stmt = (
                select(NeuroCVDContext, Patient.name.label("patient_name"))
                .outerjoin(Patient, NeuroCVDContext.patient_id == Patient.id)
                .order_by(NeuroCVDContext.created_at.desc()).limit(limit)
            )
            if doctor_id:
                stmt = stmt.where(NeuroCVDContext.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, NeuroCVDContext.doctor_id)
            if needle:
                stmt = stmt.where(Patient.name.ilike(needle))
            import json as _json
            items = [
                {
                    "id": r.id, "doctor_id": r.doctor_id, "patient_id": r.patient_id,
                    "patient_name": pname, "record_id": r.record_id,
                    "diagnosis_subtype": r.diagnosis_subtype, "surgery_status": r.surgery_status,
                    "source": r.source, "created_at": _fmt_ts(r.created_at),
                    "updated_at": _fmt_ts(r.updated_at),
                    **(_json.loads(r.raw_json) if r.raw_json else {}),
                }
                for r, pname in (await db.execute(stmt)).all()
            ]
        elif table_key == "specialty_scores":
            stmt = select(SpecialtyScore).order_by(SpecialtyScore.id.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(SpecialtyScore.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, SpecialtyScore.doctor_id)
            items = [
                {
                    "id": s.id, "record_id": s.record_id, "doctor_id": s.doctor_id,
                    "score_type": s.score_type, "score_value": s.score_value, "raw_text": s.raw_text,
                    "patient_id": getattr(s, "patient_id", None),
                    "extracted_at": _fmt_ts(getattr(s, "extracted_at", None)),
                }
                for s in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "medical_record_versions":
            stmt = select(MedicalRecordVersion).order_by(MedicalRecordVersion.changed_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(MedicalRecordVersion.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, MedicalRecordVersion.doctor_id)
            items = [
                {
                    "id": v.id, "record_id": v.record_id, "doctor_id": v.doctor_id,
                    "old_content": v.old_content, "old_tags": _parse_tags(v.old_tags),
                    "old_record_type": v.old_record_type, "changed_at": _fmt_ts(v.changed_at),
                }
                for v in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "medical_record_exports":
            stmt = select(MedicalRecordExport).order_by(MedicalRecordExport.exported_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(MedicalRecordExport.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, MedicalRecordExport.doctor_id)
            items = [
                {
                    "id": e.id, "record_id": e.record_id, "doctor_id": e.doctor_id,
                    "export_format": e.export_format, "pdf_hash": e.pdf_hash,
                    "exported_at": _fmt_ts(e.exported_at),
                }
                for e in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "pending_records":
            stmt = select(PendingRecord).order_by(PendingRecord.created_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(PendingRecord.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, PendingRecord.doctor_id)
            if needle:
                stmt = stmt.where(PendingRecord.patient_name.ilike(needle))
            items = [
                {
                    "id": p.id, "doctor_id": p.doctor_id, "patient_id": p.patient_id,
                    "patient_name": p.patient_name, "status": p.status,
                    "raw_input": p.raw_input, "created_at": _fmt_ts(p.created_at),
                    "expires_at": _fmt_ts(p.expires_at),
                }
                for p in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "pending_messages":
            stmt = select(PendingMessage).order_by(PendingMessage.created_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(PendingMessage.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, PendingMessage.doctor_id)
            items = [
                {
                    "id": p.id, "doctor_id": p.doctor_id,
                    "raw_content": p.raw_content, "msg_type": p.msg_type,
                    "status": p.status, "created_at": _fmt_ts(p.created_at),
                    "processed_at": _fmt_ts(getattr(p, "processed_at", None)),
                }
                for p in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "audit_log":
            stmt = select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(AuditLog.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, AuditLog.doctor_id)
            items = [
                {
                    "id": a.id, "ts": _fmt_ts(a.ts), "doctor_id": a.doctor_id,
                    "action": a.action, "resource_type": a.resource_type,
                    "resource_id": a.resource_id, "ok": a.ok, "ip": a.ip,
                }
                for a in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "doctor_knowledge_items":
            stmt = select(DoctorKnowledgeItem).order_by(DoctorKnowledgeItem.updated_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(DoctorKnowledgeItem.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, DoctorKnowledgeItem.doctor_id)
            items = [
                {
                    "id": k.id, "doctor_id": k.doctor_id, "content": k.content,
                    "created_at": _fmt_ts(k.created_at), "updated_at": _fmt_ts(k.updated_at),
                }
                for k in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "system_prompt_versions":
            stmt = select(SystemPromptVersion).order_by(SystemPromptVersion.changed_at.desc()).limit(limit)
            items = [
                {
                    "id": v.id, "prompt_key": v.prompt_key, "changed_by": v.changed_by,
                    "changed_at": _fmt_ts(v.changed_at),
                    "content": (v.content[:200] + "…") if v.content and len(v.content) > 200 else v.content,
                }
                for v in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "doctor_session_states":
            stmt = select(DoctorSessionState).order_by(DoctorSessionState.updated_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(DoctorSessionState.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, DoctorSessionState.doctor_id)
            items = [
                {
                    "doctor_id": s.doctor_id,
                    "current_patient_id": s.current_patient_id,
                    "pending_create_name": s.pending_create_name,
                    "pending_record_id": s.pending_record_id,
                    "updated_at": _fmt_ts(s.updated_at),
                }
                for s in (await db.execute(stmt)).scalars().all()
            ]
        elif table_key == "chat_archive":
            stmt = select(ChatArchive).order_by(ChatArchive.created_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(ChatArchive.doctor_id == doctor_id)
            else:
                stmt = apply_exclude_test_doctors(stmt, ChatArchive.doctor_id)
            items = [
                {
                    "id": a.id, "doctor_id": a.doctor_id,
                    "role": a.role,
                    "content": (a.content[:200] + "…") if a.content and len(a.content) > 200 else a.content,
                    "intent_label": a.intent_label,
                    "created_at": _fmt_ts(a.created_at),
                }
                for a in (await db.execute(stmt)).scalars().all()
            ]
        else:
            raise HTTPException(status_code=404, detail="Unknown table")

    return {"table": table_key, "items": items}


# ── Fast-router keyword management ───────────────────────────────────────────

@router.get("/api/admin/fast-router/keywords")
async def admin_get_keywords(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Return all keyword sets loaded from config/fast_router_keywords.json."""
    _require_ui_admin_access(x_admin_token)
    from services.ai.fast_router import (
        _IMPORT_KEYWORDS, _LIST_PATIENTS_EXACT, _LIST_PATIENTS_SHORT,
        _LIST_TASKS_EXACT, _LIST_TASKS_SHORT, _NON_NAME_KEYWORDS,
        _CLINICAL_KW_TIER3, _TIER3_BAD_NAME, get_extra_keywords,
    )
    return {
        "counts": {
            "tier3": len(_CLINICAL_KW_TIER3),
            "import_keywords": len(_IMPORT_KEYWORDS),
            "list_patients_exact": len(_LIST_PATIENTS_EXACT),
            "list_patients_short": len(_LIST_PATIENTS_SHORT),
            "list_tasks_exact": len(_LIST_TASKS_EXACT),
            "list_tasks_short": len(_LIST_TASKS_SHORT),
            "non_name_keywords": len(_NON_NAME_KEYWORDS),
            "tier3_bad_name": len(_TIER3_BAD_NAME),
        },
        "config": get_extra_keywords(),
    }


class KeywordsUpdateBody(BaseModel):
    model_config = {"extra": "allow"}


@router.put("/api/admin/fast-router/keywords")
async def admin_put_keywords(
    body: KeywordsUpdateBody,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Overwrite sections of the keywords config and hot-reload."""
    _require_ui_admin_access(x_admin_token)
    import json as _json
    from services.ai.fast_router import reload_extra_keywords, _EXTRA_KW_PATH
    path = Path(_EXTRA_KW_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Merge all provided fields into existing config
    updates = body.model_dump(exclude_none=True)
    existing.update(updates)
    path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    result = reload_extra_keywords()
    return {"ok": True, **result}


@router.post("/api/admin/fast-router/keywords/reload")
async def admin_reload_keywords(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Hot-reload extra keywords from data/fast_router_keywords.json without restart."""
    _require_ui_admin_access(x_admin_token)
    from services.ai.fast_router import reload_extra_keywords
    result = reload_extra_keywords()
    return {"ok": True, **result}


_LOG_SOURCES: dict[str, str] = {
    "app": "logs/app.log",
    "tasks": "logs/tasks.log",
    "scheduler": "logs/scheduler.log",
}


_LOG_LEVEL_TAGS: dict[str, list[str]] = {
    "DEBUG": ["[DEBUG]", "[INFO]", "[WARNING]", "[ERROR]", "[CRITICAL]"],
    "INFO": ["[INFO]", "[WARNING]", "[ERROR]", "[CRITICAL]"],
    "WARNING": ["[WARNING]", "[ERROR]", "[CRITICAL]"],
    "ERROR": ["[ERROR]", "[CRITICAL]"],
    "CRITICAL": ["[CRITICAL]"],
}


@router.get("/api/debug/logs")
async def debug_logs(
    level: str = Query(default="ALL", description="Filter level: ALL, DEBUG, INFO, WARNING, ERROR, CRITICAL"),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    source: str = Query(default="app", description="Log source: app, tasks, scheduler"),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Return recent log lines filtered by level (hierarchical: WARNING includes ERROR, CRITICAL)."""
    _require_ui_debug_access(x_debug_token)
    log_path = Path(_LOG_SOURCES.get(source, "logs/app.log"))
    if not log_path.exists():
        return {"lines": [], "source": source, "total": 0}
    level_tags = _LOG_LEVEL_TAGS.get(level.upper())  # None means ALL
    matching: list[str] = []
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.rstrip()
                if level_tags is None or any(tag in stripped for tag in level_tags):
                    matching.append(stripped)
    except OSError:
        return {"lines": [], "source": source, "total": 0}
    return {"lines": matching[-limit:], "source": source, "total": len(matching)}


@router.get("/api/debug/observability")
async def debug_observability(
    trace_limit: int = Query(default=80, ge=1, le=500),
    summary_limit: int = Query(default=500, ge=1, le=2000),
    span_limit: int = Query(default=300, ge=1, le=1000),
    slow_span_limit: int = Query(default=30, ge=1, le=200),
    scope: str = Query(default="public"),
    trace_id: str | None = Query(default=None),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Observability data for the debug page."""
    _require_ui_debug_access(x_debug_token)
    summary = get_latency_summary_scoped(limit=summary_limit, scope=scope)
    recent_traces = get_recent_traces_scoped(limit=trace_limit, scope=scope)
    recent_spans = get_recent_spans_scoped(limit=span_limit, scope=scope, trace_id=trace_id)
    slow_spans = get_slowest_spans_scoped(limit=slow_span_limit, scope=scope)
    trace_timeline = get_trace_timeline(trace_id=trace_id) if trace_id else []
    return {
        "summary": summary,
        "recent_traces": recent_traces,
        "recent_spans": recent_spans,
        "slow_spans": slow_spans,
        "trace_timeline": trace_timeline,
    }


@router.delete("/api/debug/observability/traces")
async def debug_clear_observability_traces(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Clear in-memory observability traces."""
    _require_ui_debug_access(x_debug_token)
    clear_traces()
    return {"ok": True}


@router.post("/api/debug/observability/sample")
async def debug_seed_observability_samples(
    count: int = Query(default=3, ge=1, le=20),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Seed sample observability data for testing."""
    _require_ui_debug_access(x_debug_token)
    now = datetime.now(timezone.utc)
    created: list[str] = []
    for i in range(count):
        trace_id = str(uuid.uuid4())
        created.append(trace_id)
        started = now - timedelta(seconds=(count - i))
        total_ms = 1200.0 + i * 180.0
        llm_ms = max(200.0, total_ms - 180.0)
        status_code = 200 if i % 4 != 3 else 500
        add_trace(trace_id=trace_id, started_at=started, method="POST", path="/api/records/chat", status_code=status_code, latency_ms=total_ms)
        add_span(trace_id=trace_id, parent_span_id=None, layer="router", name="records.chat.agent_dispatch", started_at=started, latency_ms=llm_ms + 12.0, status="ok" if status_code < 500 else "error", meta={"sample": True})
        add_span(trace_id=trace_id, parent_span_id=None, layer="llm", name="agent.chat_completion", started_at=started + timedelta(milliseconds=6), latency_ms=llm_ms, status="ok" if status_code < 500 else "error", meta={"provider": "sample"})
    return {"ok": True, "count": len(created)}


@router.get("/api/debug/routing-metrics")
async def debug_routing_metrics(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Fast-router vs LLM hit counts for the debug page."""
    _require_ui_debug_access(x_debug_token)
    from services.observability.routing_metrics import get_metrics
    return get_metrics()


@router.post("/api/debug/routing-metrics/reset")
async def debug_routing_metrics_reset(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Reset routing counters to zero."""
    _require_ui_debug_access(x_debug_token)
    from services.observability.routing_metrics import reset
    reset()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Invite code management (admin only)
# ---------------------------------------------------------------------------

import secrets as _secrets


class InviteCodeCreate(BaseModel):
    doctor_id: str
    doctor_name: Optional[str] = None
    code: Optional[str] = None  # custom code; auto-generated if omitted


class InviteCodeRow(BaseModel):
    code: str
    doctor_id: str
    doctor_name: Optional[str]
    active: bool
    created_at: str


@router.get("/api/admin/invite-codes")
async def list_invite_codes(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(InviteCode).order_by(InviteCode.created_at.desc()))).scalars().all()
    return {
        "items": [
            InviteCodeRow(
                code=r.code,
                doctor_id=r.doctor_id,
                doctor_name=r.doctor_name,
                active=bool(r.active),
                created_at=_fmt_ts(r.created_at),
            )
            for r in rows
        ]
    }


@router.post("/api/admin/invite-codes")
async def create_invite_code(
    body: InviteCodeCreate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    doctor_id = (body.doctor_id or "").strip()
    if not doctor_id:
        raise HTTPException(status_code=422, detail="doctor_id is required")
    # Validate or generate code
    if body.code:
        custom = body.code.strip()
        if not re.match(r'^[A-Za-z0-9_-]{4,32}$', custom):
            raise HTTPException(status_code=422, detail="邀请码只能包含字母、数字、- 和 _，长度 4-32 位")
        code = custom
    else:
        code = _secrets.token_urlsafe(9)  # 12-char URL-safe string
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(
            select(InviteCode).where(InviteCode.code == code).limit(1)
        )).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="该邀请码已存在")
        session.add(InviteCode(
            code=code,
            doctor_id=doctor_id,
            doctor_name=(body.doctor_name or "").strip() or None,
            active=1,
            created_at=now,
        ))
        await session.commit()
    return InviteCodeRow(
        code=code,
        doctor_id=doctor_id,
        doctor_name=(body.doctor_name or "").strip() or None,
        active=True,
        created_at=_fmt_ts(now),
    )


@router.delete("/api/admin/invite-codes/{code}")
async def revoke_invite_code(
    code: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as session:
        invite = (
            await session.execute(select(InviteCode).where(InviteCode.code == code).limit(1))
        ).scalar_one_or_none()
        if invite is None:
            raise HTTPException(status_code=404, detail="Invite code not found")
        invite.active = 0
        await session.commit()
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
    _resolve_ui_doctor_id(doctor_id, authorization)
    sess = get_session(doctor_id)
    pending_id = sess.pending_record_id
    if not pending_id:
        return None
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, doctor_id)
    if pending is None or pending.status != "awaiting":
        clear_pending_record_id(doctor_id)
        return None
    # Check expiry
    now = datetime.now(timezone.utc)
    if pending.expires_at and pending.expires_at < now:
        clear_pending_record_id(doctor_id)
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
    }


@router.post("/api/manage/pending-record/confirm")
async def confirm_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Confirm the pending record draft → save to medical_records."""
    from services.wechat.wechat_domain import save_pending_record
    _resolve_ui_doctor_id(doctor_id, authorization)
    sess = get_session(doctor_id)
    pending_id = sess.pending_record_id
    if not pending_id:
        raise HTTPException(status_code=404, detail="No pending record")
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, doctor_id)
    if pending is None or pending.status != "awaiting":
        clear_pending_record_id(doctor_id)
        raise HTTPException(status_code=404, detail="Pending record not found or already processed")
    result = await save_pending_record(doctor_id, pending)
    clear_pending_record_id(doctor_id)
    patient_name = result[0] if result else None
    return {"ok": True, "patient_name": patient_name or "未关联"}


@router.post("/api/manage/pending-record/abandon")
async def abandon_pending_record_endpoint(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Abandon the pending record draft."""
    _resolve_ui_doctor_id(doctor_id, authorization)
    sess = get_session(doctor_id)
    pending_id = sess.pending_record_id
    if not pending_id:
        raise HTTPException(status_code=404, detail="No pending record")
    async with AsyncSessionLocal() as session:
        await abandon_pending_record(session, pending_id, doctor_id=doctor_id)
    clear_pending_record_id(doctor_id)
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
