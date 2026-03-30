"""
管理后台分表查询：admin_table_rows 端点的各表行级查询逻辑。
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException
from utils.log import safe_create_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import (
    AuditLog,
    Doctor,
    DoctorChatLog,
    DoctorKnowledgeItem,
    DoctorTask,
    InterviewSessionDB,
    MedicalRecordDB,
    Patient,
)
from infra.observability.audit import audit
from channels.web.doctor_dashboard.filters import (
    _fmt_ts,
    _parse_tags,
    _parse_admin_filters,
    _apply_created_at_filters,
    apply_exclude_test_doctors,
)

_SENSITIVE_TABLES = {
    "doctor_chat_log", "medical_records",
}


# ---------------------------------------------------------------------------
# Per-table query functions (each ≤ 30 lines)
# ---------------------------------------------------------------------------

async def _rows_doctors(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(Doctor).order_by(Doctor.updated_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(Doctor.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, Doctor.doctor_id)
    return [
        {"doctor_id": d.doctor_id, "name": d.name,
         "department": d.department or "",
         "created_at": _fmt_ts(d.created_at), "updated_at": _fmt_ts(d.updated_at)}
        for d in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_patients(
    db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive,
    limit: int, offset: int,
) -> list:
    stmt = select(Patient).order_by(Patient.created_at.desc()).limit(limit).offset(offset)
    stmt = _apply_created_at_filters(stmt, Patient, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(Patient.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, Patient.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return [
        {"id": p.id, "doctor_id": p.doctor_id, "name": p.name,
         "gender": p.gender, "year_of_birth": p.year_of_birth,
         "phone": p.phone or "",
         "created_at": _fmt_ts(p.created_at)}
        for p in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_medical_records(
    db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive,
    limit: int, offset: int,
) -> list:
    stmt = (
        select(MedicalRecordDB, Patient.name.label("patient_name"))
        .outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit).offset(offset)
    )
    stmt = _apply_created_at_filters(stmt, MedicalRecordDB, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(MedicalRecordDB.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, MedicalRecordDB.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return [
        {"id": r.id, "patient_id": r.patient_id, "doctor_id": r.doctor_id,
         "patient_name": pname, "record_type": r.record_type or "visit",
         "content": r.content, "tags": _parse_tags(r.tags),
         "status": r.status or "completed",
         "has_structured": r.has_structured_data(),
         "created_at": _fmt_ts(r.created_at)}
        for r, pname in (await db.execute(stmt)).all()
    ]


async def _rows_doctor_tasks(
    db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive,
    limit: int, offset: int,
) -> list:
    stmt = (
        select(DoctorTask, Patient.name.label("patient_name"))
        .outerjoin(Patient, DoctorTask.patient_id == Patient.id)
        .order_by(DoctorTask.created_at.desc())
        .limit(limit).offset(offset)
    )
    stmt = _apply_created_at_filters(stmt, DoctorTask, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(DoctorTask.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, DoctorTask.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return [
        {"id": t.id, "doctor_id": t.doctor_id, "patient_id": t.patient_id,
         "patient_name": pname, "task_type": t.task_type, "title": t.title,
         "status": t.status, "due_at": _fmt_ts(t.due_at), "record_id": t.record_id,
         "updated_at": _fmt_ts(t.updated_at), "created_at": _fmt_ts(t.created_at)}
        for t, pname in (await db.execute(stmt)).all()
    ]


async def _rows_audit_log(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(AuditLog.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, AuditLog.doctor_id)
    return [
        {
            "id": a.id, "ts": _fmt_ts(a.ts), "doctor_id": a.doctor_id,
            "action": a.action, "resource_type": a.resource_type,
            "resource_id": a.resource_id, "ok": a.ok, "ip": a.ip,
        }
        for a in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_knowledge_items(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(DoctorKnowledgeItem).order_by(DoctorKnowledgeItem.updated_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(DoctorKnowledgeItem.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, DoctorKnowledgeItem.doctor_id)
    return [
        {"id": k.id, "doctor_id": k.doctor_id, "content": k.content,
         "created_at": _fmt_ts(k.created_at), "updated_at": _fmt_ts(k.updated_at)}
        for k in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_doctor_chat_log(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(DoctorChatLog).order_by(DoctorChatLog.created_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(DoctorChatLog.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, DoctorChatLog.doctor_id)
    return [
        {
            "id": a.id, "doctor_id": a.doctor_id, "session_id": a.session_id,
            "role": a.role,
            "content": (a.content[:200] + "\u2026") if a.content and len(a.content) > 200 else a.content,
            "created_at": _fmt_ts(a.created_at),
        }
        for a in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_interview_sessions(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(InterviewSessionDB).order_by(InterviewSessionDB.created_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(InterviewSessionDB.doctor_id == doctor_id)
    return [
        {"id": s.id[:8], "doctor_id": s.doctor_id, "patient_id": s.patient_id,
         "status": s.status, "turn_count": s.turn_count,
         "created_at": _fmt_ts(s.created_at), "updated_at": _fmt_ts(s.updated_at)}
        for s in (await db.execute(stmt)).scalars().all()
    ]


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

async def _fetch_table_rows(
    db, table_key: str,
    doctor_id: Optional[str], needle: Optional[str],
    dt_from, dt_to_exclusive, limit: int, offset: int,
) -> list:
    """Dispatch table_key to the correct per-table fetch function."""
    if table_key == "doctors":
        return await _rows_doctors(db, doctor_id, limit, offset)
    if table_key == "patients":
        return await _rows_patients(db, doctor_id, needle, dt_from, dt_to_exclusive, limit, offset)
    if table_key == "medical_records":
        return await _rows_medical_records(db, doctor_id, needle, dt_from, dt_to_exclusive, limit, offset)
    if table_key == "doctor_tasks":
        return await _rows_doctor_tasks(db, doctor_id, needle, dt_from, dt_to_exclusive, limit, offset)
    if table_key == "audit_log":
        return await _rows_audit_log(db, doctor_id, limit, offset)
    if table_key == "doctor_knowledge_items":
        return await _rows_knowledge_items(db, doctor_id, limit, offset)
    if table_key == "doctor_chat_log":
        return await _rows_doctor_chat_log(db, doctor_id, limit, offset)
    if table_key == "interview_sessions":
        return await _rows_interview_sessions(db, doctor_id, limit, offset)
    raise HTTPException(status_code=404, detail="Unknown table")


async def admin_table_rows_logic(
    db,
    table_key: str,
    doctor_id: Optional[str],
    patient_name: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    limit: int,
    offset: int,
) -> dict:
    """Resolve filters and delegate to the per-table fetch helper."""
    if table_key in _SENSITIVE_TABLES:
        safe_create_task(audit("admin", "READ", table_key, "admin_query"))
    doctor_id, patient_name, _, _, dt_from, dt_to_exclusive = _parse_admin_filters(
        doctor_id, patient_name, date_from, date_to
    )
    needle = f"%{patient_name.strip()}%" if patient_name and patient_name.strip() else None
    items = await _fetch_table_rows(db, table_key, doctor_id, needle, dt_from, dt_to_exclusive, limit, offset)
    return {"table": table_key, "items": items}
