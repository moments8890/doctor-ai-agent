"""共享病历组装：构建 MedicalRecord 对象（不保存），调用方负责渠道特定的保存策略。"""

from __future__ import annotations

import asyncio
from typing import Optional

from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.ai.structuring import structure_medical_record
from services.patient.encounter_detection import detect_encounter_type
from utils.log import log

# History turns shorter than this are likely commands ("查", "删除张三"), not clinical content.
_MIN_HISTORY_TURN_LEN = 15
_CMD_PREFIXES = ("患者列表", "所有患者", "删除", "建档", "查", "待办", "今天任务", "PDF")

# Clinical section keys from the add_medical_record / update_medical_record tool schema.
_CLINICAL_KEYS = [
    "chief_complaint",
    "history_of_present_illness",
    "past_medical_history",
    "physical_examination",
    "auxiliary_examinations",
    "diagnosis",
    "treatment_plan",
    "follow_up_plan",
]

# Lines in a prior-visit summary that look like prompt-injection attempts.
_SUMMARY_BLOCKED_PREFIXES = ("忽略", "SYSTEM", "system", "System", "#", "---")


def _record_from_structured_fields(
    intent_result: "IntentResult",  # type: ignore[name-defined]
    text: str,
) -> MedicalRecord:
    """Assemble a MedicalRecord from pre-structured intent fields (no LLM call)."""
    fields = dict(intent_result.structured_fields)
    parts = [fields.get(k) for k in _CLINICAL_KEYS]
    assembled = "；".join(p for p in parts if p)
    content_text = assembled or text.strip() or "门诊就诊"
    return MedicalRecord(content=content_text, record_type="dictation")


def _build_full_text(text: str, history: list[dict]) -> str:
    """Filter history to clinical turns and append current text, deduplicated."""
    doctor_ctx = [
        m["content"] for m in (history or [])[-6:]
        if m["role"] == "user"
        and len(m["content"]) >= _MIN_HISTORY_TURN_LEN
        and not any(m["content"].startswith(p) for p in _CMD_PREFIXES)
    ]
    doctor_ctx.append(text)
    return "\n".join(dict.fromkeys(filter(None, doctor_ctx)))


def _sanitize_prior_summary(enc_type: str, raw_summary: Optional[str]) -> Optional[str]:
    """Return a sanitized prior-visit summary block, or None if not applicable."""
    if enc_type != "follow_up" or not raw_summary:
        return None
    safe_lines = [
        line for line in raw_summary.strip().splitlines()
        if not any(line.lstrip().startswith(kw) for kw in _SUMMARY_BLOCKED_PREFIXES)
    ]
    return f"\n<prior_summary>\n{chr(10).join(safe_lines)[:500]}\n</prior_summary>\n"


async def assemble_record(
    intent_result: "IntentResult",  # type: ignore[name-defined]
    text: str,
    history: list[dict],
    doctor_id: str,
    patient_id: Optional[int] = None,
) -> MedicalRecord:
    """Build a MedicalRecord from intent structured_fields or by calling the structuring LLM.

    When structured_fields are present (single-LLM path), content is assembled
    from the 8 clinical section keys and no second LLM call is made.

    When structured_fields are absent, the structuring LLM is called with:
      - Filtered history (clinical turns only, last 6)
      - Encounter type (first_visit | follow_up | unknown)
      - Prior-visit summary injected as context for follow-up encounters

    Does NOT save the record — that is the caller's responsibility.

    Raises:
        ValueError: If structuring LLM rejects the input as non-clinical.
        Exception: Any other structuring or DB error propagates to the caller.
    """
    if intent_result.structured_fields:
        return _record_from_structured_fields(intent_result, text)

    full_text = _build_full_text(text, history)

    async def _detect() -> str:
        async with AsyncSessionLocal() as s:
            return await detect_encounter_type(s, doctor_id, patient_id, text)

    async def _prior() -> Optional[str]:
        if patient_id is None:
            return None
        try:
            from services.patient.prior_visit import get_prior_visit_summary
            return await get_prior_visit_summary(doctor_id, patient_id)
        except Exception:
            return None

    enc_type, raw_summary = await asyncio.gather(_detect(), _prior())
    prior_summary = _sanitize_prior_summary(enc_type, raw_summary)

    log(f"[domain] structuring enc_type={enc_type} prior={'yes' if prior_summary else 'no'} doctor={doctor_id}")
    return await structure_medical_record(
        full_text,
        encounter_type=enc_type,
        prior_visit_summary=prior_summary,
    )
