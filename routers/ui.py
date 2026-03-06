from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
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
)
from db.engine import AsyncSessionLocal
from db.models import (
    Doctor,
    DoctorContext,
    DoctorTask,
    MedicalRecordDB,
    NeuroCaseDB,
    Patient,
    PatientLabel,
    SystemPrompt,
    patient_label_assignments,
)
from services.patient_timeline import build_patient_timeline
from services.observability import (
    add_span,
    add_trace,
    clear_traces,
    get_latency_summary_scoped,
    get_recent_spans_scoped,
    get_recent_traces_scoped,
    get_slowest_spans_scoped,
    get_trace_timeline,
)
from services.runtime_config import (
    apply_runtime_config,
    load_runtime_config_dict,
    runtime_config_categories,
    runtime_config_source_path,
    save_runtime_config_dict,
    validate_runtime_config,
)

router = APIRouter(tags=["ui"])


class PromptUpdate(BaseModel):
    content: str


class RuntimeConfigUpdate(BaseModel):
    config: dict


def _extract_tunnel_url_from_log(content: str) -> str | None:
    quick = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", content or "")
    if quick:
        return quick[-1]

    generic = re.findall(r"https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s|]*)?", content or "")
    for url in reversed(generic):
        if "127.0.0.1" in url or "localhost" in url:
            continue
        if "cloudflare.com" in url and "trycloudflare.com" not in url:
            continue
        return url.rstrip(" .|")
    return None


def _fmt_ts(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_tags(raw: str | None) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _parse_bool(raw: str | None) -> bool | None:
    if raw is None or not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _is_risk_stale(risk_computed_at: datetime | None, hours: int = 24) -> bool:
    if risk_computed_at is None:
        return True
    if risk_computed_at.tzinfo is None:
        risk_computed_at = risk_computed_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - risk_computed_at
    return delta.total_seconds() >= hours * 3600


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


@router.get("/api/manage/patients")
async def manage_patients(
    doctor_id: str = Query(default="web_doctor"),
    category: str | None = Query(default=None),
    risk: str | None = Query(default=None),
    follow_up_state: str | None = Query(default=None),
    stale_risk: str | None = Query(default=None),
):
    category = _normalize_query_str(category)
    risk = _normalize_query_str(risk)
    follow_up_state = _normalize_query_str(follow_up_state)
    stale_risk = _normalize_query_str(stale_risk)

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
            "category_computed_at": _fmt_ts(p.category_computed_at),
            "category_rules_version": p.category_rules_version,
            "primary_risk_level": p.primary_risk_level,
            "risk_tags": _parse_tags(p.risk_tags),
            "risk_score": p.risk_score,
            "follow_up_state": p.follow_up_state,
            "risk_computed_at": _fmt_ts(p.risk_computed_at),
            "risk_rules_version": p.risk_rules_version,
            "stale_risk": _is_risk_stale(p.risk_computed_at),
            "labels": [{"id": lbl.id, "name": lbl.name, "color": lbl.color} for lbl in (p.labels or [])],
        }
        for p in patients
    ]

    if category is not None:
        items = [item for item in items if item["primary_category"] == category]
    if risk is not None:
        items = [item for item in items if item["primary_risk_level"] == risk]
    if follow_up_state is not None:
        items = [item for item in items if item["follow_up_state"] == follow_up_state]

    stale_filter = _parse_bool(stale_risk)
    if stale_filter is not None:
        items = [item for item in items if bool(item["stale_risk"]) is stale_filter]

    return {"doctor_id": doctor_id, "items": items}


_CATEGORY_ORDER = ["high_risk", "active_followup", "stable", "new", "uncategorized"]


@router.get("/api/manage/patients/grouped")
async def manage_patients_grouped(doctor_id: str = Query(default="web_doctor")):
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
            "category_computed_at": _fmt_ts(p.category_computed_at),
            "category_rules_version": p.category_rules_version,
            "primary_risk_level": p.primary_risk_level,
            "risk_tags": _parse_tags(p.risk_tags),
            "risk_score": p.risk_score,
            "follow_up_state": p.follow_up_state,
            "risk_computed_at": _fmt_ts(p.risk_computed_at),
            "risk_rules_version": p.risk_rules_version,
            "stale_risk": _is_risk_stale(p.risk_computed_at),
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


@router.get("/api/manage/patients/grouped-risk")
async def manage_patients_grouped_risk(doctor_id: str = Query(default="web_doctor")):
    async with AsyncSessionLocal() as db:
        patients = await get_all_patients(db, doctor_id)

    order = ["critical", "high", "medium", "low", "unknown"]
    bucket: dict = {key: [] for key in order}
    for p in patients:
        key = p.primary_risk_level or "unknown"
        if key not in bucket:
            key = "unknown"
        bucket[key].append(
            {
                "id": p.id,
                "name": p.name,
                "primary_risk_level": p.primary_risk_level,
                "risk_score": p.risk_score,
                "follow_up_state": p.follow_up_state,
                "risk_computed_at": _fmt_ts(p.risk_computed_at),
            }
        )

    groups = [{"group": key, "count": len(bucket[key]), "items": bucket[key]} for key in order]
    return {"doctor_id": doctor_id, "groups": groups}


@router.get("/api/manage/patients/{patient_id}/timeline")
async def manage_patient_timeline(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    limit: int = Query(default=100, ge=1, le=500),
):
    async with AsyncSessionLocal() as db:
        data = await build_patient_timeline(db, doctor_id=doctor_id, patient_id=patient_id, limit=limit)
    if data is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return {"doctor_id": doctor_id, **data}


@router.get("/api/manage/records")
async def manage_records(
    doctor_id: str = Query(default="web_doctor"),
    patient_id: int | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
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
                    "chief_complaint": r.chief_complaint,
                    "history_of_present_illness": r.history_of_present_illness,
                    "past_medical_history": r.past_medical_history,
                    "physical_examination": r.physical_examination,
                    "auxiliary_examinations": r.auxiliary_examinations,
                    "diagnosis": r.diagnosis,
                    "treatment_plan": r.treatment_plan,
                    "follow_up_plan": r.follow_up_plan,
                    "created_at": _fmt_ts(r.created_at),
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
                    "chief_complaint": r.chief_complaint,
                    "history_of_present_illness": r.history_of_present_illness,
                    "past_medical_history": r.past_medical_history,
                    "physical_examination": r.physical_examination,
                    "auxiliary_examinations": r.auxiliary_examinations,
                    "diagnosis": r.diagnosis,
                    "treatment_plan": r.treatment_plan,
                    "follow_up_plan": r.follow_up_plan,
                    "created_at": _fmt_ts(r.created_at),
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

    return {"doctor_id": doctor_id, "items": items[:limit]}


@router.get("/api/manage/prompts")
async def manage_prompts():
    async with AsyncSessionLocal() as db:
        base = await get_system_prompt(db, "structuring")
        ext = await get_system_prompt(db, "structuring.extension")
    return {
        "structuring": base.content if base else "",
        "structuring_extension": ext.content if ext else "",
    }


@router.put("/api/manage/prompts/{key}")
async def update_prompt(key: str, body: PromptUpdate):
    if key not in {"structuring", "structuring.extension"}:
        raise HTTPException(status_code=400, detail="Only structuring and structuring.extension are editable.")
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
async def list_labels(doctor_id: str = Query(default="web_doctor")):
    async with AsyncSessionLocal() as db:
        labels = await get_labels_for_doctor(db, doctor_id)
    return {
        "items": [
            {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}
            for lbl in labels
        ]
    }


@router.post("/api/manage/labels")
async def create_label_endpoint(body: LabelCreate):
    async with AsyncSessionLocal() as db:
        lbl = await create_label(db, body.doctor_id, body.name, body.color)
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}


@router.patch("/api/manage/labels/{label_id}")
async def update_label_endpoint(label_id: int, body: LabelUpdate):
    async with AsyncSessionLocal() as db:
        lbl = await update_label(db, label_id, body.doctor_id, name=body.name, color=body.color)
    if lbl is None:
        raise HTTPException(status_code=404, detail="Label not found")
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color}


@router.delete("/api/manage/labels/{label_id}")
async def delete_label_endpoint(label_id: int, doctor_id: str = Query(default="web_doctor")):
    async with AsyncSessionLocal() as db:
        found = await delete_label(db, label_id, doctor_id)
    if not found:
        raise HTTPException(status_code=404, detail="Label not found")
    return {"ok": True}


@router.post("/api/manage/patients/{patient_id}/labels/{label_id}")
async def assign_label_endpoint(patient_id: int, label_id: int, doctor_id: str = Query(default="web_doctor")):
    async with AsyncSessionLocal() as db:
        try:
            await assign_label(db, patient_id, label_id, doctor_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.delete("/api/manage/patients/{patient_id}/labels/{label_id}")
async def remove_label_endpoint(patient_id: int, label_id: int, doctor_id: str = Query(default="web_doctor")):
    async with AsyncSessionLocal() as db:
        try:
            await remove_label(db, patient_id, label_id, doctor_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.get("/api/admin/observability")
async def admin_observability(
    trace_limit: int = 100,
    summary_limit: int = 500,
    span_limit: int = 200,
    slow_span_limit: int = 30,
    scope: str = "all",
    trace_id: str | None = None,
):
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
async def admin_clear_observability_traces():
    clear_traces()
    return {"ok": True}


@router.post("/api/admin/observability/sample")
async def admin_seed_observability_samples(count: int = Query(default=3, ge=1, le=20)):
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
async def admin_get_runtime_config():
    config = await load_runtime_config_dict()
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(config)
    return {"source": source, "config": config, "categories": categories}


@router.put("/api/admin/config")
async def admin_update_runtime_config(body: RuntimeConfigUpdate):
    if not isinstance(body.config, dict):
        raise HTTPException(status_code=400, detail="config must be a JSON object")
    saved = await save_runtime_config_dict(body.config)
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(saved)
    return {"ok": True, "applied": False, "source": source, "config": saved, "categories": categories}


@router.post("/api/admin/config/verify")
async def admin_verify_runtime_config(body: RuntimeConfigUpdate):
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
async def admin_apply_runtime_config():
    saved = await load_runtime_config_dict()
    await apply_runtime_config(saved)
    source = str(runtime_config_source_path())
    categories = runtime_config_categories(saved)
    return {"ok": True, "applied": True, "source": source, "config": saved, "categories": categories}


@router.get("/api/admin/dev/tunnel-url")
async def admin_get_tunnel_url():
    log_path_raw = (
        os.environ.get("CLOUDFLARED_LOG_PATH")
        or os.environ.get("TUNNEL_LOG_PATH")
        or str(Path.home() / "Library/Logs/aiagent-cloudflared.log")
    )
    log_path = Path(log_path_raw).expanduser()
    if not log_path.exists():
        return {"ok": False, "url": None, "source": str(log_path), "detail": "log file not found"}

    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": None, "source": str(log_path), "detail": f"read failed: {exc}"}

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
):
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
            rows = (await db.execute(select(col).where(col.is_not(None)))).scalars().all()
            for value in rows:
                if isinstance(value, str) and value.strip():
                    doctor_candidates.add(value.strip())

        patient_stmt = select(Patient.name).where(Patient.name.is_not(None))
        if doctor_id:
            patient_stmt = patient_stmt.where(Patient.doctor_id == doctor_id)
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
):
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
            "chief_complaint": record.chief_complaint,
            "diagnosis": record.diagnosis,
            "treatment_plan": record.treatment_plan,
            "follow_up_plan": record.follow_up_plan,
            "created_at": _fmt_ts(record.created_at),
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


def _apply_created_at_filters(stmt, model, dt_from: datetime | None, dt_to_exclusive: datetime | None):
    if dt_from is not None and hasattr(model, "created_at"):
        stmt = stmt.where(model.created_at >= dt_from)
    if dt_to_exclusive is not None and hasattr(model, "created_at"):
        stmt = stmt.where(model.created_at < dt_to_exclusive)
    return stmt


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


@router.get("/api/admin/tables")
async def admin_tables(
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    doctor_id, patient_name, _, _, dt_from, dt_to_exclusive = _parse_admin_filters(
        doctor_id, patient_name, date_from, date_to
    )
    needle = f"%{patient_name.strip()}%" if patient_name and patient_name.strip() else None

    counts = {
        "doctors": 0,
        "patients": 0,
        "medical_records": 0,
        "doctor_tasks": 0,
        "neuro_cases": 0,
        "patient_labels": 0,
        "patient_label_assignments": 0,
        "system_prompts": 0,
        "doctor_contexts": 0,
    }

    async with AsyncSessionLocal() as db:
        doctors_stmt = select(func.count(Doctor.doctor_id))
        if doctor_id:
            doctors_stmt = doctors_stmt.where(Doctor.doctor_id == doctor_id)
        counts["doctors"] = int((await db.execute(doctors_stmt)).scalar() or 0)

        patients_stmt = select(func.count(Patient.id))
        patients_stmt = _apply_created_at_filters(patients_stmt, Patient, dt_from, dt_to_exclusive)
        if doctor_id:
            patients_stmt = patients_stmt.where(Patient.doctor_id == doctor_id)
        if needle:
            patients_stmt = patients_stmt.where(Patient.name.ilike(needle))
        counts["patients"] = int((await db.execute(patients_stmt)).scalar() or 0)

        records_stmt = select(func.count(MedicalRecordDB.id)).outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
        records_stmt = _apply_created_at_filters(records_stmt, MedicalRecordDB, dt_from, dt_to_exclusive)
        if doctor_id:
            records_stmt = records_stmt.where(MedicalRecordDB.doctor_id == doctor_id)
        if needle:
            records_stmt = records_stmt.where(Patient.name.ilike(needle))
        counts["medical_records"] = int((await db.execute(records_stmt)).scalar() or 0)

        tasks_stmt = select(func.count(DoctorTask.id)).outerjoin(Patient, DoctorTask.patient_id == Patient.id)
        tasks_stmt = _apply_created_at_filters(tasks_stmt, DoctorTask, dt_from, dt_to_exclusive)
        if doctor_id:
            tasks_stmt = tasks_stmt.where(DoctorTask.doctor_id == doctor_id)
        if needle:
            tasks_stmt = tasks_stmt.where(Patient.name.ilike(needle))
        counts["doctor_tasks"] = int((await db.execute(tasks_stmt)).scalar() or 0)

        neuro_stmt = select(func.count(NeuroCaseDB.id))
        neuro_stmt = _apply_created_at_filters(neuro_stmt, NeuroCaseDB, dt_from, dt_to_exclusive)
        if doctor_id:
            neuro_stmt = neuro_stmt.where(NeuroCaseDB.doctor_id == doctor_id)
        if needle:
            neuro_stmt = neuro_stmt.where(NeuroCaseDB.patient_name.ilike(needle))
        counts["neuro_cases"] = int((await db.execute(neuro_stmt)).scalar() or 0)

        labels_stmt = select(func.count(PatientLabel.id))
        labels_stmt = _apply_created_at_filters(labels_stmt, PatientLabel, dt_from, dt_to_exclusive)
        if doctor_id:
            labels_stmt = labels_stmt.where(PatientLabel.doctor_id == doctor_id)
        counts["patient_labels"] = int((await db.execute(labels_stmt)).scalar() or 0)

        assignments_stmt = (
            select(func.count())
            .select_from(patient_label_assignments)
            .join(PatientLabel, patient_label_assignments.c.label_id == PatientLabel.id)
            .join(Patient, patient_label_assignments.c.patient_id == Patient.id)
        )
        if doctor_id:
            assignments_stmt = assignments_stmt.where(PatientLabel.doctor_id == doctor_id)
        if needle:
            assignments_stmt = assignments_stmt.where(Patient.name.ilike(needle))
        counts["patient_label_assignments"] = int((await db.execute(assignments_stmt)).scalar() or 0)

        prompts_stmt = select(func.count(SystemPrompt.key))
        counts["system_prompts"] = int((await db.execute(prompts_stmt)).scalar() or 0)

        context_stmt = select(func.count(DoctorContext.doctor_id))
        if doctor_id:
            context_stmt = context_stmt.where(DoctorContext.doctor_id == doctor_id)
        counts["doctor_contexts"] = int((await db.execute(context_stmt)).scalar() or 0)

    ordered = [
        "doctors",
        "patients",
        "medical_records",
        "doctor_tasks",
        "neuro_cases",
        "patient_labels",
        "patient_label_assignments",
        "system_prompts",
        "doctor_contexts",
    ]
    return {"items": [{"key": key, "count": counts[key]} for key in ordered]}


@router.get("/api/admin/tables/{table_key}")
async def admin_table_rows(
    table_key: str,
    doctor_id: str | None = Query(default=None),
    patient_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    doctor_id, patient_name, _, _, dt_from, dt_to_exclusive = _parse_admin_filters(
        doctor_id, patient_name, date_from, date_to
    )
    needle = f"%{patient_name.strip()}%" if patient_name and patient_name.strip() else None

    async with AsyncSessionLocal() as db:
        if table_key == "doctors":
            stmt = select(Doctor).order_by(Doctor.updated_at.desc()).limit(limit)
            if doctor_id:
                stmt = stmt.where(Doctor.doctor_id == doctor_id)
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
            if needle:
                stmt = stmt.where(Patient.name.ilike(needle))
            items = [
                {
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "doctor_id": r.doctor_id,
                    "patient_name": pname,
                    "chief_complaint": r.chief_complaint,
                    "diagnosis": r.diagnosis,
                    "treatment_plan": r.treatment_plan,
                    "follow_up_plan": r.follow_up_plan,
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
                    "trigger_source": t.trigger_source,
                    "created_at": _fmt_ts(t.created_at),
                }
                for t, pname in (await db.execute(stmt)).all()
            ]
        elif table_key == "neuro_cases":
            stmt = select(NeuroCaseDB).order_by(NeuroCaseDB.created_at.desc()).limit(limit)
            stmt = _apply_created_at_filters(stmt, NeuroCaseDB, dt_from, dt_to_exclusive)
            if doctor_id:
                stmt = stmt.where(NeuroCaseDB.doctor_id == doctor_id)
            if needle:
                stmt = stmt.where(NeuroCaseDB.patient_name.ilike(needle))
            items = [
                {
                    "id": n.id,
                    "doctor_id": n.doctor_id,
                    "patient_id": n.patient_id,
                    "patient_name": n.patient_name,
                    "chief_complaint": n.chief_complaint,
                    "primary_diagnosis": n.primary_diagnosis,
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
            items = [
                {
                    "doctor_id": c.doctor_id,
                    "summary": c.summary,
                    "updated_at": _fmt_ts(c.updated_at),
                }
                for c in (await db.execute(stmt)).scalars().all()
            ]
        else:
            raise HTTPException(status_code=404, detail="Unknown table")

    return {"table": table_key, "items": items}
