"""Conversation model — one LLM call per turn (ADR 0011 §7)."""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from messages import M
from services.runtime.models import (
    ActionRequest,
    DoctorCtx,
    MEMORY_FIELDS,
    ModelOutput,
    VALID_ACTION_TYPES,
)
from utils.log import log


def _build_context_block(ctx: DoctorCtx) -> str:
    """Serialize context to a concise string for the LLM."""
    parts: list[str] = []
    wf = ctx.workflow
    if wf.patient_id:
        parts.append(f"{M.ctx_patient}: {wf.patient_name} (id={wf.patient_id})")
    else:
        parts.append(f"{M.ctx_patient}: {M.ctx_no_patient}")

    mem = ctx.memory
    if mem.working_note:
        parts.append(f"{M.ctx_note}: {mem.working_note}")
    if mem.candidate_patient:
        parts.append(f"{M.ctx_candidate}: {json.dumps(mem.candidate_patient, ensure_ascii=False)}")
    if mem.summary:
        parts.append(f"{M.ctx_summary}: {mem.summary}")

    return "\n".join(parts)


def _build_messages(
    ctx: DoctorCtx,
    user_input: str,
    recent_turns: List[dict],
) -> List[dict]:
    """Assemble the message list for the LLM call."""
    context_block = _build_context_block(ctx)
    system_content = f"{M.system_prompt}\n\n## {M.ctx_patient}\n{context_block}"

    messages: list[dict] = [{"role": "system", "content": system_content}]

    for turn in recent_turns[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_input})
    return messages


def _parse_model_response(raw: str) -> ModelOutput:
    """Parse LLM JSON response into ModelOutput."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log(f"[conversation] JSON parse failed, raw={raw[:200]}")
        return ModelOutput(reply=M.parse_error_reply)

    reply = data.get("reply") or M.default_reply

    action_request: Optional[ActionRequest] = None
    ar = data.get("action_request")
    if isinstance(ar, dict):
        action_type = ar.get("type", "none")
        if action_type in VALID_ACTION_TYPES:
            action_request = ActionRequest(
                type=action_type,
                patient_name=ar.get("patient_name"),
                patient_gender=ar.get("patient_gender"),
                patient_age=_safe_int(ar.get("patient_age")),
            )
        else:
            log(f"[conversation] invalid action type: {action_type}")

    memory_patch: Optional[Dict] = None
    mp = data.get("memory_patch")
    if isinstance(mp, dict):
        memory_patch = {k: v for k, v in mp.items() if k in MEMORY_FIELDS}
        if not memory_patch:
            memory_patch = None

    return ModelOutput(reply=reply, memory_patch=memory_patch, action_request=action_request)


def _safe_int(val: object) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


async def call_conversation_model(
    ctx: DoctorCtx,
    user_input: str,
    recent_turns: List[dict],
) -> ModelOutput:
    """One LLM call per turn. Returns structured ModelOutput."""
    from openai import AsyncOpenAI
    from services.ai.llm_client import _PROVIDERS

    provider_name = os.environ.get("CONVERSATION_LLM") or os.environ.get("ROUTING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        provider_name = "deepseek"
        provider = _PROVIDERS["deepseek"]

    extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("CONVERSATION_LLM_TIMEOUT", "30")),
        max_retries=0,
        default_headers=extra_headers,
    )

    messages = _build_messages(ctx, user_input, recent_turns)
    model_name = provider.get("model", "deepseek-chat")

    log(f"[conversation] calling {provider_name}/{model_name} doctor={ctx.doctor_id} len={len(user_input)}")

    try:
        completion = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=1000,
            temperature=0.1,
        )
    except TimeoutError:
        log(f"[conversation] LLM timeout doctor={ctx.doctor_id} provider={provider_name}")
        return ModelOutput(reply=M.service_unavailable)
    except ConnectionError as e:
        log(f"[conversation] LLM connection error doctor={ctx.doctor_id}: {e}", level="error", exc_info=True)
        return ModelOutput(reply=M.service_unavailable)
    except Exception as e:
        # Rate-limit (429), auth (401), server (5xx), or unexpected errors
        log(f"[conversation] LLM call FAILED ({type(e).__name__}) doctor={ctx.doctor_id}: {e}", level="error", exc_info=True)
        return ModelOutput(reply=M.service_unavailable)

    raw = completion.choices[0].message.content or ""
    log(f"[conversation] response: {raw[:200]}")
    return _parse_model_response(raw)
