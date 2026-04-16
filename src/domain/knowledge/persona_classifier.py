"""Classify doctor edits as style/factual/context-specific; emit typed model."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, model_validator

from utils.log import log
from utils.prompt_loader import get_prompt_sync


class LearningType(str, Enum):
    style = "style"
    factual = "factual"
    context_specific = "context_specific"


class PersonaField(str, Enum):
    reply_style = "reply_style"
    closing = "closing"
    structure = "structure"
    avoid = "avoid"
    edits = "edits"


class KbCategory(str, Enum):
    custom = "custom"
    diagnosis = "diagnosis"
    followup = "followup"
    medication = "medication"


class ClassifyResult(BaseModel):
    type: LearningType
    persona_field: Optional[PersonaField] = None
    summary: str = Field(min_length=1, max_length=500)
    confidence: Literal["low", "medium", "high"]
    kb_category: Optional[KbCategory] = None
    proposed_kb_rule: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _enforce_type_contract(self) -> "ClassifyResult":
        if self.type == LearningType.style:
            if not self.persona_field:
                raise ValueError("persona_field required when type=style")
            if self.kb_category or self.proposed_kb_rule:
                raise ValueError("kb fields must be empty when type=style")
        elif self.type == LearningType.factual:
            if not self.kb_category:
                raise ValueError("kb_category required when type=factual")
            if not self.proposed_kb_rule.strip():
                raise ValueError("proposed_kb_rule required when type=factual")
            if self.persona_field:
                raise ValueError("persona_field must be empty when type=factual")
        else:  # context_specific
            if self.persona_field or self.kb_category or self.proposed_kb_rule:
                raise ValueError("all learning fields must be empty when type=context_specific")
        return self


def compute_pattern_hash(field: str, summary: str) -> str:
    """Persona-side hash — signature unchanged (existing callers depend on it)."""
    normalized = f"{field}:{summary.strip().lower()}"
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def compute_kb_pattern_hash(category: str, summary: str) -> str:
    """KB-side hash — distinct namespace prevents collision with persona hashes."""
    normalized = f"kb:{category}:{summary.strip().lower()}"
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _coerce_empty_to_none(raw: dict) -> dict:
    """Prompt emits '' for empty optional enums; convert to None before Pydantic."""
    out = dict(raw)
    for key in ("persona_field", "kb_category"):
        if out.get(key) == "":
            out[key] = None
    return out


async def classify_edit(original: str, edited: str) -> Optional[ClassifyResult]:
    """Classify a doctor edit using LLM. Returns ClassifyResult or None on any failure."""
    if not original or not edited:
        return None
    if original.strip() == edited.strip():
        return None

    template = get_prompt_sync("persona-classify")
    prompt = template.format(
        original=original[:500],
        edited=edited[:500],
    )

    try:
        from agent.llm import llm_call
        response = await llm_call(
            messages=[
                {"role": "system", "content": "你是一个分析医生编辑行为的助手。只输出JSON，不要输出其他内容。"},
                {"role": "user", "content": prompt},
            ],
            op_name="persona_classify",
        )
        if not response:
            return None

        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        raw = json.loads(text)
        coerced = _coerce_empty_to_none(raw)
        return ClassifyResult.model_validate(coerced)
    except (json.JSONDecodeError, ValidationError) as exc:
        log(f"[persona_classifier] invalid output: {exc}", level="warning")
        return None
    except Exception as exc:
        log(f"[persona_classifier] unexpected error: {exc}", level="warning")
        return None
