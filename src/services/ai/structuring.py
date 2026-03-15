"""
将医生口述或文字转换为结构化病历 JSON，支持多轮提示和系统提示覆盖。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Optional, Tuple

from openai import AsyncOpenAI

from db.models.medical_record import MedicalRecord
from services.ai.llm_client import _PROVIDERS  # shared provider registry
from services.ai.llm_resilience import call_with_retry_and_fallback
from services.observability.observability import trace_block
from utils.log import log

# Module-level singleton cache: one HTTP connection pool per provider.
_STRUCTURING_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}


def _get_structuring_client(provider_name: str, provider: dict) -> AsyncOpenAI:
    extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
    # Skip singleton cache in test environments so mock patches can intercept.
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        return AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("STRUCTURING_LLM_TIMEOUT", "30")),
            max_retries=0,
            default_headers=extra_headers,
        )
    if provider_name not in _STRUCTURING_CLIENT_CACHE:
        _STRUCTURING_CLIENT_CACHE[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("STRUCTURING_LLM_TIMEOUT", "30")),
            max_retries=0,
            default_headers=extra_headers,
        )
    return _STRUCTURING_CLIENT_CACHE[provider_name]

_FOLLOWUP_KEYWORDS = frozenset({
    "复诊", "随访", "复查", "上次", "那次", "上回", "继续上次",
    "之前开的药", "药吃完", "回来复查", "按时随访",
})

async def _get_system_prompt() -> str:
    """Load structuring prompt from DB, appending optional extension if set."""
    from utils.prompt_loader import get_prompt
    base = await get_prompt("structuring")
    extension = await get_prompt("structuring.extension", "")
    if extension.strip():
        return base + "\n\n" + extension.strip()
    return base


def detect_followup_from_text(text: str) -> bool:
    """Return True if the text suggests a follow-up/return visit."""
    return any(kw in text for kw in _FOLLOWUP_KEYWORDS)


def _resolve_provider(provider_name: str) -> dict:
    """Resolve and configure provider dict; raise RuntimeError if invalid."""
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise RuntimeError(
            "Unsupported STRUCTURING_LLM provider: {0} (allowed: {1})".format(provider_name, allowed)
        )
    provider = dict(provider)
    if provider_name == "ollama":
        provider["model"] = (
            os.environ.get("OLLAMA_STRUCTURING_MODEL")
            or os.environ.get("OLLAMA_MODEL", provider["model"])
        )
    elif provider_name == "openai":
        provider["base_url"] = os.environ.get("OPENAI_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("OPENAI_MODEL", provider["model"])
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
    elif provider_name == "claude":
        provider["model"] = os.environ.get("CLAUDE_MODEL", provider["model"])
    strict_mode = os.environ.get("LLM_PROVIDER_STRICT_MODE", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if strict_mode and provider_name != "ollama":
        key_env = provider["api_key_env"]
        if not os.environ.get(key_env, "").strip():
            raise RuntimeError(
                "Selected provider '{0}' requires {1}, but it is empty; strict mode blocks fallback".format(
                    provider_name, key_env,
                )
            )
    return provider


async def _build_system_prompt(
    consultation_mode: bool,
    encounter_type: str,
) -> str:
    """Assemble system prompt with optional consultation/followup suffixes."""
    from utils.prompt_loader import get_prompt
    with trace_block("llm", "structuring.load_prompt"):
        system_prompt = await _get_system_prompt()
    if consultation_mode:
        system_prompt = system_prompt + await get_prompt(
            "structuring-consultation-suffix"
        )
    if encounter_type == "follow_up":
        system_prompt = system_prompt + await get_prompt(
            "structuring-followup-suffix"
        )
    return system_prompt


def _make_llm_caller(client: AsyncOpenAI, provider_name: str, system_prompt: str, user_content: str):
    """Return an async callable suitable for call_with_retry_and_fallback."""
    async def _call(model_name: str):
        with trace_block("llm", "structuring.chat_completion", {"provider": provider_name, "model": model_name}):
            return await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=1500,
                temperature=0,
            )
    return _call


async def _call_with_cloud_fallback(
    primary_call,
    provider: dict,
    provider_name: str,
    system_prompt: str,
    user_content: str,
    doctor_id: Optional[str],
) -> object:
    """Call LLM with retry; on failure attempt cloud fallback if configured."""
    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    try:
        return await call_with_retry_and_fallback(
            primary_call,
            primary_model=provider["model"],
            fallback_model=fallback_model,
            max_attempts=int(os.environ.get("STRUCTURING_LLM_ATTEMPTS", "3")),
            op_name="structuring.chat_completion",
            circuit_key_suffix=doctor_id or "",
        )
    except Exception as _ollama_err:
        return await _try_cloud_fallback(
            _ollama_err, provider_name, system_prompt, user_content
        )


async def _try_cloud_fallback(
    original_err: Exception,
    provider_name: str,
    system_prompt: str,
    user_content: str,
) -> object:
    """Attempt cloud fallback when primary (usually ollama) fails entirely."""
    _cloud_fallback = (
        os.environ.get("OLLAMA_CLOUD_FALLBACK", "").strip() if provider_name == "ollama" else ""
    )
    if not _cloud_fallback:
        raise original_err
    # PHI egress gate: block cloud fallback unless explicitly allowed.
    from services.ai.egress_policy import check_cloud_egress
    check_cloud_egress(_cloud_fallback, "structuring", original_error=original_err)
    log(f"[LLM:ollama] all retries failed ({original_err}); trying cloud fallback={_cloud_fallback}")
    _cloud_provider = _PROVIDERS.get(_cloud_fallback)
    if _cloud_provider is None:
        raise original_err
    _cloud_provider = dict(_cloud_provider)
    _cloud_client = _get_structuring_client(_cloud_fallback, _cloud_provider)
    _cloud_call = _make_llm_caller(_cloud_client, _cloud_fallback, system_prompt, user_content)
    _cloud_timeout = float(os.environ.get("STRUCTURING_CLOUD_FALLBACK_TIMEOUT", "3.0"))
    try:
        return await asyncio.wait_for(
            call_with_retry_and_fallback(
                _cloud_call,
                primary_model=_cloud_provider["model"],
                max_attempts=2,
                op_name="structuring.chat_completion.cloud_fallback",
            ),
            timeout=_cloud_timeout,
        )
    except asyncio.TimeoutError:
        log(f"[Structuring] cloud fallback timed out")
        raise


_NO_CLINICAL_CONTENT = "__NO_CLINICAL_CONTENT__"


def _parse_llm_response(raw: str, text: str, provider_name: str) -> dict:
    """Parse JSON from LLM response; sentinel on parse error."""
    with trace_block("llm", "structuring.parse_response"):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as _e:
            log(f"[LLM:{provider_name}] JSON parse FAILED ({_e}); returning sentinel")
            data = {"content": _NO_CLINICAL_CONTENT, "tags": []}
    return data


def _coerce_content(data: dict, text: str, provider_name: str) -> dict:
    """将 content 字段强制转换为字符串，空值时从原始文本派生。"""
    content_val = data.get("content")
    if content_val is None or not isinstance(content_val, str):
        if isinstance(content_val, list):
            data["content"] = "；".join(str(x) for x in content_val if x)
        elif isinstance(content_val, dict):
            data["content"] = "；".join(f"{k}：{v}" for k, v in content_val.items())
        elif content_val is not None:
            data["content"] = str(content_val)
    if not (data.get("content") or "").strip():
        data["content"] = _NO_CLINICAL_CONTENT
        log(f"[LLM:{provider_name}] content was empty, returning sentinel")
    return data


def _validate_and_coerce_fields(data: dict, text: str, provider_name: str) -> dict:
    """Validate required fields and coerce types to match MedicalRecord schema."""
    if isinstance(data, list):
        data = data[0] if data else {}

    _required_fields = {"content", "tags"}
    _missing = _required_fields - set(data.keys() if isinstance(data, dict) else [])
    if _missing:
        log(f"[Structuring] WARNING: LLM response missing fields {_missing}")
        if "content" not in data:
            data["content"] = _NO_CLINICAL_CONTENT
        if "tags" not in data:
            data["tags"] = []

    data.pop("specialty_scores", None)

    data = _coerce_content(data, text, provider_name)

    tags_val = data.get("tags")
    if not isinstance(tags_val, list):
        data["tags"] = []
    else:
        data["tags"] = [str(t) for t in tags_val if t]

    rt = data.get("record_type")
    if not isinstance(rt, str) or not rt.strip():
        data["record_type"] = "visit"

    return data


async def structure_medical_record(
    text: str,
    consultation_mode: bool = False,
    encounter_type: str = "unknown",
    prior_visit_summary: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> MedicalRecord:
    """将文本转换为结构化 MedicalRecord，支持问诊/复诊模式和多提供商 LLM。"""
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _resolve_provider(provider_name)
    log(f"[LLM:{provider_name}] calling API: {text[:80]}")

    client = _get_structuring_client(provider_name, provider)
    system_prompt = await _build_system_prompt(consultation_mode, encounter_type)

    user_content = text
    if prior_visit_summary:
        user_content = f"【上次就诊参考】\n{prior_visit_summary}\n\n【本次记录】\n{text}"

    primary_call = _make_llm_caller(client, provider_name, system_prompt, user_content)
    completion = await _call_with_cloud_fallback(
        primary_call, provider, provider_name, system_prompt, user_content, doctor_id
    )

    raw = completion.choices[0].message.content or ""
    log(f"[LLM:{provider_name}] response: {raw}")

    data = _parse_llm_response(raw, text, provider_name)
    data = _validate_and_coerce_fields(data, text, provider_name)

    return MedicalRecord.model_validate(data)
