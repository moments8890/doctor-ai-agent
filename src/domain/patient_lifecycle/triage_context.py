"""Patient context loader for triage LLM prompts (ADR 0020).

Builds the patient context dict injected into classify() and handler prompts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.patient_message import list_patient_messages
from utils.log import log


async def load_patient_context(
    patient_id: int,
    doctor_id: str,
    db_session: AsyncSession,
) -> dict:
    """Build a patient context dict for injection into triage LLM prompts.

    Loads:
    - Latest treatment plan (not yet implemented)
    - Pending patient tasks
    - Recent 10 messages
    """
    from db.models.tasks import DoctorTask, TaskStatus
    from sqlalchemy import select

    # Treatment plan: not yet implemented (derive_treatment_plan removed).
    treatment_plan: Optional[Dict[str, Any]] = None

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

    # 4. Diagnosis summary (extracted from treatment plan)
    diagnosis_summary: Optional[str] = None
    if treatment_plan:
        diagnoses = treatment_plan.get("diagnosis", [])
        if diagnoses:
            # Build a readable summary from differential diagnoses
            parts = []
            for d in diagnoses[:5]:  # cap at 5
                if isinstance(d, dict):
                    name = d.get("condition", d.get("name", ""))
                    if name:
                        parts.append(name)
                elif isinstance(d, str):
                    parts.append(d)
            if parts:
                diagnosis_summary = "、".join(parts)

    # 5. Medications (extracted from treatment plan)
    medications: List[str] = []
    if treatment_plan:
        for item in treatment_plan.get("treatment", [])[:10]:
            if isinstance(item, dict):
                drug = item.get("drug_class", item.get("description", ""))
                if drug:
                    medications.append(drug)

    return {
        "treatment_plan": treatment_plan,
        "pending_tasks": pending_tasks,
        "recent_messages": recent_messages,
        "diagnosis_summary": diagnosis_summary,
        "medications": medications,
    }
