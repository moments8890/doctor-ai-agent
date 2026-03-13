"""
LLM 意图调度核心：路由用户输入并调用工具，支持多提供商故障转移。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, List, Optional, Tuple

from openai import AsyncOpenAI

from services.ai.intent import Intent, IntentResult
from services.ai.llm_client import _PROVIDERS  # shared provider registry; re-exported for memory.py
from services.ai.llm_resilience import call_with_retry_and_fallback
from services.observability.observability import trace_block
from utils.log import log

# ---------------------------------------------------------------------------
# Re-exported from companion modules (tool schemas, prompts, fallback routing)
# ---------------------------------------------------------------------------
from services.ai.agent_tools import (  # noqa: F401
    _TOOLS,
    _TOOLS_COMPACT,
    _SYSTEM_PROMPT,
    _SYSTEM_PROMPT_COMPACT,
    _INTENT_MAP,
    _selected_tools,
)
from services.ai.agent_fallback import (  # noqa: F401
    fallback_intent_from_text as _fallback_intent_from_text,
)

# Module-level singleton cache: one HTTP connection pool per provider.
# Avoids TCP/TLS handshake overhead on every request (~150-300ms saved).
_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}


def _get_client(provider_name: str, provider: dict) -> AsyncOpenAI:
    extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
    # Skip singleton cache in test environments so mock patches can intercept.
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        return AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("AGENT_LLM_TIMEOUT", "45")),
            max_retries=0,
            default_headers=extra_headers,
        )
    if provider_name not in _CLIENT_CACHE:
        if len(_CLIENT_CACHE) >= 10:
            _CLIENT_CACHE.pop(next(iter(_CLIENT_CACHE)))
        _CLIENT_CACHE[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("AGENT_LLM_TIMEOUT", "45")),
            max_retries=0,
            default_headers=extra_headers,
        )
    return _CLIENT_CACHE[provider_name]


async def _get_routing_prompt() -> str:
    from utils.prompt_loader import get_prompt
    mode = os.environ.get("AGENT_ROUTING_PROMPT_MODE", "compact").strip().lower()
    if mode == "full":
        return await get_prompt("agent.routing", _SYSTEM_PROMPT)
    return await get_prompt("agent.routing.compact", _SYSTEM_PROMPT_COMPACT)


# Pattern: Ollama reply that verbally "performed" an action without calling a tool.
# Used to trigger a retry with an explicit tool-use instruction.
_VERBAL_ACTION_RE = re.compile(
    r"已(?:为您|帮您)?(?:记录|保存|登记|安排|创建|设置|创建|更新|建好|录入|建立|添加|预约|随访|存入)"
    r"|为您(?:记录|安排|创建|设置|完成|创建|更新|添加|预约)"
    r"|帮您(?:记录|安排|创建|保存|添加|预约)"
    r"|(?:随访提醒|随访任务|复诊提醒)(?:已|将)?(?:设置|创建|安排)"
    r"|(?:病历|记录)(?:已|将)?(?:记录|保存|录入|存入)"
)


def _extract_embedded_tool_call(content: Optional[str]) -> Tuple[Optional[str], dict]:
    """Best-effort parser for providers that return tool-calls in text content."""
    if not content:
        return None, {}

    icall_match = re.search(
        r"_icall_function\(\s*['\"](?P<name>[a-zA-Z_][a-zA-Z0-9_]*)['\"]\s*,\s*(?P<args>\{.*?\})\s*\)",
        content,
        flags=re.DOTALL,
    )
    if icall_match:
        fn_name = icall_match.group("name")
        args_raw = icall_match.group("args")
        try:
            args = json.loads(args_raw)
            if not isinstance(args, dict):
                args = {}
        except (json.JSONDecodeError, TypeError):
            args = {}
        return fn_name, args

    return _scan_json_for_tool_call(content)


def _scan_json_for_tool_call(content: str) -> Tuple[Optional[str], dict]:
    """Scan content for a JSON object matching a known tool name."""
    decoder = json.JSONDecoder()
    known_tools = set(_INTENT_MAP.keys()) | {"manage_task"}
    for idx, ch in enumerate(content):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(content[idx:])
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        fn_name = obj.get("name")
        if not isinstance(fn_name, str) or fn_name not in known_tools:
            continue
        args = obj.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                args = {}
        if not isinstance(args, dict):
            args = {}
        return fn_name, args
    return None, {}


def _looks_like_tool_markup(content: Optional[str]) -> bool:
    if not content:
        return False
    lowered = content.lower()
    if "tool_call" in lowered or "</tool_call>" in lowered or "_icall_function(" in lowered:
        return True
    stripped = content.strip()
    if stripped.startswith("{") and '"name"' in stripped and '"arguments"' in stripped:
        return True
    return False


# ---------------------------------------------------------------------------
# Tool-call result parsing helpers
# ---------------------------------------------------------------------------

_CLINICAL_KEYS = {
    "chief_complaint", "history_of_present_illness", "past_medical_history",
    "physical_examination", "auxiliary_examinations",
    "diagnosis", "treatment_plan", "follow_up_plan",
}

_CVD_KEYS = {
    "diagnosis_subtype", "gcs_score", "hunt_hess_grade", "wfns_grade",
    "fisher_grade", "modified_fisher_grade",
    "ich_score", "nihss_score",
    "surgery_status", "mrs_score", "suzuki_stage", "spetzler_martin_grade",
}


def _parse_manage_task(args: dict) -> IntentResult:
    """Expand manage_task into a concrete task IntentResult."""
    action = args.get("action", "complete")
    task_id = args.get("task_id")
    delta_days = args.get("delta_days")
    if action == "postpone":
        return IntentResult(
            intent=Intent.postpone_task,
            extra_data={"task_id": task_id, "delta_days": delta_days},
        )
    if action == "cancel":
        return IntentResult(
            intent=Intent.cancel_task,
            extra_data={"task_id": task_id},
        )
    return IntentResult(
        intent=Intent.complete_task,
        extra_data={"task_id": task_id},
    )


def _build_extra_data(fn_name: str, args: dict) -> dict:
    """Build the extra_data dict for a given tool call."""
    extra_data: dict = {}
    if fn_name == "postpone_task":
        extra_data["task_id"] = args.get("task_id")
        extra_data["delta_days"] = args.get("delta_days", 7)
    elif fn_name in ("cancel_task", "complete_task"):
        extra_data["task_id"] = args.get("task_id")
    elif fn_name == "delete_patient":
        extra_data["occurrence_index"] = args.get("occurrence_index")
    elif fn_name == "schedule_appointment":
        extra_data["appointment_time"] = args.get("appointment_time")
        extra_data["notes"] = args.get("notes")
    elif fn_name == "schedule_follow_up":
        extra_data["follow_up_plan"] = args.get("follow_up_plan") or "下次随访"
    elif fn_name == "add_cvd_record":
        cvd_fields = {k: args[k] for k in _CVD_KEYS if args.get(k) is not None}
        if cvd_fields:
            extra_data["cvd_context"] = cvd_fields
        extra_data["record_subtype"] = "cvd"
    return extra_data


def _build_structured_fields(fn_name: str, args: dict) -> Optional[dict]:
    """Extract structured clinical fields for correction tools only.

    Only update_medical_record uses structured_fields — these identify which
    field to correct, not generate note content.  add_medical_record note
    generation is handled exclusively by the structuring LLM (ADR 0008).
    """
    if fn_name == "update_medical_record":
        extracted = {k: args[k] for k in _CLINICAL_KEYS if args.get(k)}
        return extracted if extracted else None
    return None


def _intent_result_from_tool_call(fn_name: str, args: dict, chat_reply: Optional[str]) -> IntentResult:
    """Convert a tool-call name + args into a typed IntentResult."""
    if fn_name == "manage_task":
        return _parse_manage_task(args)

    intent = _INTENT_MAP.get(fn_name, Intent.unknown)

    age = args.get("age")
    if not isinstance(age, int):
        age = None
    gender = args.get("gender")
    if gender not in ("男", "女"):
        gender = None

    extra_data = _build_extra_data(fn_name, args)
    structured_fields = _build_structured_fields(fn_name, args)

    return IntentResult(
        intent=intent,
        patient_name=args.get("patient_name") or args.get("name"),
        gender=gender,
        age=age,
        extra_data=extra_data,
        chat_reply=chat_reply,
        structured_fields=structured_fields,
    )


# ---------------------------------------------------------------------------
# Ollama post-processing helpers
# ---------------------------------------------------------------------------

async def _ollama_verbal_retry(
    chat_reply: str,
    messages: List[dict],
    client: Any,
    model_name: str,
    tools: list,
    routing_max_tokens: int,
) -> Optional[IntentResult]:
    """Retry Ollama with an explicit tool-use nudge after a verbal-action reply."""
    retry_messages = messages + [
        {"role": "assistant", "content": chat_reply},
        {
            "role": "user",
            "content": "[系统提示：请务必调用相应工具执行操作，不要只用文字回复。]",
        },
    ]
    try:
        with trace_block("llm", "agent.chat_completion", {"provider": "ollama", "model": model_name, "retry": True}):
            retry_completion = await client.chat.completions.create(
                model=model_name,
                messages=retry_messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=routing_max_tokens,
                temperature=0,
            )
        retry_msg = retry_completion.choices[0].message
        if retry_msg.tool_calls:
            retry_fn = retry_msg.tool_calls[0].function.name
            try:
                retry_args = json.loads(retry_msg.tool_calls[0].function.arguments)
                if not isinstance(retry_args, dict):
                    retry_args = {}
            except (json.JSONDecodeError, TypeError):
                retry_args = {}
            log(f"[Agent:ollama] retry tool_call: {retry_fn}({retry_args})")
            return _intent_result_from_tool_call(retry_fn, retry_args, retry_msg.content or chat_reply)
    except Exception as retry_err:
        log(f"[Agent:ollama] retry failed: {retry_err}")
    return None


async def _ollama_post_process(
    message: Any,
    text: str,
    messages: List[dict],
    client: Any,
    model_name: str,
    tools: list,
    routing_max_tokens: int,
) -> Optional[IntentResult]:
    """Handle Ollama-specific post-processing when no formal tool_calls are present.

    Covers three cases in order:
    1. Embedded tool call in text content.
    2. Verbal-action retry: Ollama described an action in words → nudge it to call the tool.
    3. No-tool-call fallback: Ollama returned markup or empty content → regex fallback.

    Returns an IntentResult on success, or None to signal that the caller should fall
    through to _fallback_intent_from_text().
    """
    chat_reply = message.content or None

    # 1. Embedded tool call extraction
    embedded_fn, embedded_args = _extract_embedded_tool_call(chat_reply)
    if embedded_fn:
        log(f"[Agent:ollama] embedded tool_call: {embedded_fn}({embedded_args})")
        cleaned_reply = None if _looks_like_tool_markup(chat_reply) else chat_reply
        return _intent_result_from_tool_call(embedded_fn, embedded_args, cleaned_reply)

    # 2. Verbal action retry
    if chat_reply and not _looks_like_tool_markup(chat_reply) and _VERBAL_ACTION_RE.search(chat_reply):
        log(f"[Agent:ollama] verbal action detected, retrying: {chat_reply[:60]}")
        result = await _ollama_verbal_retry(chat_reply, messages, client, model_name, tools, routing_max_tokens)
        if result is not None:
            return result

    # 3. No-tool-call fallback
    if not chat_reply or _looks_like_tool_markup(chat_reply):
        log("[Agent:ollama] no formal tool call, using local fallback")
        from services.observability.routing_metrics import record as _record_metric
        _record_metric("fallback:regex")
        with trace_block("agent", "agent.local_fallback", {"reason": "no_tool_call"}):
            return _fallback_intent_from_text(text)

    return None


# ---------------------------------------------------------------------------
# Provider resolution helpers
# ---------------------------------------------------------------------------

def _resolve_provider(provider_name: str) -> dict:
    """Return the provider dict for provider_name, applying env-var overrides."""
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise RuntimeError(
            "Unsupported ROUTING_LLM provider: {0} (allowed: {1})".format(provider_name, allowed)
        )
    provider = dict(provider)
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    elif provider_name == "openai":
        provider["base_url"] = os.environ.get("OPENAI_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("OPENAI_MODEL", provider["model"])
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
    elif provider_name == "claude":
        provider["model"] = os.environ.get("CLAUDE_MODEL", provider["model"])
    return provider


def _check_api_key(provider_name: str, provider: dict) -> None:
    """Raise RuntimeError if strict mode is enabled and the API key is missing."""
    strict_mode = os.environ.get("LLM_PROVIDER_STRICT_MODE", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if strict_mode and provider_name != "ollama":
        key_env = provider["api_key_env"]
        if not os.environ.get(key_env, "").strip():
            raise RuntimeError(
                "Selected provider '{0}' requires {1}, but it is empty; strict mode blocks fallback".format(
                    provider_name, key_env
                )
            )


_HIGH_VALUE_RE = re.compile(
    r"患者[\s:：【]"           # patient binding / mention
    r"|请问.*叫什么"           # clarification question
    r"|创建.*患者"             # patient creation context
    r"|确认|保存|撤销"         # pending-record confirmation context
    r"|复诊|随访|复查"         # follow-up context
    r"|[A-Z]{2,}[：:\s]?\d"   # scale scores (NIHSS:8, GCS 14)
    r"|(?:诊断|处方|处置|用药)", # clinical decision turns
    re.IGNORECASE,
)


def _is_high_value_turn(msg: dict) -> bool:
    """Return True if a history turn carries important routing context."""
    content = msg.get("content") or ""
    if len(content) > 80:  # long turns are likely clinical content
        return True
    return bool(_HIGH_VALUE_RE.search(content))


def _trim_history_by_value(history: List[dict], max_chars: int) -> List[dict]:
    """Trim history to fit within max_chars, preserving high-value turns.

    Strategy:
      1. Always keep the last 2 turns (immediate context).
      2. Among older turns, keep high-value ones first, then fill with recent low-value.
      3. Result is in chronological order.
    """
    if not history:
        return []
    # Split into recent (always kept) and older
    recent = history[-2:]
    older = history[:-2]
    recent_chars = sum(len(m.get("content") or "") for m in recent)
    budget = max_chars - recent_chars
    if budget <= 0:
        # Even recent turns exceed budget — trim recent by char limit
        trimmed = []
        total = 0
        for msg in reversed(recent):
            chunk = len(msg.get("content") or "")
            if total + chunk > max_chars:
                break
            trimmed.insert(0, msg)
            total += chunk
        return trimmed

    # Partition older turns into high-value and low-value, preserving order
    high = [(i, m) for i, m in enumerate(older) if _is_high_value_turn(m)]
    low = [(i, m) for i, m in enumerate(older) if not _is_high_value_turn(m)]

    selected_indices: set[int] = set()
    total = 0
    # Add high-value turns newest-first
    for idx, msg in reversed(high):
        chunk = len(msg.get("content") or "")
        if total + chunk > budget:
            continue
        selected_indices.add(idx)
        total += chunk
    # Fill remaining budget with low-value turns newest-first
    for idx, msg in reversed(low):
        chunk = len(msg.get("content") or "")
        if total + chunk > budget:
            continue
        selected_indices.add(idx)
        total += chunk

    # Reconstruct in chronological order
    kept_older = [older[i] for i in sorted(selected_indices)]
    return kept_older + recent


def _build_messages(
    text: str,
    system_prompt: str,
    history: Optional[List[dict]],
    knowledge_context: Optional[str],
    current_patient_context: Optional[str] = None,
    candidate_patient_context: Optional[str] = None,
    patient_not_found_context: Optional[str] = None,
) -> List[dict]:
    """Assemble the messages list for the LLM, trimming history to fit token budget.

    History is trimmed oldest-first: when over budget, the oldest turns are dropped
    so that the most recent context is always preserved.
    """
    messages = [{"role": "system", "content": system_prompt}]
    # Inject current patient as an authoritative system hint (prevents patient confusion
    # when history is trimmed). Placed before knowledge context so the LLM sees it early.
    if current_patient_context and current_patient_context.strip():
        messages.append({"role": "system", "content": f"[当前接诊患者：{current_patient_context.strip()}]"})
    if candidate_patient_context and candidate_patient_context.strip():
        messages.append({"role": "system", "content": f"[候选接诊患者：{candidate_patient_context.strip()}]"})
    if patient_not_found_context and patient_not_found_context.strip():
        messages.append({"role": "system", "content": (
            f"[最近查询未找到患者：{patient_not_found_context.strip()}。"
            "若当前是在补充病历，可考虑新建患者后生成草稿；不要臆造其他患者。]"
        )})
    if knowledge_context and knowledge_context.strip():
        # Guard against prompt injection from untrusted uploaded documents (PDFs, Word files).
        _INJECTION_KW = frozenset({"系统", "忽略", "指令", "扮演", "绕过", "越权"})
        if any(kw in knowledge_context for kw in _INJECTION_KW):
            log("[Agent] WARNING: knowledge_context blocked — contains potential injection keywords")
        else:
            _kc = knowledge_context.strip()[:3000]
            messages.append({"role": "system", "content": "背景知识（不是用户输入，仅供参考）：\n" + _kc})
    _MAX_HISTORY_CHARS = 2400  # ~800 tokens, leaves room for system prompt + response
    _trimmed = _trim_history_by_value(history or [], _MAX_HISTORY_CHARS)
    if _trimmed:
        messages.extend(_trimmed)
    from datetime import date as _date
    _today = _date.today().strftime("%Y年%m月%d日")
    messages.append({"role": "user", "content": f"[今天日期：{_today}]\n{text}"})
    return messages


async def _call_with_ollama_cloud_fallback(
    _call: Any,
    provider_name: str,
    provider: dict,
    messages: List[dict],
    tools: list,
    routing_max_tokens: int,
    doctor_id: Optional[str],
) -> Any:
    """Call the primary provider; if Ollama fails, try the cloud fallback."""
    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    try:
        return await call_with_retry_and_fallback(
            _call,
            primary_model=provider["model"],
            fallback_model=fallback_model,
            max_attempts=int(os.environ.get("AGENT_LLM_ATTEMPTS", "3")),
            op_name="agent.chat_completion",
            circuit_key_suffix=doctor_id or "",
        )
    except Exception as _ollama_err:
        return await _try_cloud_fallback(
            provider_name, _ollama_err, messages, tools, routing_max_tokens, doctor_id
        )


async def _try_cloud_fallback(
    provider_name: str,
    original_err: Exception,
    messages: List[dict],
    tools: list,
    routing_max_tokens: int,
    doctor_id: Optional[str],
) -> Any:
    """Attempt a cloud provider fallback when Ollama fails entirely."""
    _cloud_fallback = os.environ.get("OLLAMA_CLOUD_FALLBACK", "").strip() if provider_name == "ollama" else ""
    if not _cloud_fallback:
        raise original_err
    # PHI egress gate: block cloud fallback unless explicitly allowed.
    from services.ai.egress_policy import check_cloud_egress
    check_cloud_egress(_cloud_fallback, "routing", original_error=original_err)
    log(f"[Agent:ollama] all retries failed ({original_err}); trying cloud fallback={_cloud_fallback}")
    _cloud_provider = _PROVIDERS.get(_cloud_fallback)
    if _cloud_provider is None:
        raise original_err
    _cloud_provider = dict(_cloud_provider)
    _cloud_client = _get_client(_cloud_fallback, _cloud_provider)

    async def _cloud_call(model_name: str):
        with trace_block("llm", "agent.chat_completion", {"provider": _cloud_fallback, "model": model_name}):
            return await _cloud_client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=routing_max_tokens,
                temperature=0,
            )

    _cloud_timeout = float(os.environ.get("AGENT_CLOUD_FALLBACK_TIMEOUT", "3.0"))
    try:
        return await asyncio.wait_for(
            call_with_retry_and_fallback(
                _cloud_call,
                primary_model=_cloud_provider["model"],
                max_attempts=2,
                op_name="agent.chat_completion.cloud_fallback",
                circuit_key_suffix=doctor_id or "",
            ),
            timeout=_cloud_timeout,
        )
    except asyncio.TimeoutError:
        log(f"[Agent] cloud fallback timed out after {_cloud_timeout}s")
        raise


def _handle_non_ollama_no_tool(
    provider_name: str,
    chat_reply: Optional[str],
) -> IntentResult:
    """For non-Ollama providers: try embedded tool extraction, else return chat reply."""
    embedded_fn, embedded_args = _extract_embedded_tool_call(chat_reply)
    if embedded_fn:
        log(f"[Agent:{provider_name}] embedded tool_call: {embedded_fn}({embedded_args})")
        cleaned_reply = None if _looks_like_tool_markup(chat_reply) else chat_reply
        return _intent_result_from_tool_call(embedded_fn, embedded_args, cleaned_reply)
    reply_text = chat_reply or "您好！有什么可以帮您？"
    log(f"[Agent:{provider_name}] no tool call → chat reply: {reply_text[:80]}")
    return IntentResult(intent=Intent.unknown, chat_reply=reply_text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def _build_system_prompt(specialty: Optional[str], doctor_name: Optional[str]) -> str:
    """Compose the final system prompt with optional specialty/doctor-name prefix."""
    system_prompt = await _get_routing_prompt()
    if specialty and specialty.strip():
        system_prompt = f"你是{specialty.strip()}科医生助手。\n" + system_prompt
    if doctor_name and doctor_name.strip():
        _dn = doctor_name.strip()
        system_prompt = f"当前医生姓名：{_dn}。在回复中可以称呼医生为「{_dn}医生」（例如：好的，{_dn}医生）。\n" + system_prompt
    return system_prompt


def _clamp_max_tokens() -> int:
    """Read ROUTING_MAX_TOKENS from env and clamp to [80, 1200]."""
    val = int(os.environ.get("ROUTING_MAX_TOKENS", "600"))
    return max(80, min(val, 1200))


async def _resolve_completion(
    text: str,
    provider_name: str,
    provider: dict,
    messages: List[dict],
    tools_for_call: list,
    routing_max_tokens: int,
    doctor_id: Optional[str],
    client: Any,
) -> Any:
    """Fire the LLM call (with retries/fallback); raise on unrecoverable error."""
    async def _call(model_name: str):
        with trace_block("llm", "agent.chat_completion", {"provider": provider_name, "model": model_name}):
            return await client.chat.completions.create(
                model=model_name,
                messages=messages,
                tools=tools_for_call,
                tool_choice="auto",
                max_tokens=routing_max_tokens,
                temperature=0,
            )
    return await _call_with_ollama_cloud_fallback(
        _call, provider_name, provider, messages, tools_for_call, routing_max_tokens, doctor_id
    )


async def _interpret_completion(
    completion: Any,
    text: str,
    provider_name: str,
    provider: dict,
    messages: List[dict],
    tools_for_call: list,
    routing_max_tokens: int,
    client: Any,
) -> IntentResult:
    """Extract an IntentResult from a completed LLM response."""
    message = completion.choices[0].message
    chat_reply = message.content or None

    if message.tool_calls:
        tool_call = message.tool_calls[0]
        fn_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
            if not isinstance(args, dict):
                args = {}
        except (json.JSONDecodeError, TypeError):
            args = {}
        log(f"[Agent:{provider_name}] tool_call: {fn_name}({args})")
        return _intent_result_from_tool_call(fn_name, args, chat_reply)

    if provider_name == "ollama":
        result = await _ollama_post_process(
            message=message, text=text, messages=messages, client=client,
            model_name=provider["model"], tools=tools_for_call,
            routing_max_tokens=routing_max_tokens,
        )
        if result is not None:
            return result
        # Ollama produced readable text but no tool call — treat same as
        # non-Ollama: return unknown with preserved chat reply (conservative).
        if chat_reply and not _looks_like_tool_markup(chat_reply):
            return IntentResult(intent=Intent.unknown, chat_reply=chat_reply)
        # No readable reply — fall through to keyword fallback.
        return _fallback_intent_from_text(text)

    return _handle_non_ollama_no_tool(provider_name, chat_reply)


async def dispatch(
    text: str,
    history: Optional[List[dict]] = None,
    knowledge_context: Optional[str] = None,
    specialty: Optional[str] = None,
    doctor_id: Optional[str] = None,
    doctor_name: Optional[str] = None,
    current_patient_context: Optional[str] = None,
    candidate_patient_context: Optional[str] = None,
    patient_not_found_context: Optional[str] = None,
) -> IntentResult:
    """Call LLM with function-calling tools and return an IntentResult.

    Args:
        text: The current user message.
        history: Optional prior turns as [{"role": "user"|"assistant", "content": "..."}].
    """
    provider_name = os.environ.get("ROUTING_LLM") or os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _resolve_provider(provider_name)
    _check_api_key(provider_name, provider)
    log(f"[Agent:{provider_name}] dispatching: {text[:80]}")

    system_prompt = await _build_system_prompt(specialty, doctor_name)
    messages = _build_messages(
        text, system_prompt, history, knowledge_context,
        current_patient_context, candidate_patient_context, patient_not_found_context,
    )
    client = _get_client(provider_name, provider)
    routing_max_tokens = _clamp_max_tokens()
    tools_for_call = _selected_tools()

    try:
        completion = await _resolve_completion(
            text, provider_name, provider, messages, tools_for_call, routing_max_tokens, doctor_id, client
        )
    except Exception as e:
        log(f"[Agent:{provider_name}] tool-call failed, using local fallback: {e}")
        from services.observability.routing_metrics import record as _record_metric
        _record_metric("fallback:regex")
        with trace_block("agent", "agent.local_fallback", {"reason": f"{provider_name}_error"}):
            return _fallback_intent_from_text(text)

    result = await _interpret_completion(
        completion, text, provider_name, provider, messages, tools_for_call, routing_max_tokens, client
    )

    # Post-LLM guardrail: if LLM returned unknown/garbled but text clearly
    # has create + clinical content, coerce to add_record so the planner can
    # handle compound patient-creation automatically.
    if result.intent == Intent.unknown:
        from services.ai.agent_fallback import _CREATE_SIGNALS, _has_clinical, _extract_name_gender_age
        name, gender, age = None, None, None
        try:
            name, gender, age = _extract_name_gender_age(text)
        except Exception:
            pass
        if (any(k in text for k in _CREATE_SIGNALS)
                and _has_clinical(text, name, gender, age)):
            log(f"[Agent:{provider_name}] post-LLM guardrail: create+clinical → add_record")
            result = IntentResult(
                intent=Intent.add_record,
                patient_name=name or result.patient_name,
                gender=gender or result.gender,
                age=age or result.age,
            )

    return result
