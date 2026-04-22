"""Shared LLM call helper for the Plan-and-Act pipeline.

Consolidates provider resolution, client caching, retry/resilience,
tracing, and Qwen3 thinking-mode workarounds.

Two call modes:
- llm_call()        → returns raw text (for compose/summary responses)
- structured_call() → returns a validated Pydantic model via instructor
                      (uses tool-calling protocol for reliable structured output)
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from infra.llm.resilience import call_with_retry_and_fallback
from infra.observability.observability import trace_block
from utils.log import log

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# LLM call logger — append-only JSONL with correlation fields
# ---------------------------------------------------------------------------

import json as _json
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parents[2]
_LLM_LOG_FILE = _REPO_ROOT / "logs" / "llm_calls.jsonl"
_LLM_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_LLM_LOG_BACKUP_COUNT = 5


def _rotate_if_needed(path: _Path) -> None:
    """Rotate log file by size or date. Keeps up to _LLM_LOG_BACKUP_COUNT backups."""
    if not path.exists():
        return
    # Check date — rotate if file is from a different day
    from datetime import date as _date
    file_date = _dt.fromtimestamp(path.stat().st_mtime, tz=_tz.utc).date()
    needs_rotate = path.stat().st_size >= _LLM_LOG_MAX_BYTES or file_date < _dt.now(_tz.utc).date()
    if not needs_rotate:
        return
    # Shift existing backups: .4 → .5, .3 → .4, etc.
    for i in range(_LLM_LOG_BACKUP_COUNT, 0, -1):
        src = path.with_suffix(f".jsonl.{i}") if i < _LLM_LOG_BACKUP_COUNT else None
        dst = path.with_suffix(f".jsonl.{i}")
        src = path.with_suffix(f".jsonl.{i - 1}") if i > 1 else path
        if src.exists():
            dst = path.with_suffix(f".jsonl.{i}")
            src.rename(dst)
    # Delete oldest if over limit
    oldest = path.with_suffix(f".jsonl.{_LLM_LOG_BACKUP_COUNT + 1}")
    if oldest.exists():
        oldest.unlink()


def _log_llm_call(
    op_name: str, model: str, messages: list, output: Any = None, *,
    usage: Any = None, error: Any = None, raw_messages: list | None = None,
    duration_ms: int | None = None,
) -> None:
    """Log LLM call to an append-only JSONL file.

    Logs both successful and failed calls for debug visibility.
    - Append file: logs/llm_calls.jsonl (one JSON line per call, auto-rotated by size/date)
    """
    try:
        now = _dt.now(_tz.utc)

        # Prompt version hash — correlate output quality with prompt changes
        import hashlib as _hashlib
        system_content = next((m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "system"), "")
        prompt_hash = _hashlib.md5(system_content.encode()).hexdigest()[:8]

        # Build entry
        entry: Dict[str, Any] = {
            "timestamp": now.isoformat(),
            "op": op_name,
            "model": model,
            "prompt_hash": prompt_hash,
            "status": "error" if error else "ok",
            "input": {"messages": messages},
        }
        if raw_messages:
            entry["raw_messages"] = raw_messages
        if output is not None:
            if isinstance(output, BaseModel):
                entry["output"] = output.model_dump()
            elif isinstance(output, str):
                entry["output"] = {"text": output}
            else:
                entry["output"] = output
        if error is not None:
            entry["error"] = str(error)

        # Correlation: trace_id from HTTP middleware (observability ContextVar)
        from infra.observability.observability import get_current_trace_id
        # doctor_id / intent / request_id from log ContextVars.
        # request_id is bound by RequestContextMiddleware on every HTTP
        # request — joins this JSONL record to access logs and Sentry
        # Issues tagged with the same id.
        from utils.log import _ctx_doctor_id, _ctx_intent, _ctx_layers, _ctx_request_id
        entry["trace_id"] = get_current_trace_id() or ""
        entry["doctor_id"] = _ctx_doctor_id.get("")
        entry["intent"] = _ctx_intent.get("")
        entry["request_id"] = _ctx_request_id.get("")
        layers = _ctx_layers.get("")
        if layers:
            entry["layers"] = layers

        # Pre-call token estimate (Chinese ≈ 1 token per 1.5 chars)
        total_chars = sum(len(m.get("content", "")) for m in messages if isinstance(m, dict))
        entry["estimated_input_tokens"] = int(total_chars / 1.5)

        # Token usage from LLM response
        if usage is not None:
            entry["tokens"] = {
                "prompt": getattr(usage, "prompt_tokens", 0),
                "completion": getattr(usage, "completion_tokens", 0),
                "total": getattr(usage, "total_tokens", 0),
            }

        if duration_ms is not None:
            entry["duration_ms"] = duration_ms

        # Append to rotated JSONL file
        _LLM_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(_LLM_LOG_FILE)
        with open(_LLM_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, ensure_ascii=False) + "\n")

        # Also emit a compact Sentry Logs event so LLM calls land in the
        # GlitchTip Logs tab alongside HTTP events with the same
        # request_id. Only fires when _experiments.enable_logs=True on
        # sentry_sdk.init. Wrapped defensively — logger is still an
        # experimental API and may rename between sentry-sdk versions.
        try:
            from sentry_sdk import logger as _sentry_log
            tokens = entry.get("tokens") or {}
            _sentry_log.info(
                "llm.call",
                op=op_name,
                model=model,
                status=entry["status"],
                duration_ms=duration_ms or 0,
                tokens_in=int(tokens.get("prompt", 0)),
                tokens_out=int(tokens.get("completion", 0)),
                tokens_total=int(tokens.get("total", 0)),
                request_id=entry.get("request_id", ""),
                doctor_id=entry.get("doctor_id", ""),
                trace_id=entry.get("trace_id", ""),
                intent=entry.get("intent", ""),
            )
        except Exception:
            pass  # observability must not break the LLM call path

    except Exception:
        pass  # never break the LLM call path

_client_cache: dict[str, AsyncOpenAI] = {}
_instructor_cache: dict[str, Any] = {}
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _get_provider(env_var: str = "ROUTING_LLM", default: str = "groq"):
    """Return (provider_name, provider_config) for the given env var."""
    from infra.llm.client import _get_providers
    provider_name = os.environ.get(env_var, default)
    providers = _get_providers()
    provider = providers.get(provider_name, providers.get("groq"))
    return provider_name, provider


def _get_client(env_var: str = "ROUTING_LLM", default: str = "groq") -> AsyncOpenAI:
    """Get or create a cached AsyncOpenAI client."""
    provider_name, provider = _get_provider(env_var, default)
    if provider_name not in _client_cache:
        _client_cache[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider.get("api_key_env", ""), "nokeyneeded"),
            timeout=float(os.environ.get("LLM_TIMEOUT", "30")),
            max_retries=0,
            http_client=httpx.AsyncClient(trust_env=False),
        )
    return _client_cache[provider_name]


def _get_model(env_var: str = "ROUTING_LLM", default: str = "groq") -> str:
    """Return the model name for the given provider env var."""
    _, provider = _get_provider(env_var, default)
    return provider.get("model", "deepseek-chat")


def _extra_body(model: str) -> Optional[Dict[str, Any]]:
    """Build extra_body for provider-specific workarounds.

    NOTE: chat_template_kwargs was used to disable Qwen3 thinking mode,
    but Groq now rejects it. Disabled until we confirm which providers
    still need it.
    """
    return None


def _get_instructor_client(env_var: str = "ROUTING_LLM", default: str = "groq"):
    """Get or create a cached instructor-wrapped AsyncOpenAI client.

    Uses JSON mode (not tool-calling) because Groq/Qwen3 rejects
    tool calls even when the model produces valid JSON output.
    JSON mode tells instructor to use response_format instead of tools.
    """
    provider_name, _ = _get_provider(env_var, default)
    cache_key = f"instructor:{provider_name}"
    if cache_key not in _instructor_cache:
        base_client = _get_client(env_var, default)
        _instructor_cache[cache_key] = instructor.from_openai(
            base_client, mode=instructor.Mode.MD_JSON
        )
    return _instructor_cache[cache_key]


def clean_llm_output(raw: str) -> str:
    """Strip <think> blocks and whitespace from LLM output."""
    if not raw:
        return raw
    return _THINK_RE.sub("", raw).strip()


def _compute_raw_messages(messages: list, response_model: type) -> list | None:
    """Compute the actual messages instructor sends to the API (for debug logging).

    Instructor modifies messages in MD_JSON mode:
    - Appends JSON schema to system message
    - Appends "Return the correct JSON response..." as final user message
    """
    try:
        import copy
        from instructor.processing.response import handle_json_modes
        kwargs = {"messages": copy.deepcopy(messages)}
        _, modified = handle_json_modes(response_model, kwargs, instructor.Mode.MD_JSON)
        return modified.get("messages")
    except Exception:
        return None


async def structured_call(
    *,
    response_model: Type[T],
    messages: List[Dict[str, str]],
    op_name: str = "structured_call",
    env_var: str = "ROUTING_LLM",
    temperature: float = 0.1,
    max_tokens: int = 512,
    max_retries: int = 2,
) -> T:
    """Make an LLM call that returns a validated Pydantic model.

    Uses Instructor (tool-calling protocol) for reliable structured output.
    Instructor handles retries and validation internally.
    """
    model = _get_model(env_var)

    log(f"[{op_name}] input: model={model} msgs={len(messages)}")

    _last_usage = None
    raw_messages = _compute_raw_messages(messages, response_model)

    async def _call(model_name: str) -> T:
        nonlocal _last_usage
        instructor_client = _get_instructor_client(env_var)
        result = await instructor_client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )
        # instructor attaches _raw_response on the Pydantic model
        raw_resp = getattr(result, "_raw_response", None)
        if raw_resp:
            _last_usage = getattr(raw_resp, "usage", None)
        return result

    import time as _time
    _t0 = _time.monotonic()
    try:
        with trace_block("llm", op_name, {"model": model, "response_model": response_model.__name__}):
            result = await _call(model)

        _dur = int((_time.monotonic() - _t0) * 1000)
        log(f"[{op_name}] output: {result.model_dump_json()[:200]}")
        _log_llm_call(op_name, model, messages, result, usage=_last_usage, raw_messages=raw_messages, duration_ms=_dur)
        return result
    except Exception as exc:
        _dur = int((_time.monotonic() - _t0) * 1000)
        _log_llm_call(op_name, model, messages, error=exc, raw_messages=raw_messages, duration_ms=_dur)
        raise


async def llm_call(
    *,
    messages: List[Dict[str, str]],
    op_name: str = "llm_call",
    env_var: str = "ROUTING_LLM",
    temperature: float = 0.3,
    max_tokens: int = 800,
    json_mode: bool = False,
) -> str:
    """Make an LLM call with retry, circuit breaker, and tracing.

    Returns the raw response content (cleaned of <think> tags).
    Raises on failure after all retries are exhausted.
    """
    model = _get_model(env_var)

    _last_usage = None

    async def _call(model_name: str) -> str:
        nonlocal _last_usage
        client = _get_client(env_var)
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        extra = _extra_body(model_name)
        if extra:
            kwargs["extra_body"] = extra

        response = await client.chat.completions.create(**kwargs)
        _last_usage = getattr(response, "usage", None)
        raw = response.choices[0].message.content or ""
        return clean_llm_output(raw)

    import time as _time
    _t0 = _time.monotonic()
    try:
        with trace_block("llm", op_name, {"model": model, "env_var": env_var}):
            result = await call_with_retry_and_fallback(
                _call,
                primary_model=model,
                fallback_model=None,  # single provider for now
                max_attempts=2,
                backoff_seconds=(0.5,),
                op_name=op_name,
            )
        _dur = int((_time.monotonic() - _t0) * 1000)
        _log_llm_call(op_name, model, messages, result, usage=_last_usage, raw_messages=messages, duration_ms=_dur)
        return result
    except Exception as exc:
        _dur = int((_time.monotonic() - _t0) * 1000)
        _log_llm_call(op_name, model, messages, error=exc, raw_messages=messages, duration_ms=_dur)
        raise
