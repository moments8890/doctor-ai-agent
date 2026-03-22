"""Auto-generate patient tasks when a doctor confirms a diagnosis.

Reads the confirmed DiagnosisResult's ai_output and doctor_decisions,
then creates DoctorTask rows for every approved workup and treatment item.

Urgency → due-date mapping (workup):
  - 急诊  → +1 day
  - 紧急  → +3 days
  - 常规  → +7 days

Treatment → task type mapping:
  - intervention=观察  → follow_up task, +7 days
  - otherwise         → medication task, +7 days
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.diagnosis_result import DiagnosisResult
from db.models.records import MedicalRecordDB
from db.models.tasks import DoctorTask, TaskStatus
from utils.log import log

# ── Urgency → due-day offsets ──────────────────────────────────────────
_URGENCY_DAYS: Dict[str, int] = {
    "急诊": 1,
    "紧急": 3,
    "常规": 7,
}
_DEFAULT_TREATMENT_DAYS = 7


# ── Helpers ────────────────────────────────────────────────────────────

def _parse_json(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _approved_indices(decisions: Dict[str, Any], category: str) -> set:
    """Return the set of index strings marked 'confirmed' in doctor_decisions."""
    cat = decisions.get(category, {})
    if not isinstance(cat, dict):
        return set()
    return {idx for idx, dec in cat.items() if dec == "confirmed"}


async def _resolve_patient_id(
    session: AsyncSession,
    record_id: int,
) -> Optional[int]:
    """Look up patient_id from the medical record linked to the diagnosis."""
    row = (await session.execute(
        select(MedicalRecordDB.patient_id).where(MedicalRecordDB.id == record_id)
    )).scalar_one_or_none()
    return row


async def _task_exists(
    session: AsyncSession,
    doctor_id: str,
    record_id: int,
    task_type: str,
    title: str,
) -> bool:
    """Check if a pending/notified task already exists for the same record+type+title."""
    stmt = (
        select(DoctorTask.id)
        .where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.record_id == record_id,
            DoctorTask.task_type == task_type,
            DoctorTask.title == title,
            DoctorTask.status.in_([TaskStatus.pending, TaskStatus.notified]),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


# ── Main entry point ──────────────────────────────────────────────────

async def generate_patient_tasks(
    diagnosis_result: DiagnosisResult,
    db_session: AsyncSession,
) -> List[DoctorTask]:
    """Create DoctorTask rows from a confirmed diagnosis.

    Returns the list of newly created tasks (may be empty if all items
    were rejected or tasks already exist).
    """
    ai_output = _parse_json(diagnosis_result.ai_output)
    decisions = _parse_json(diagnosis_result.doctor_decisions)

    doctor_id = diagnosis_result.doctor_id
    record_id = diagnosis_result.record_id
    patient_id = await _resolve_patient_id(db_session, record_id)
    now = datetime.now(timezone.utc)

    created: List[DoctorTask] = []

    # ── Workup items ──────────────────────────────────────────────
    approved_workup = _approved_indices(decisions, "workup")
    workup_items: List[Dict[str, Any]] = ai_output.get("workup", [])
    for idx_str in sorted(approved_workup):
        idx = int(idx_str)
        if idx >= len(workup_items):
            continue
        item = workup_items[idx]
        test_name = item.get("test", "检查")
        urgency = item.get("urgency", "常规")
        due_days = _URGENCY_DAYS.get(urgency, 7)
        task_type = "lab_review" if urgency != "急诊" else "emergency"
        title = f"检查：{test_name}"
        content = item.get("rationale", "")

        if await _task_exists(db_session, doctor_id, record_id, task_type, title):
            continue

        task = DoctorTask(
            doctor_id=doctor_id,
            patient_id=patient_id,
            record_id=record_id,
            task_type=task_type,
            title=title,
            content=content,
            status=TaskStatus.pending,
            due_at=now + timedelta(days=due_days),
            target="patient",
            source_type="diagnosis_auto",
            source_id=diagnosis_result.id,
        )
        db_session.add(task)
        created.append(task)

    # ── Treatment items ───────────────────────────────────────────
    approved_treatment = _approved_indices(decisions, "treatment")
    treatment_items: List[Dict[str, Any]] = ai_output.get("treatment", [])
    for idx_str in sorted(approved_treatment):
        idx = int(idx_str)
        if idx >= len(treatment_items):
            continue
        item = treatment_items[idx]
        drug_class = item.get("drug_class", "")
        intervention = item.get("intervention", "药物")
        description = item.get("description", "")

        if intervention == "观察":
            task_type = "follow_up"
            title = f"随访观察：{drug_class or description}"
        else:
            task_type = "medication"
            title = f"治疗：{drug_class or description}"

        # Truncate title to fit DB column (256 chars)
        title = title[:256]
        content = description

        if await _task_exists(db_session, doctor_id, record_id, task_type, title):
            continue

        task = DoctorTask(
            doctor_id=doctor_id,
            patient_id=patient_id,
            record_id=record_id,
            task_type=task_type,
            title=title,
            content=content,
            status=TaskStatus.pending,
            due_at=now + timedelta(days=_DEFAULT_TREATMENT_DAYS),
            target="patient",
            source_type="diagnosis_auto",
            source_id=diagnosis_result.id,
        )
        db_session.add(task)
        created.append(task)

    if created:
        await db_session.flush()
        log(
            f"[task_generation] created {len(created)} patient tasks "
            f"for diagnosis {diagnosis_result.id} (record {record_id})",
        )

    return created
