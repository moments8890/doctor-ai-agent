"""Patient context loader for triage LLM prompts (ADR 0020).

Builds the patient context dict injected into classify() and handler prompts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.patient_message import list_patient_messages
from utils.log import log


def _clean_text(value: Optional[str]) -> str:
    text = (value or "").strip()
    return text


def _looks_meaningful(value: Optional[str]) -> bool:
    text = _clean_text(value)
    return bool(text and text not in {"无", "不详", "未知", "未填写", "暂无"})


def _extract_medications(*texts: Optional[str]) -> List[str]:
    medications: List[str] = []
    seen = set()
    for text in texts:
        cleaned = _clean_text(text)
        if not cleaned:
            continue
        for raw_line in cleaned.replace("；", "\n").replace("。", "\n").splitlines():
            line = raw_line.strip(" -:：,，;；")
            if not line or len(line) > 80:
                continue
            if "药" not in line and "mg" not in line.lower() and "片" not in line and "次" not in line:
                continue
            if line not in seen:
                seen.add(line)
                medications.append(line)
    return medications[:10]


async def load_patient_context(
    patient_id: int,
    doctor_id: str,
    db_session: AsyncSession,
) -> dict:
    """Build a patient context dict for injection into triage LLM prompts.

    Loads:
    - Aggregated prior stable history from recent structured records
    - Latest record summary (diagnosis / treatment / follow-up)
    - Pending patient tasks
    - Recent 10 messages
    """
    from db.models.records import MedicalRecordDB, RecordStatus
    from db.models.tasks import DoctorTask, TaskStatus
    from sqlalchemy import select

    # Structured record context from recent visits (newest first).
    latest_record: Optional[Dict[str, Any]] = None
    stable_history: Dict[str, str] = {}
    try:
        result = await db_session.execute(
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == doctor_id,
                MedicalRecordDB.status.in_([
                    RecordStatus.completed.value,
                    RecordStatus.pending_review.value,
                ]),
            )
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(5)
        )
        rows = result.scalars().all()

        if rows:
            latest = rows[0]
            stable_labels = {
                "past_history": "既往史",
                "allergy_history": "过敏史",
                "family_history": "家族史",
                "personal_history": "个人史",
                "marital_reproductive": "婚育史",
            }
            for row in reversed(rows):
                for field_name in stable_labels:
                    value = _clean_text(getattr(row, field_name, None))
                    if _looks_meaningful(value):
                        stable_history[field_name] = value

            latest_record = {
                "created_at": latest.created_at.isoformat() if latest.created_at else None,
                "chief_complaint": _clean_text(latest.chief_complaint),
                "present_illness": _clean_text(latest.present_illness),
                "diagnosis": _clean_text(latest.diagnosis or latest.final_diagnosis),
                "treatment_plan": _clean_text(latest.treatment_plan),
                "orders_followup": _clean_text(latest.orders_followup),
                "past_history": _clean_text(latest.past_history),
                "allergy_history": _clean_text(latest.allergy_history),
            }
            latest_record = {key: value for key, value in latest_record.items() if value}
    except Exception as exc:
        log(f"[triage] records load failed for patient {patient_id}: {exc}", level="warning")

    # 1. Pending patient tasks
    pending_tasks: List[Dict[str, Any]] = []
    try:
        result = await db_session.execute(
            select(DoctorTask)
            .where(
                DoctorTask.patient_id == patient_id,
                DoctorTask.doctor_id == doctor_id,
                DoctorTask.target == "patient",
                DoctorTask.status.in_([TaskStatus.pending, TaskStatus.notified]),
            )
            .order_by(DoctorTask.due_at.asc())
            .limit(20)
        )
        for task in result.scalars().all():
            pending_tasks.append({
                "type": task.task_type,
                "title": task.title,
                "content": task.content,
                "due_at": task.due_at.isoformat() if task.due_at else None,
            })
    except Exception as exc:
        log(f"[triage] tasks load failed for patient {patient_id}: {exc}", level="warning")

    # 3. Recent messages (last 10)
    recent_messages: List[Dict[str, str]] = []
    try:
        messages = await list_patient_messages(
            db_session, patient_id, doctor_id, limit=10,
        )
        for msg in reversed(messages):  # oldest first for conversation flow
            recent_messages.append({
                "direction": msg.direction,
                "source": msg.source or ("patient" if msg.direction == "inbound" else "ai"),
                "content": msg.content[:300],  # truncate long messages
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            })
    except Exception as exc:
        log(f"[triage] messages load failed for patient {patient_id}: {exc}", level="warning")

    diagnosis_summary: Optional[str] = None
    if latest_record:
        diagnosis_summary = _clean_text(latest_record.get("diagnosis"))

    medications = _extract_medications(
        latest_record.get("treatment_plan") if latest_record else None,
        latest_record.get("orders_followup") if latest_record else None,
    )

    return {
        "stable_history": stable_history,
        "latest_record": latest_record,
        "treatment_plan": latest_record.get("treatment_plan") if latest_record else None,
        "pending_tasks": pending_tasks,
        "recent_messages": recent_messages,
        "diagnosis_summary": diagnosis_summary,
        "medications": medications,
    }
