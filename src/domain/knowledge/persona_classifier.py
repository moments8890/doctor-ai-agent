"""Classify doctor edits as style/factual/context-specific for persona learning."""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from utils.log import log


CLASSIFICATION_PROMPT = """分析以下医生对AI草稿的修改，判断这是风格偏好还是事实纠正。

AI原文：
{original}

医生修改后：
{edited}

请用JSON格式回答（不要输出其他内容）：
{{
  "type": "style" 或 "factual" 或 "context_specific",
  "persona_field": "reply_style" 或 "closing" 或 "structure" 或 "avoid" 或 "edits" 或 null,
  "summary": "一句话结构性描述（不含患者姓名、日期等个人信息）",
  "confidence": "low" 或 "medium" 或 "high"
}}

判断规则：
- 如果医生改变了语气、称呼、结构、删除了某类内容 → type=style
- 如果医生纠正了药名、剂量、检查项目、医学事实 → type=factual
- 如果修改只适用于这个特定患者场景 → type=context_specific
- confidence=high 当修改模式非常明确（如删除整段、改变称呼方式）
- confidence=low 当修改很小或意图模糊"""


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

    prompt = CLASSIFICATION_PROMPT.format(
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
