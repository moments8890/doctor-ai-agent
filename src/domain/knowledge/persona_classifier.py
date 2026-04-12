"""Classify doctor edits as style/factual/context-specific for persona learning."""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from utils.log import log
from utils.prompt_loader import get_prompt_sync


def compute_pattern_hash(field: str, summary: str) -> str:
    """Compute a hash for suppression matching."""
    normalized = f"{field}:{summary.strip().lower()}"
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


async def classify_edit(original: str, edited: str) -> Optional[dict]:
    """Classify a doctor edit using LLM.

    Returns dict with type, persona_field, summary, confidence.
    Returns None if classification fails.
    """
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

        # Extract JSON from response (may be wrapped in markdown code block)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(text)

        # Validate required fields
        valid_types = {"style", "factual", "context_specific"}
        valid_fields = {"reply_style", "closing", "structure", "avoid", "edits", None}
        if result.get("type") not in valid_types:
            return None
        if result.get("persona_field") not in valid_fields:
            result["persona_field"] = None

        return result
    except (json.JSONDecodeError, Exception) as exc:
        log(f"[persona_classifier] classification failed: {exc}", level="warning")
        return None
