"""Match a patient upload against pending workup/lab tasks (ADR 0020).

When a patient uploads lab or imaging results, this module uses an LLM to
determine which pending task the upload fulfils.  High-confidence matches
(>= 0.7) are returned with a confirmation prompt; low-confidence or
ambiguous results fall back to manual selection from the full task list.

LLM call pattern mirrors ``triage.py``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.log import log


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    """Output of ``match_upload``."""

    matched_task_id: Optional[int]
    confidence: float
    confirmation_text: str
    pending_tasks: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM call (reuses triage provider resolution)
# ---------------------------------------------------------------------------

async def _call_matcher_llm(system_prompt: str, user_content: str) -> str:
    """Make a single matcher LLM call. Returns raw response text."""
    from domain.patient_lifecycle.triage import (
        _get_triage_client,
        _resolve_provider,
    )
    from infra.llm.resilience import call_with_retry_and_fallback
    from infra.observability.observability import trace_block

    import os

    provider_name, provider = _resolve_provider()
    client = _get_triage_client(provider_name, provider)

    async def _call(model_name: str):
        with trace_block("llm", "upload_matcher.chat_completion", {"provider": provider_name, "model": model_name}):
            return await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0,
            )

    response = await call_with_retry_and_fallback(
        _call,
        primary_model=provider["model"],
        max_attempts=int(os.environ.get("TRIAGE_LLM_ATTEMPTS", "2")),
        op_name="upload_matcher.chat_completion",
    )
    raw = response.choices[0].message.content or ""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    return raw


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_MATCH_SYSTEM_PROMPT = """\
你是一个医疗文件匹配系统。你的任务是将患者上传的检查/化验结果与待完成的医嘱任务进行匹配。

## 待完成任务列表

{tasks_json}

## 匹配规则

- 分析上传内容的关键词（检查类型、器官部位、化验项目等）
- 与任务标题和内容进行语义匹配
- 如果明确匹配到一个任务，返回该任务的 id 和高置信度
- 如果匹配模糊或可能匹配多个任务，返回低置信度

## 输出格式

返回严格的 JSON：
```json
{{"matched_task_id": 5, "confidence": 0.9, "confirmation_text": "这是颈椎MRI的结果吗？"}}
```

- matched_task_id: 匹配到的任务 id（整数），无法确定时为 null
- confidence: 0.0-1.0 的置信度
- confirmation_text: 用于向患者确认的提示语（中文，简洁友好）

仅返回 JSON，不要包含任何其他文字。
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def match_upload(
    extracted_content: str,
    pending_tasks: List[Dict[str, Any]],
) -> MatchResult:
    """Match extracted upload text against a list of pending tasks.

    Parameters
    ----------
    extracted_content:
        Plain-text content already extracted from the uploaded file by the
        Vision LLM.
    pending_tasks:
        Each dict must contain at least ``id``, ``task_type``, ``title``,
        and optionally ``content``.

    Returns
    -------
    MatchResult
        If confidence >= 0.7, ``matched_task_id`` is set and
        ``confirmation_text`` contains a patient-facing prompt.
        Otherwise ``matched_task_id`` is None and ``pending_tasks`` carries
        the full list for the patient to choose from.
    """
    if not pending_tasks:
        return MatchResult(
            matched_task_id=None,
            confidence=0.0,
            confirmation_text="",
            pending_tasks=[],
        )

    tasks_json = json.dumps(pending_tasks, ensure_ascii=False, indent=2)
    system = _MATCH_SYSTEM_PROMPT.replace("{tasks_json}", tasks_json)

    try:
        raw = await _call_matcher_llm(system, extracted_content)
        data = json.loads(raw)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log(f"[upload_matcher] parse error: {exc}", level="warning")
        return MatchResult(
            matched_task_id=None,
            confidence=0.0,
            confirmation_text="",
            pending_tasks=pending_tasks,
        )
    except Exception as exc:
        log(f"[upload_matcher] LLM call failed: {exc}", level="error")
        return MatchResult(
            matched_task_id=None,
            confidence=0.0,
            confirmation_text="",
            pending_tasks=pending_tasks,
        )

    matched_task_id = data.get("matched_task_id")
    confidence = float(data.get("confidence", 0.0))
    confirmation_text = str(data.get("confirmation_text", ""))

    # Validate that matched_task_id is actually in the pending list
    valid_ids = {t["id"] for t in pending_tasks}
    if matched_task_id is not None and matched_task_id not in valid_ids:
        log(
            f"[upload_matcher] LLM returned invalid task id {matched_task_id}",
            level="warning",
        )
        matched_task_id = None
        confidence = 0.0

    # High confidence → return match; low → return full list for selection
    if confidence >= 0.7 and matched_task_id is not None:
        return MatchResult(
            matched_task_id=matched_task_id,
            confidence=confidence,
            confirmation_text=confirmation_text,
            pending_tasks=[],
        )

    return MatchResult(
        matched_task_id=None,
        confidence=confidence,
        confirmation_text=confirmation_text,
        pending_tasks=pending_tasks,
    )
