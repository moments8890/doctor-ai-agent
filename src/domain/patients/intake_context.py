"""Context loaders for interview turns: patient demographics and prior history (ADR 0016)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from utils.log import log


async def _load_patient_info(patient_id: Optional[int]) -> Dict[str, Any]:
    """Load patient demographics for prompt context."""
    if patient_id is None:
        return {"name": "未知", "gender": "未知", "age": "未知"}

    from db.engine import AsyncSessionLocal
    from db.models import Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        patient = (await db.execute(
            select(Patient).where(Patient.id == patient_id)
        )).scalar_one_or_none()

    if patient is None:
        return {"name": "未知", "gender": "未知", "age": "未知"}

    age = "未知"
    if patient.year_of_birth:
        age = str(datetime.now().year - patient.year_of_birth)

    return {
        "name": patient.name or "未知",
        "gender": patient.gender or "未知",
        "age": age,
    }


async def _load_previous_history(patient_id: Optional[int], doctor_id: str) -> Optional[str]:
    """Load structured fields from patient's completed records for context.

    Aggregates stable fields (past_history, allergy, family, personal) across all
    completed records, and shows the latest visit's chief_complaint + diagnosis.
    Skips records in interview_active or pending_review status.
    """
    if patient_id is None:
        return None

    from db.engine import AsyncSessionLocal
    from db.models import MedicalRecordDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == doctor_id,
                MedicalRecordDB.status.in_(["completed", "pending_review"]),
            ).order_by(MedicalRecordDB.created_at.desc()).limit(5)
        )).scalars().all()

    if not rows:
        return None

    # Aggregate stable fields across all records (newest wins)
    stable_fields = {
        "past_history": "既往史",
        "allergy_history": "过敏史",
        "family_history": "家族史",
        "personal_history": "个人史",
    }
    aggregated = {}
    for row in reversed(rows):  # oldest first so newest overwrites
        for key in stable_fields:
            val = getattr(row, key, None) or ""
            if val and val not in ("无", "不详"):
                aggregated[key] = val

    # Latest visit info from the most recent record
    latest = rows[0]
    visit_fields = {
        "chief_complaint": "上次主诉",
        "diagnosis": "上次诊断",
    }

    lines = []
    for key, label in stable_fields.items():
        val = aggregated.get(key, "")
        if val:
            lines.append(f"- {label}：{val}")
    for key, label in visit_fields.items():
        val = getattr(latest, key, None) or ""
        if val:
            lines.append(f"- {label}：{val}")

    if not lines:
        return None

    date_str = latest.created_at.strftime("%Y-%m-%d") if latest.created_at else "未知"
    return f"既往记录（最近就诊 {date_str}）：\n" + "\n".join(lines)
