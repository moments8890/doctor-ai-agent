"""Compose phase: generate user-facing reply from execution results (ADR 0012 §9).

Three strategies:
- compose_template   — deterministic, for write actions and errors
- compose_llm        — LLM call, for read queries
- compose_clarification — deterministic, for structured clarifications
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from messages import M
from services.runtime.types import (
    ActionType,
    Clarification,
    ClarificationKind,
    CommitResult,
    ReadResult,
)
from utils.log import log


# ── Template composer (ADR 0012 §9 — template response mode) ───────────────


def compose_template(
    result: Any,  # ReadResult | CommitResult
    action_type: ActionType,
    patient_name: Optional[str] = None,
) -> str:
    """Format a template reply from execution result data."""

    # Error path
    if result.status == "error":
        error_key = getattr(result, "error_key", None)
        if error_key and hasattr(M, error_key):
            return getattr(M, error_key)
        return M.execute_error

    # CommitResult paths
    if isinstance(result, CommitResult):
        return _compose_commit(result, action_type, patient_name)

    # ReadResult paths (truncation notice only — LLM does the main reply)
    if isinstance(result, ReadResult):
        return _compose_read_template(result)

    return M.default_reply


def _compose_commit(
    result: CommitResult,
    action_type: ActionType,
    patient_name: Optional[str],
) -> str:
    """Template for commit engine results."""
    name = patient_name or ""
    data = result.data or {}

    if action_type == ActionType.record:
        if data.get("patient_only"):
            return M.patient_registered.format(name=name)
        preview = data.get("preview", "")
        return M.record_created.format(patient=name, preview=preview)

    if action_type == ActionType.update:
        preview = data.get("preview", "")
        return M.record_updated.format(patient=name, preview=preview)

    if action_type == ActionType.task:
        dt_display = data.get("datetime_display", "")
        title = data.get("title") or "任务"
        if not dt_display:
            return f"已为【{name}】创建任务：{title}"
        noon_default = data.get("noon_default", False)
        if noon_default:
            return f"已为【{name}】创建任务：{title}，时间：{dt_display}（默认中午12点）。"
        return f"已为【{name}】创建任务：{title}，时间：{dt_display}。"

    return M.default_reply


def _compose_read_template(result: ReadResult) -> str:
    """Minimal template fallback for read results (used on compose_llm failure)."""
    if result.status == "empty":
        return "未找到相关记录。"

    total = result.total_count or 0
    shown = len(result.data) if result.data else 0

    if result.truncated and total > shown:
        return M.truncation_notice.format(total=total, shown=shown)

    return M.compose_error_fallback.format(count=shown)


# ── LLM composer (ADR 0012 §9 — llm_compose response mode) ─────────────────


async def compose_llm(
    result: ReadResult,
    user_input: str,
    patient_name: Optional[str] = None,
) -> str:
    """Summarise fetched data via LLM. Falls back to template on failure."""
    if result.status == "empty":
        return "未找到相关记录。"

    if not result.data:
        return _compose_read_template(result)

    try:
        summary = await _call_compose_llm(result.data, user_input, patient_name)

        # Truncation notice
        if result.truncated and result.total_count:
            shown = len(result.data)
            summary += f"\n\n{M.truncation_notice.format(total=result.total_count, shown=shown)}"

        return summary
    except Exception as e:
        log(f"[compose] LLM failed, falling back to template: {e}", level="error")
        return _compose_read_template(result)


async def _call_compose_llm(
    data: Any,
    user_input: str,
    patient_name: Optional[str],
) -> str:
    """Single LLM call to summarise fetched data naturally."""
    import json

    from openai import AsyncOpenAI
    from services.ai.llm_client import _PROVIDERS

    provider_name = os.environ.get("CONVERSATION_LLM") or os.environ.get("ROUTING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        provider_name = "deepseek"
        provider = _PROVIDERS["deepseek"]

    # Build concise data summary for the LLM
    data_text = json.dumps(data, ensure_ascii=False, default=str)
    if len(data_text) > 4000:
        data_text = data_text[:4000] + "..."

    name_ctx = f"患者【{patient_name}】的" if patient_name else ""

    system_prompt = (
        "你是医疗助手的回复模块。根据查询结果，用自然、简洁的中文回复医生。"
        "直接给出信息，不要添加建议或解释。"
    )
    user_prompt = (
        f"医生问：{user_input}\n\n"
        f"{name_ctx}查询结果：\n{data_text}\n\n"
        "请用简洁自然的中文总结以上信息回复医生。"
    )

    extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("CONVERSATION_LLM_TIMEOUT", "30")),
        max_retries=0,
        default_headers=extra_headers,
    )
    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[compose:{provider_name}:{model_name}]"
    log(f"{_tag} request: {user_input[:80]}")
    response = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=500,
    )
    reply = response.choices[0].message.content or M.default_reply
    log(f"{_tag} response: {reply[:200]}")
    return reply


# ── Clarification composer (ADR 0012 §4 composition rule) ──────────────────


def compose_clarification(c: Clarification) -> str:
    """Render a Clarification into a user-facing reply string."""

    # Deterministic kinds → template only
    if c.kind == ClarificationKind.missing_field:
        if c.missing_fields:
            field_labels = {
                "patient_name": "患者姓名",
                "scheduled_for": "预约时间",
            }
            label = field_labels.get(c.missing_fields[0], c.missing_fields[0])
            return M.clarify_missing_field.format(field_label=label)
        return M.need_patient_name

    if c.kind == ClarificationKind.ambiguous_patient:
        if c.options:
            lines = [f"{i+1}. {opt.get('name', '?')}" for i, opt in enumerate(c.options)]
            return M.clarify_ambiguous_patient.format(options_text="\n".join(lines))
        if c.suggested_question:
            return c.suggested_question
        return M.need_patient_name

    if c.kind == ClarificationKind.not_found:
        msg_key = c.message_key
        if msg_key == "clarify_not_found_too_many":
            return M.clarify_not_found_too_many
        return M.clarify_not_found.format(name=c.searched_name or "?")

    if c.kind == ClarificationKind.invalid_time:
        return M.clarify_invalid_time.format(reason="请检查日期和时间")

    if c.kind == ClarificationKind.blocked:
        return M.clarify_blocked

    if c.kind == ClarificationKind.unsupported:
        return M.clarify_unsupported

    # Semantic kind: ambiguous_intent
    if c.kind == ClarificationKind.ambiguous_intent:
        if c.suggested_question:
            return c.suggested_question
        return M.clarify_ambiguous_intent

    return M.clarify_ambiguous_intent
