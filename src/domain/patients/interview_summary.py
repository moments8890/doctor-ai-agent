"""Generate MedicalRecord from completed interview (ADR 0016).

Batch-extracts all clinical record fields from the complete conversation transcript
in one LLM pass. No incremental merge needed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel

from db.models.medical_record import MedicalRecord
from domain.patients.completeness import ALL_COLLECTABLE
from utils.log import log


# ---------------------------------------------------------------------------
# Pydantic response models for structured LLM extraction
# ---------------------------------------------------------------------------

class DoctorExtractResult(BaseModel):
    """14-field extraction result for doctor dictation mode."""
    department: Optional[str] = None
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None
    past_history: Optional[str] = None
    allergy_history: Optional[str] = None
    personal_history: Optional[str] = None
    marital_reproductive: Optional[str] = None
    family_history: Optional[str] = None
    physical_exam: Optional[str] = None
    specialist_exam: Optional[str] = None
    auxiliary_exam: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None
    orders_followup: Optional[str] = None


class PatientExtractResult(BaseModel):
    """7-field extraction result for patient pre-consultation mode."""
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None
    past_history: Optional[str] = None
    allergy_history: Optional[str] = None
    personal_history: Optional[str] = None
    marital_reproductive: Optional[str] = None
    family_history: Optional[str] = None

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


def _load_extract_prompt(mode: str) -> str:
    """Load batch extraction prompt from markdown file."""
    from utils.prompt_loader import get_prompt_sync
    prompt_key = "intent/patient-extract" if mode == "patient" else "intent/doctor-extract"
    return get_prompt_sync(prompt_key)


async def batch_extract_from_transcript(
    conversation: list,
    patient_info: dict,
    mode: str = "patient",
) -> Dict[str, str]:
    """Extract all clinical record fields from the complete conversation in one LLM pass.

    Args:
        conversation: Full conversation history (list of dicts with role/content).
        patient_info: Dict with keys name, gender, age.
        mode: "patient" for pre-consultation interviews, "doctor" for doctor dictation.

    Returns:
        Dict of field_name -> extracted value (empty fields filtered out).
    """
    from agent.llm import structured_call

    # Build transcript
    transcript_lines = []
    for turn in conversation:
        if mode == "patient":
            role = "AI助手" if turn.get("role") in ("assistant", "system") else "患者"
        else:
            role = "AI助手" if turn.get("role") in ("assistant", "system") else "医生"
        text = turn.get("content", turn.get("text", ""))
        transcript_lines.append(f"{role}：{text}")
    transcript = "\n".join(transcript_lines)

    name = patient_info.get("name", "未知")
    gender = patient_info.get("gender", "未知")
    age = patient_info.get("age", "未知")

    template = _load_extract_prompt(mode)
    # Manual substitution — .format() breaks on JSON braces in prompt examples
    prompt = (
        template
        .replace("{name}", str(name))
        .replace("{gender}", str(gender))
        .replace("{age}", str(age))
        .replace("{transcript}", transcript)
    )

    response_model = DoctorExtractResult if mode == "doctor" else PatientExtractResult

    # Load base safety prompt (Pattern C prompts get base.md as system msg)
    from utils.prompt_loader import get_prompt_sync
    base_prompt = get_prompt_sync("common/base", fallback="")

    try:
        messages = []
        if base_prompt:
            messages.append({"role": "system", "content": base_prompt})
        messages.append({"role": "user", "content": prompt})

        extracted = await structured_call(
            response_model=response_model,
            messages=messages,
            op_name="interview.batch_extract",
            temperature=0.1,
            max_tokens=1024,
        )

        # Convert to dict, filtering out None and empty fields
        result = {
            k: v.strip()
            for k, v in extracted.model_dump().items()
            if isinstance(v, str) and v.strip()
        }

        log(f"[batch_extract] extracted {len(result)} fields: {list(result.keys())}")
        return result

    except Exception as exc:
        log(f"[batch_extract] failed: {exc}", level="warning")
        return {}


async def confirm_interview(
    session_id: str,
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    collected: Dict[str, str],
    conversation: Optional[list] = None,
) -> Dict[str, int]:
    """Finalize interview: batch-extract from transcript → save record → create review task. Returns {record_id, review_id}."""
    from domain.patients.interview_turn import get_session_lock, release_session_lock

    async with get_session_lock(session_id):
        try:
            return await _confirm_interview_inner(
                session_id=session_id,
                doctor_id=doctor_id,
                patient_id=patient_id,
                patient_name=patient_name,
                collected=collected,
                conversation=conversation,
            )
        finally:
            release_session_lock(session_id)


async def _confirm_interview_inner(
    session_id: str,
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    collected: Dict[str, str],
    conversation: Optional[list] = None,
) -> Dict[str, int]:
    """Inner implementation of confirm_interview — always called under the session lock."""
    from db.crud.patient import get_patient_for_doctor
    from db.crud.records import save_record
    from db.engine import AsyncSessionLocal

    # Batch-extract all fields from the full transcript in one pass
    if conversation:
        # Load patient info for the extraction prompt
        async with AsyncSessionLocal() as db:
            patient = await get_patient_for_doctor(db, doctor_id, patient_id)

        if patient:
            now = datetime.now()
            age = now.year - patient.year_of_birth if patient.year_of_birth else "未知"
            patient_info = {
                "name": patient.name,
                "gender": patient.gender or "未知",
                "age": age,
            }
        else:
            patient_info = {"name": patient_name, "gender": "未知", "age": "未知"}

        collected = await batch_extract_from_transcript(
            conversation, patient_info, mode="patient",
        )

    record = build_medical_record(collected)

    async with AsyncSessionLocal() as db:
        from db.models.records import RecordStatus
        db_record = await save_record(
            db, doctor_id, record, patient_id,
            status=RecordStatus.pending_review.value,
            commit=True,
        )

        # Review notification handled by 审核 tab — no task created.
        await db.commit()

    log(f"[interview] confirmed session={session_id} record={db_record.id}")

    # Auto-trigger diagnosis pipeline (fire-and-forget)
    try:
        from domain.diagnosis import run_diagnosis
        from utils.log import safe_create_task
        safe_create_task(
            run_diagnosis(doctor_id=doctor_id, record_id=db_record.id),
            name=f"diagnosis-{db_record.id}",
        )
        log(f"[interview] diagnosis triggered for record={db_record.id}")
    except Exception as e:
        log(f"[interview] diagnosis trigger failed: {e}", level="warning")

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
