"""
管理后台分表查询：admin_table_rows 端点的各表行级查询逻辑。
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import Optional

from fastapi import HTTPException
from utils.log import safe_create_task
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import (
    AuditLog,
    ChatArchive,
    Doctor,
    DoctorContext,
    DoctorKnowledgeItem,
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
from services.observability.audit import audit
from channels.web.ui._utils import (
    _fmt_ts,
    _parse_tags,
    _parse_admin_filters,
    _apply_created_at_filters,
    apply_exclude_test_doctors,
)

_SENSITIVE_TABLES = {
    "chat_archive", "medical_records",
    "pending_records", "pending_messages",
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


async def _rows_neuro_cases(
    db, doctor_id: Optional[str], needle: Optional[str], dt_from, dt_to_exclusive,
    limit: int, offset: int,
) -> list:
    stmt = (
        select(MedicalRecordDB)
        .where(MedicalRecordDB.record_type == "neuro_case")
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit).offset(offset)
    )
    stmt = _apply_created_at_filters(stmt, MedicalRecordDB, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(MedicalRecordDB.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, MedicalRecordDB.doctor_id)
    if needle:
        stmt = stmt.where(MedicalRecordDB.neuro_patient_name.ilike(needle))
    return [
        {"id": n.id, "doctor_id": n.doctor_id, "patient_id": n.patient_id,
         "patient_name": n.neuro_patient_name, "nihss": n.nihss,
         "created_at": _fmt_ts(n.created_at)}
        for n in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_patient_labels(
    db, doctor_id: Optional[str], dt_from, dt_to_exclusive, limit: int, offset: int,
) -> list:
    stmt = select(PatientLabel).order_by(PatientLabel.created_at.desc()).limit(limit).offset(offset)
    stmt = _apply_created_at_filters(stmt, PatientLabel, dt_from, dt_to_exclusive)
    if doctor_id:
        stmt = stmt.where(PatientLabel.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, PatientLabel.doctor_id)
    return [
        {"id": lbl.id, "doctor_id": lbl.doctor_id, "name": lbl.name,
         "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}
        for lbl in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_label_assignments(
    db, doctor_id: Optional[str], needle: Optional[str], limit: int, offset: int,
) -> list:
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
        .limit(limit).offset(offset)
    )
    if doctor_id:
        stmt = stmt.where(PatientLabel.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, PatientLabel.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return [
        {"patient_id": pid, "label_id": lid, "patient_name": pname,
         "label_name": lname, "doctor_id": did}
        for pid, lid, pname, lname, did in (await db.execute(stmt)).all()
    ]


async def _rows_system_prompts(db, limit: int, offset: int) -> list:
    stmt = select(SystemPrompt).order_by(SystemPrompt.updated_at.desc()).limit(limit).offset(offset)
    return [
        {"key": p.key, "content": p.content, "updated_at": _fmt_ts(p.updated_at)}
        for p in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_doctor_contexts(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(DoctorContext).order_by(DoctorContext.updated_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(DoctorContext.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, DoctorContext.doctor_id)
    return [
        {"doctor_id": c.doctor_id, "summary": c.summary, "updated_at": _fmt_ts(c.updated_at)}
        for c in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_neuro_cvd_context(
    db, doctor_id: Optional[str], needle: Optional[str], limit: int, offset: int,
) -> list:
    stmt = (
        select(NeuroCVDContext, Patient.name.label("patient_name"))
        .outerjoin(Patient, NeuroCVDContext.patient_id == Patient.id)
        .order_by(NeuroCVDContext.created_at.desc()).limit(limit).offset(offset)
    )
    if doctor_id:
        stmt = stmt.where(NeuroCVDContext.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, NeuroCVDContext.doctor_id)
    if needle:
        stmt = stmt.where(Patient.name.ilike(needle))
    return [
        {
            "id": r.id, "doctor_id": r.doctor_id, "patient_id": r.patient_id,
            "patient_name": pname, "record_id": r.record_id,
            "diagnosis_subtype": r.diagnosis_subtype,
            "surgery_status": r.surgery_status,
            "source": r.source,
            "created_at": _fmt_ts(r.created_at),
            "updated_at": _fmt_ts(r.updated_at),
            **(_json.loads(r.raw_json) if r.raw_json else {}),
        }
        for r, pname in (await db.execute(stmt)).all()
    ]


async def _rows_specialty_scores(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(SpecialtyScore).order_by(SpecialtyScore.id.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(SpecialtyScore.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, SpecialtyScore.doctor_id)
    return [
        {
            "id": s.id, "record_id": s.record_id, "doctor_id": s.doctor_id,
            "score_type": s.score_type, "score_value": s.score_value, "raw_text": s.raw_text,
            "patient_id": getattr(s, "patient_id", None),
            "extracted_at": _fmt_ts(getattr(s, "extracted_at", None)),
        }
        for s in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_record_versions(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(MedicalRecordVersion).order_by(MedicalRecordVersion.changed_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(MedicalRecordVersion.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, MedicalRecordVersion.doctor_id)
    return [
        {
            "id": v.id, "record_id": v.record_id, "doctor_id": v.doctor_id,
            "old_content": v.old_content, "old_tags": _parse_tags(v.old_tags),
            "old_record_type": v.old_record_type, "changed_at": _fmt_ts(v.changed_at),
        }
        for v in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_record_exports(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(MedicalRecordExport).order_by(MedicalRecordExport.exported_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(MedicalRecordExport.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, MedicalRecordExport.doctor_id)
    return [
        {
            "id": e.id, "record_id": e.record_id, "doctor_id": e.doctor_id,
            "export_format": e.export_format, "pdf_hash": e.pdf_hash,
            "exported_at": _fmt_ts(e.exported_at),
        }
        for e in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_pending_records(
    db, doctor_id: Optional[str], needle: Optional[str], limit: int, offset: int,
) -> list:
    stmt = select(PendingRecord).order_by(PendingRecord.created_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(PendingRecord.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, PendingRecord.doctor_id)
    if needle:
        stmt = stmt.where(PendingRecord.patient_name.ilike(needle))
    return [
        {
            "id": p.id, "doctor_id": p.doctor_id, "patient_id": p.patient_id,
            "patient_name": p.patient_name, "status": p.status,
            "draft_json": p.draft_json, "created_at": _fmt_ts(p.created_at),
            "expires_at": _fmt_ts(p.expires_at),
        }
        for p in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_pending_messages(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(PendingMessage).order_by(PendingMessage.created_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(PendingMessage.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, PendingMessage.doctor_id)
    return [
        {"id": p.id, "doctor_id": p.doctor_id, "raw_content": p.raw_content,
         "status": p.status, "attempt_count": p.attempt_count,
         "created_at": _fmt_ts(p.created_at)}
        for p in (await db.execute(stmt)).scalars().all()
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


async def _rows_prompt_versions(db, limit: int, offset: int) -> list:
    stmt = select(SystemPromptVersion).order_by(SystemPromptVersion.changed_at.desc()).limit(limit).offset(offset)
    return [
        {
            "id": v.id, "prompt_key": v.prompt_key, "changed_by": v.changed_by,
            "changed_at": _fmt_ts(v.changed_at),
            "content": (v.content[:200] + "…") if v.content and len(v.content) > 200 else v.content,
        }
        for v in (await db.execute(stmt)).scalars().all()
    ]


async def _rows_chat_archive(db, doctor_id: Optional[str], limit: int, offset: int) -> list:
    stmt = select(ChatArchive).order_by(ChatArchive.created_at.desc()).limit(limit).offset(offset)
    if doctor_id:
        stmt = stmt.where(ChatArchive.doctor_id == doctor_id)
    else:
        stmt = apply_exclude_test_doctors(stmt, ChatArchive.doctor_id)
    return [
        {
            "id": a.id, "doctor_id": a.doctor_id, "role": a.role,
            "content": (a.content[:200] + "…") if a.content and len(a.content) > 200 else a.content,
            "intent_label": a.intent_label, "created_at": _fmt_ts(a.created_at),
        }
        for a in (await db.execute(stmt)).scalars().all()
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
    if table_key == "neuro_cases":
        return await _rows_neuro_cases(db, doctor_id, needle, dt_from, dt_to_exclusive, limit, offset)
    if table_key == "patient_labels":
        return await _rows_patient_labels(db, doctor_id, dt_from, dt_to_exclusive, limit, offset)
    if table_key == "patient_label_assignments":
        return await _rows_label_assignments(db, doctor_id, needle, limit, offset)
    if table_key == "system_prompts":
        return await _rows_system_prompts(db, limit, offset)
    if table_key == "doctor_contexts":
        return await _rows_doctor_contexts(db, doctor_id, limit, offset)
    if table_key == "neuro_cvd_context":
        return await _rows_neuro_cvd_context(db, doctor_id, needle, limit, offset)
    if table_key == "specialty_scores":
        return await _rows_specialty_scores(db, doctor_id, limit, offset)
    if table_key == "medical_record_versions":
        return await _rows_record_versions(db, doctor_id, limit, offset)
    if table_key == "medical_record_exports":
        return await _rows_record_exports(db, doctor_id, limit, offset)
    if table_key == "pending_records":
        return await _rows_pending_records(db, doctor_id, needle, limit, offset)
    if table_key == "pending_messages":
        return await _rows_pending_messages(db, doctor_id, limit, offset)
    if table_key == "audit_log":
        return await _rows_audit_log(db, doctor_id, limit, offset)
    if table_key == "doctor_knowledge_items":
        return await _rows_knowledge_items(db, doctor_id, limit, offset)
    if table_key == "system_prompt_versions":
        return await _rows_prompt_versions(db, limit, offset)
    if table_key == "chat_archive":
        return await _rows_chat_archive(db, doctor_id, limit, offset)
    raise HTTPException(status_code=404, detail="Unknown table")


async def admin_table_rows_logic(
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
    async with AsyncSessionLocal() as db:
        items = await _fetch_table_rows(db, table_key, doctor_id, needle, dt_from, dt_to_exclusive, limit, offset)
    return {"table": table_key, "items": items}
