"""AI triage for patient messages (ADR 0020).

Classifies every inbound patient message into a triage category and routes it
to the appropriate handler:

- **informational** — AI answers directly using patient context
- **symptom_report / side_effect** — escalated to doctor with structured summary
- **general_question** — escalated (safe default for ambiguous messages)
- **urgent** — immediate safety guidance + doctor notification

This is safety-critical code: classification errors can suppress clinical
content.  The system prompt is deliberately conservative — ambiguous messages
are classified to the *most clinical* category, and low-confidence outputs
default to ``general_question`` (escalation).

Sub-modules
-----------
- ``triage_handlers`` — handle_informational, handle_escalation, handle_urgent
- ``triage_context``  — load_patient_context
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

from utils.log import log
from utils.prompt_loader import get_prompt_sync

# Re-export handlers and context loader so existing importers work unchanged.
from domain.patient_lifecycle.triage_handlers import (  # noqa: F401
    handle_informational,
    handle_escalation,
    handle_urgent,
)
from domain.patient_lifecycle.triage_context import load_patient_context  # noqa: F401


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TriageCategory(str, Enum):
    """Patient message triage categories."""
    informational = "informational"
    symptom_report = "symptom_report"
    side_effect = "side_effect"
    general_question = "general_question"
    urgent = "urgent"


_VALID_CATEGORIES = {c.value for c in TriageCategory}


# -- Pydantic response model for classify() --------------------------------

class ClassifyLLMResponse(BaseModel):
    """LLM response for triage classification."""
    category: TriageCategory
    confidence: float = Field(ge=0.0, le=1.0)


# Categories that trigger escalation to doctor (not AI-handled).
_ESCALATION_CATEGORIES = {
    TriageCategory.symptom_report,
    TriageCategory.side_effect,
    TriageCategory.general_question,
}

# Categories eligible for KB-aware downgrade to informational.
# If KB has a matching answer, the message can be auto-replied instead of escalated.
# Never downgrade symptom_report (needs clinical judgment) or urgent.
_KB_DOWNGRADE_ELIGIBLE = {
    TriageCategory.side_effect,
    TriageCategory.general_question,
}


@dataclass
class TriageResult:
    """Output of the classify() step."""
    category: TriageCategory
    confidence: float


# ---------------------------------------------------------------------------
# LLM provider helper (shared with handlers via env var name)
# ---------------------------------------------------------------------------

def _triage_env_var() -> str:
    """Resolve env var for triage LLM: TRIAGE_LLM → ROUTING_LLM → groq."""
    if os.environ.get("TRIAGE_LLM"):
        return "TRIAGE_LLM"
    return "ROUTING_LLM"


# ---------------------------------------------------------------------------
# Step 1: Classify
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM_PROMPT = get_prompt_sync("intent/triage-classify")

# Minimum KB relevance score to trigger downgrade (token overlap)
_KB_DOWNGRADE_MIN_SCORE = 4


async def _check_kb_can_answer(message: str, doctor_id: str, patient_context_text: str) -> bool:
    """Check if doctor's KB has relevant content for this message.

    Returns True if KB items score highly enough against the message,
    meaning the KB likely has a usable answer.
    """
    try:
        from domain.knowledge.knowledge_context import load_knowledge, _score_item
        from db.engine import AsyncSessionLocal
        from db.crud import list_doctor_knowledge_items
        from domain.knowledge.knowledge_crud import _decode_knowledge_payload, knowledge_limits

        if not doctor_id:
            return False

        limits = knowledge_limits()
        async with AsyncSessionLocal() as session:
            items = await list_doctor_knowledge_items(
                session, doctor_id, limit=limits["candidate_limit"],
            )
        if not items:
            return False

        scoring_query = f"{message} {patient_context_text[:500]}"
        for item in items:
            text, _source, _conf, _url, _fp = _decode_knowledge_payload(item.content)
            if not text:
                continue
            score = _score_item(scoring_query, text)
            if score >= _KB_DOWNGRADE_MIN_SCORE:
                log(f"[triage] KB downgrade: item {item.id} scored {score} for message, eligible for auto-reply")
                return True
        return False
    except Exception as exc:
        log(f"[triage] KB downgrade check failed (non-fatal): {exc}", level="warning")
        return False


async def classify(message: str, patient_context: dict, doctor_id: str = "") -> TriageResult:
    """Classify a patient message into a triage category.

    Uses structured_call() with ClassifyLLMResponse for validated output.
    If confidence < 0.7, defaults to ``general_question`` (safe escalation).
    """
    from agent.llm import structured_call

    context_text = json.dumps(patient_context, ensure_ascii=False, indent=2)
    system = _CLASSIFY_SYSTEM_PROMPT.replace("{patient_context}", context_text)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]

    try:
        result = await structured_call(
            response_model=ClassifyLLMResponse,
            messages=messages,
            op_name="triage.classify",
            env_var=_triage_env_var(),
            temperature=0.1,
            max_tokens=200,
            max_retries=2,
        )
    except Exception as exc:
        log(f"[triage] classify failed: {exc}", level="error")
        return TriageResult(category=TriageCategory.general_question, confidence=0.0)

    # Low confidence → safe default
    if result.confidence < 0.7:
        log(f"[triage] low confidence {result.confidence:.2f} for '{result.category.value}', escalating to general_question")
        return TriageResult(
            category=TriageCategory.general_question,
            confidence=result.confidence,
        )

    return TriageResult(
        category=result.category,
        confidence=result.confidence,
    )
