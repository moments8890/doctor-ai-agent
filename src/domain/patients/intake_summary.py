"""Generate MedicalRecord from completed intake (ADR 0016).

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
    """Build a MedicalRecord from intake collected fields."""
    content = generate_content(collected)
    if not content:
        content = "预问诊记录（无临床内容）"

    structured = generate_structured(collected)
    tags = extract_tags(collected)

    return MedicalRecord(
        content=content,
        structured=structured,
        tags=tags,
        record_type="intake_summary",
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
        mode: "patient" for pre-consultation intakes, "doctor" for doctor dictation.

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
            op_name="intake.batch_extract",
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


async def confirm_intake(
    session_id: str,
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    collected: Dict[str, str],
    conversation: Optional[list] = None,
) -> Dict[str, int]:
    """Patient-side confirm. Phase 1: delegates to IntakeEngine.confirm.

    Preserves the return shape expected by patient_intake_routes.py.
    The engine handles batch re-extract, record persist, diagnosis trigger,
    doctor notification, session mark-confirmed, and lock release internally.
    """
    # Import inside function body to avoid circular imports (same pattern as Task 11).
    from domain.intake.engine import IntakeEngine

    engine = IntakeEngine()
    ref = await engine.confirm(
        session_id=session_id,
        override_patient_name=patient_name or None,
    )
    # review_id was from a review-task entity that no longer exists
    # (commit 4a2eba87). Kept in the response shape for backwards compat
    # with DoctorPage code that reads submitted.review_id with falsy guards.
    return {"record_id": ref.id, "review_id": None}
