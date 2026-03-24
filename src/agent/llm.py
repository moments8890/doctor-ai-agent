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

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from infra.llm.resilience import call_with_retry_and_fallback
from infra.observability.observability import trace_block
from utils.log import log

T = TypeVar("T", bound=BaseModel)

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
            base_client, mode=instructor.Mode.JSON
        )
    return _instructor_cache[cache_key]


def clean_llm_output(raw: str) -> str:
    """Strip <think> blocks and whitespace from LLM output."""
    if not raw:
        return raw
    return _THINK_RE.sub("", raw).strip()


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

    # Log full LLM input
    import json as _json
    log(f"[{op_name}] input: model={model} messages={_json.dumps(messages, ensure_ascii=False)[:2000]}")

    async def _call(model_name: str) -> T:
        instructor_client = _get_instructor_client(env_var)
        return await instructor_client.chat.completions.create(
            model=model_name,
            messages=messages,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=max_retries,
        )

    with trace_block("llm", op_name, {"model": model, "response_model": response_model.__name__}):
        result = await _call(model)

    # Log output
    log(f"[{op_name}] output: {result.model_dump_json()[:200]}")
    return result


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

    async def _call(model_name: str) -> str:
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
        raw = response.choices[0].message.content or ""
        return clean_llm_output(raw)

    with trace_block("llm", op_name, {"model": model, "env_var": env_var}):
        result = await call_with_retry_and_fallback(
            _call,
            primary_model=model,
            fallback_model=None,  # single provider for now
            max_attempts=2,
            backoff_seconds=(0.5,),
            op_name=op_name,
        )
    return result
