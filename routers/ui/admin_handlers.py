"""
管理后台处理器：admin_tables、admin_db_view 及可观测性样本填充的业务逻辑。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Query
from utils.log import safe_create_task
from sqlalchemy import func, select

from db.engine import AsyncSessionLocal
from db.models import (
    AuditLog,
    ChatArchive,
    Doctor,
    DoctorContext,
    DoctorKnowledgeItem,
    DoctorSessionState,
    DoctorTask,
    MedicalRecordDB,
    MedicalRecordExport,
    MedicalRecordVersion,
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
from services.observability.observability import add_span, add_trace
from services.observability.audit import audit
from routers.ui._utils import (
    _fmt_ts,
    _parse_tags,
    _normalize_query_str,
    _normalize_date_yyyy_mm_dd,
    _parse_admin_filters,
    _apply_created_at_filters,
    apply_exclude_test_doctors,
)


# ---------------------------------------------------------------------------
# admin_db_view helpers
# ---------------------------------------------------------------------------

def _build_db_view_stmts(
    doctor_id: Optional[str],
    patient_name: Optional[str],
    dt_from: Optional[datetime],
    dt_to_exclusive: Optional[datetime],
    limit: int,
):
    """Build patient + record SQLAlchemy statements for admin_db_view."""
    needle = f"%{patient_name.strip()}%" if patient_name else None

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

    if needle:
        patient_stmt = patient_stmt.where(Patient.name.ilike(needle))
        record_stmt = record_stmt.where(Patient.name.ilike(needle))

    if dt_from is not None:
        record_stmt = record_stmt.where(MedicalRecordDB.created_at >= dt_from)
    if dt_to_exclusive is not None:
        record_stmt = record_stmt.where(MedicalRecordDB.created_at < dt_to_exclusive)

    return patient_stmt, record_stmt


def _serialize_patient_item(p) -> dict:
    """Serialize a Patient ORM row for the db-view response."""
    return {
        "id": p.id, "doctor_id": p.doctor_id, "name": p.name,
        "gender": p.gender, "year_of_birth": p.year_of_birth,
        "created_at": _fmt_ts(p.created_at),
    }


def _serialize_record_item(record, pname: Optional[str]) -> dict:
    """Serialize a MedicalRecordDB ORM row for the db-view response."""
    return {
        "id": record.id, "patient_id": record.patient_id, "doctor_id": record.doctor_id,
        "patient_name": pname, "record_type": record.record_type or "visit",
        "content": record.content, "tags": _parse_tags(record.tags),
        "encounter_type": record.encounter_type or "unknown",
        "created_at": _fmt_ts(record.created_at), "updated_at": _fmt_ts(record.updated_at),
    }


async def admin_db_view_logic(
    doctor_id: Optional[str],
    patient_name: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    limit: int,
) -> dict:
    """Core logic for admin_db_view endpoint."""
    safe_create_task(audit("admin", "READ", "db_view", "admin_query"))
    doctor_id = _normalize_query_str(doctor_id)
    patient_name = _normalize_query_str(patient_name)
    date_from = _normalize_date_yyyy_mm_dd(date_from)
    date_to = _normalize_date_yyyy_mm_dd(date_to)
    dt_from = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    dt_to_exclusive = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1) if date_to else None

    patient_stmt, record_stmt = _build_db_view_stmts(
        doctor_id, patient_name, dt_from, dt_to_exclusive, limit
    )
    async with AsyncSessionLocal() as db:
        patients = (await db.execute(patient_stmt)).scalars().all()
        records = (await db.execute(record_stmt)).all()

    patient_items = [_serialize_patient_item(p) for p in patients]
    record_items = [_serialize_record_item(r, pname) for r, pname in records]

    return {
        "filters": {"doctor_id": doctor_id, "patient_name": patient_name,
                    "date_from": date_from, "date_to": date_to, "limit": limit},
        "counts": {"patients": len(patient_items), "records": len(record_items)},
        "patients": patient_items,
        "records": record_items,
    }


# ---------------------------------------------------------------------------
# admin_tables helpers
# ---------------------------------------------------------------------------

async def _count_doctors(db, doctor_id: Optional[str]) -> int:
    stmt = select(func.count(Doctor.doctor_id))
    if doctor_id:
        stmt = stmt.where(Doctor.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, Doctor.doctor_id)
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_patients(db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive) -> int:
    stmt = select(func.count(Patient.id))
    stmt = _apply_created_at_filters(stmt, Patient, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(Patient.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, Patient.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_records(db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive) -> int:
    stmt = (
        select(func.count(MedicalRecordDB.id))
        .outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
    )
    stmt = _apply_created_at_filters(stmt, MedicalRecordDB, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(MedicalRecordDB.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, MedicalRecordDB.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_tasks(db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive) -> int:
    stmt = (
        select(func.count(DoctorTask.id))
        .outerjoin(Patient, DoctorTask.patient_id == Patient.id)
    )
    stmt = _apply_created_at_filters(stmt, DoctorTask, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(DoctorTask.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, DoctorTask.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_neuro_cases(db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive) -> int:
    stmt = select(func.count(MedicalRecordDB.id)).where(
        MedicalRecordDB.record_type == "neuro_case"
    )
    stmt = _apply_created_at_filters(stmt, MedicalRecordDB, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(MedicalRecordDB.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, MedicalRecordDB.doctor_id)
    if needle:
        stmt = stmt.where(MedicalRecordDB.neuro_patient_name.ilike(needle))
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_labels_and_assignments(
    db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive
) -> tuple[int, int]:
    """Return (patient_labels count, patient_label_assignments count)."""
    labels_stmt = select(func.count(PatientLabel.id))
    labels_stmt = _apply_created_at_filters(labels_stmt, PatientLabel, dt_from, dt_to_exclusive)
    if doctor_id:
        labels_stmt = labels_stmt.where(PatientLabel.doctor_id == doctor_id)
    else:
        labels_stmt = apply_exclude_test_doctors(labels_stmt, PatientLabel.doctor_id)
    labels_count = int((await db.execute(labels_stmt)).scalar() or 0)

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
    assignments_count = int((await db.execute(assignments_stmt)).scalar() or 0)

    return labels_count, assignments_count


async def _count_pending_records(db, doctor_id: Optional[str], needle: Optional[str]) -> int:
    """Count pending_records with optional patient_name filter (matches drill-down)."""
    stmt = select(func.count()).select_from(PendingRecord)
    if doctor_id:
        stmt = stmt.where(PendingRecord.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, PendingRecord.doctor_id)
    if needle:
        stmt = stmt.where(PendingRecord.patient_name.ilike(needle))
    return int((await db.execute(stmt)).scalar() or 0)


async def _count_generic_tables(db, doctor_id: Optional[str]) -> dict:
    """Count rows for generic tables that only filter by doctor_id."""
    counts: dict = {}
    for model, key, col in [
        (NeuroCVDContext, "neuro_cvd_context", NeuroCVDContext.doctor_id),
        (SpecialtyScore, "specialty_scores", SpecialtyScore.doctor_id),
        (MedicalRecordVersion, "medical_record_versions", MedicalRecordVersion.doctor_id),
        (MedicalRecordExport, "medical_record_exports", MedicalRecordExport.doctor_id),
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
    return counts


_TABLES_ORDER = [
    "doctors", "patients", "medical_records", "medical_record_versions",
    "medical_record_exports", "doctor_tasks", "neuro_cases", "neuro_cvd_context",
    "specialty_scores", "pending_records", "pending_messages", "audit_log",
    "doctor_knowledge_items", "patient_labels", "patient_label_assignments",
    "system_prompts", "system_prompt_versions", "doctor_contexts",
    "doctor_session_states", "chat_archive",
]


async def _count_all_tables(db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive) -> dict:
    """Aggregate row counts for every admin table in one DB session."""
    counts: dict = {k: 0 for k in _TABLES_ORDER}
    counts["doctors"] = await _count_doctors(db, doctor_id)
    counts["patients"] = await _count_patients(db, doctor_id, needle, dt_from, dt_to_exclusive)
    counts["medical_records"] = await _count_records(db, doctor_id, needle, dt_from, dt_to_exclusive)
    counts["doctor_tasks"] = await _count_tasks(db, doctor_id, needle, dt_from, dt_to_exclusive)
    counts["neuro_cases"] = await _count_neuro_cases(db, doctor_id, needle, dt_from, dt_to_exclusive)
    counts["patient_labels"], counts["patient_label_assignments"] = (
        await _count_labels_and_assignments(db, doctor_id, needle, dt_from, dt_to_exclusive)
    )
    counts["pending_records"] = await _count_pending_records(db, doctor_id, needle)
    counts["system_prompts"] = int(
        (await db.execute(select(func.count(SystemPrompt.key)))).scalar() or 0
    )
    ctx_stmt = select(func.count(DoctorContext.doctor_id))
    if doctor_id:
        ctx_stmt = ctx_stmt.where(DoctorContext.doctor_id == doctor_id)
    else:
        ctx_stmt = apply_exclude_test_doctors(ctx_stmt, DoctorContext.doctor_id)
    counts["doctor_contexts"] = int((await db.execute(ctx_stmt)).scalar() or 0)
    counts.update(await _count_generic_tables(db, doctor_id))
    counts["system_prompt_versions"] = int(
        (await db.execute(select(func.count(SystemPromptVersion.id)))).scalar() or 0
    )
    return counts


async def admin_tables_logic(
    doctor_id: Optional[str],
    patient_name: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
) -> dict:
    """Core logic for admin_tables endpoint — count rows in every DB table."""
    doctor_id, patient_name, _, _, dt_from, dt_to_exclusive = _parse_admin_filters(
        doctor_id, patient_name, date_from, date_to
    )
    needle = f"%{patient_name.strip()}%" if patient_name and patient_name.strip() else None
    async with AsyncSessionLocal() as db:
        counts = await _count_all_tables(db, doctor_id, needle, dt_from, dt_to_exclusive)
    return {"items": [{"key": k, "count": counts[k]} for k in _TABLES_ORDER]}


# ---------------------------------------------------------------------------
# admin_seed_observability_samples helper
# ---------------------------------------------------------------------------

def _build_sample_spans(trace_id: str, started: datetime, total_ms: float, status_code: int) -> None:
    """Add the standard 4-span tree for a sample trace."""
    llm_ms = max(200.0, total_ms - 180.0)
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


async def admin_seed_samples_logic(count: int) -> dict:
    """Core logic for admin_seed_observability_samples endpoint."""
    now = datetime.now(timezone.utc)
    created: list[str] = []
    for i in range(count):
        trace_id = str(uuid.uuid4())
        created.append(trace_id)
        started = now - timedelta(seconds=(count - i))
        total_ms = 1200.0 + i * 180.0
        status_code = 200 if i % 4 != 3 else 500
        add_trace(
            trace_id=trace_id,
            started_at=started,
            method="POST",
            path="/api/records/chat",
            status_code=status_code,
            latency_ms=total_ms,
        )
        _build_sample_spans(trace_id, started, total_ms, status_code)
    return {"ok": True, "count": len(created), "trace_ids": created}
