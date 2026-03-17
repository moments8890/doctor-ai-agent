"""Understand phase: classify intent and extract entities (ADR 0012 §3)."""
from __future__ import annotations

import json
import os
from dataclasses import fields as dc_fields
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.runtime.types import (
    ARGS_TYPE_TABLE,
    ActionIntent,
    ActionType,
    Clarification,
    ClarificationKind,
    UnderstandError,
    UnderstandResult,
)
from utils.log import log
from utils.prompt_loader import get_prompt_sync


_UNDERSTAND_PROMPT: Optional[str] = None
_MAX_ACTIONS = 3


def _get_prompt() -> str:
    global _UNDERSTAND_PROMPT
    if _UNDERSTAND_PROMPT is None:
        _UNDERSTAND_PROMPT = get_prompt_sync("understand")
    return _UNDERSTAND_PROMPT


async def understand(
    text: str,
    recent_turns: List[Dict[str, str]],
    ctx: Any,  # DoctorCtx — avoid circular import
) -> UnderstandResult:
    """Classify user intent and extract entities. Single LLM call."""
    from openai import AsyncOpenAI
    from services.ai.llm_client import _PROVIDERS

    provider_name = os.environ.get("CONVERSATION_LLM") or os.environ.get("ROUTING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        provider_name = "deepseek"
        provider = _PROVIDERS["deepseek"]

    current_date = datetime.now().strftime("%Y-%m-%d")
    timezone = os.environ.get("TZ", "Asia/Shanghai")
    current_patient = ctx.workflow.patient_name or "未选择"

    prompt_template = _get_prompt()
    system_prompt = (
        prompt_template
        .replace("{current_date}", current_date)
        .replace("{timezone}", timezone)
        .replace("{current_patient}", current_patient)
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in recent_turns[-10:]:
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
    messages.append({"role": "user", "content": text})

    extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("CONVERSATION_LLM_TIMEOUT", "30")),
        max_retries=0,
        default_headers=extra_headers,
    )

    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[understand:{provider_name}:{model_name}]"
    log(f"{_tag} request: {text[:80]}")

    try:
        completion = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=1000,
        )
    except Exception as e:
        log(f"{_tag} LLM call failed ({type(e).__name__}): {e}", level="error")
        raise UnderstandError(str(e)) from e

    raw = completion.choices[0].message.content or ""
    log(f"{_tag} response: {raw[:200]}")
    return _parse_response(raw)


def _parse_response(raw: Optional[str]) -> UnderstandResult:
    """Parse LLM JSON response into UnderstandResult with invariant enforcement."""
    if not raw:
        raise UnderstandError("empty LLM response")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UnderstandError(f"invalid JSON: {e}") from e

    # Parse clarification
    clarification: Optional[Clarification] = None
    raw_clar = data.get("clarification")
    if raw_clar and isinstance(raw_clar, dict):
        try:
            kind = ClarificationKind(raw_clar.get("kind", ""))
        except ValueError:
            kind = ClarificationKind.unsupported
        clarification = Clarification(
            kind=kind,
            missing_fields=raw_clar.get("missing_fields", []),
            options=raw_clar.get("options", []),
            suggested_question=raw_clar.get("suggested_question"),
        )

    # Parse actions: new array format takes precedence over legacy flat format
    raw_actions = data.get("actions")
    if isinstance(raw_actions, list):
        actions = _parse_actions_list(raw_actions)
    else:
        # Legacy flat format: wrap single action in list
        action_type, args = _parse_single_action(data)
        actions = [ActionIntent(action_type=action_type, args=args)]

    # Cap at _MAX_ACTIONS
    if len(actions) > _MAX_ACTIONS:
        log(f"[understand] response contained {len(actions)} actions, capping at {_MAX_ACTIONS}", level="warning")
        actions = actions[:_MAX_ACTIONS]

    # Parse chat_reply
    chat_reply: Optional[str] = data.get("chat_reply")

    # Invariant: strip chat_reply when any action is non-none
    if any(a.action_type != ActionType.none for a in actions):
        chat_reply = None

    # Precedence: clarification wins over chat_reply
    if clarification and chat_reply:
        chat_reply = None

    return UnderstandResult(
        actions=actions,
        chat_reply=chat_reply,
        clarification=clarification,
    )


def _parse_actions_list(raw_actions: list) -> List[ActionIntent]:
    """Parse a list of action dicts (new array format) into ActionIntent objects."""
    actions: List[ActionIntent] = []
    for item in raw_actions:
        if not isinstance(item, dict):
            log(f"[understand] skipping non-dict action item: {item!r}", level="warning")
            continue
        action_type, args = _parse_single_action(item)
        actions.append(ActionIntent(action_type=action_type, args=args))
    if not actions:
        actions = [ActionIntent(action_type=ActionType.none, args=None)]
    return actions


def _parse_single_action(data: dict) -> tuple:
    """Parse action_type and args from a flat dict. Returns (ActionType, args)."""
    raw_action = data.get("action_type", "none")
    try:
        action_type = ActionType(raw_action)
    except ValueError:
        log(f"[understand] unknown action_type '{raw_action}', degrading to none", level="warning")
        action_type = ActionType.none
    args = _parse_args(action_type, data.get("args") or {})
    return action_type, args


def _parse_args(action_type: ActionType, raw_args: Dict[str, Any]) -> Optional[Any]:
    """Parse raw args dict into typed dataclass, with validation."""
    if action_type == ActionType.none:
        return None

    args_cls = ARGS_TYPE_TABLE.get(action_type)
    if args_cls is None or args_cls is type(None):
        return None

    # Get valid field names for the dataclass
    valid_fields = {f.name for f in dc_fields(args_cls)}
    filtered = {k: v for k, v in raw_args.items() if k in valid_fields}

    # Clamp limit for query_records
    if action_type == ActionType.query:
        limit = filtered.get("limit")
        if limit is not None:
            try:
                limit = int(limit)
                filtered["limit"] = min(max(limit, 1), 10)
            except (ValueError, TypeError):
                filtered["limit"] = 5

    # Check required fields before constructing
    required = {
        f.name for f in dc_fields(args_cls)
        if f.default is dc_fields.__class__  # no clean sentinel in 3.9
    }
    # Dataclass fields without defaults are required — detect via try
    try:
        return args_cls(**filtered)
    except TypeError as e:
        # Missing required field → surface as clarification, not crash
        missing = str(e)  # e.g. "__init__() missing 1 required ... 'patient_name'"
        log(f"[understand] args parse failed for {action_type}: {missing}", level="warning")
        return None  # caller handles None args via resolve's missing_field check
