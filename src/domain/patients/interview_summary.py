"""Generate MedicalRecord from completed interview (ADR 0016)."""
from __future__ import annotations

import re
from typing import Dict, List

from db.models.medical_record import MedicalRecord
from domain.patients.completeness import ALL_COLLECTABLE
from utils.log import log

FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
    "family_history": "家族史",
    "physical_exam": "体格检查",
    "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查",
    "diagnosis": "诊断",
    "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
}


def generate_content(collected: Dict[str, str]) -> str:
    """Generate prose content string from collected fields."""
    lines: List[str] = []
    for field in ALL_COLLECTABLE:
        value = collected.get(field, "")
        if not value:
            continue
        label = FIELD_LABELS.get(field, field)
        lines.append(f"{label}：{value}")
    return "\n".join(lines) if lines else ""


def generate_structured(collected: Dict[str, str]) -> Dict[str, str]:
    """Map collected fields to the 14-field outpatient schema."""
    from domain.records.schema import FIELD_KEYS
    structured: Dict[str, str] = {}
    for key in FIELD_KEYS:
        structured[key] = collected.get(key, "")
    return structured


def extract_tags(collected: Dict[str, str]) -> List[str]:
    """Extract keyword tags from chief_complaint and present_illness."""
    tags: List[str] = []
    for field in ("chief_complaint", "present_illness"):
        value = collected.get(field, "")
        if not value:
            continue
        parts = re.split(r"[，。；、\s]+", value)
        for part in parts:
            part = part.strip()
            if 1 < len(part) <= 10 and part not in tags:
                tags.append(part)
    return tags[:10]


def build_medical_record(collected: Dict[str, str]) -> MedicalRecord:
    """Build a MedicalRecord from interview collected fields."""
    content = generate_content(collected)
    if not content:
        content = "预问诊记录（无临床内容）"

    structured = generate_structured(collected)
    tags = extract_tags(collected)

    return MedicalRecord(
        content=content,
        structured=structured,
        tags=tags,
        record_type="interview_summary",
    )


async def confirm_interview(
    session_id: str,
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    collected: Dict[str, str],
) -> Dict[str, int]:
    """Finalize interview: save record + create review task. Returns {record_id, review_id}."""
    from db.crud.records import save_record
    from db.crud.tasks import create_task
    from db.engine import AsyncSessionLocal

    record = build_medical_record(collected)

    async with AsyncSessionLocal() as db:
        db_record = await save_record(
            db, doctor_id, record, patient_id,
            needs_review=True,
            commit=True,
        )

        # Create review task for the doctor
        task = await create_task(
            db, doctor_id,
            task_type="review",
            title=f"审阅患者【{patient_name}】预问诊记录",
            content=f"患者已完成预问诊，请审阅病历记录。",
            patient_id=patient_id,
            record_id=db_record.id,
        )
        await db.commit()

    log(f"[interview] confirmed session={session_id} record={db_record.id} task={task.id}")

    # Notify doctor (best-effort, don't block on failure)
    try:
        from domain.tasks.notifications import send_doctor_notification
        await send_doctor_notification(
            doctor_id,
            f"患者【{patient_name}】已完成预问诊，请查看待审核记录。",
        )
    except Exception as e:
        log(f"[interview] doctor notification failed: {e}", level="warning")

    return {"record_id": db_record.id, "review_id": task.id}
