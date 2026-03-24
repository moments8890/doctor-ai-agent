"""
将医生口述或文字转换为结构化病历 JSON，支持多轮提示和系统提示覆盖。
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from db.models.medical_record import MedicalRecord
from infra.llm.client import _PROVIDERS  # shared provider registry
from infra.llm.resilience import call_with_retry_and_fallback
from infra.observability.observability import trace_block
from utils.log import log


class StructuringLLMResponse(BaseModel):
    """Response model for the structuring LLM call.

    Mirrors MedicalRecord but with relaxed validation so that
    structured_call can parse the LLM output; post-processing
    coerces fields to the stricter MedicalRecord schema.
    """

    content: str = Field(default="", description="LLM-organised clinical note")
    structured: Optional[Dict[str, str]] = Field(
        default=None, description="SOAP fields dict"
    )
    tags: List[str] = Field(default_factory=list, description="Keyword tags")
    record_type: str = Field(default="visit", description="Record type")


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
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
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


async def _get_system_prompt() -> str:
    """Load structuring prompt from DB, appending optional extension if set."""
    from utils.prompt_loader import get_prompt
    base = await get_prompt("structuring")
    extension = await get_prompt("structuring.extension", "")
    if extension.strip():
        return base + "\n\n" + extension.strip()
    return base


async def _build_system_prompt() -> str:
    """Load structuring system prompt."""
    with trace_block("llm", "structuring.load_prompt"):
        return await _get_system_prompt()


async def _structured_call_for_structuring(
    system_prompt: str,
    user_content: str,
    env_var: str = "STRUCTURING_LLM",
) -> StructuringLLMResponse:
    """Call the LLM via shared structured_call helper."""
    from agent.llm import structured_call

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    return await structured_call(
        response_model=StructuringLLMResponse,
        messages=messages,
        op_name="structuring",
        env_var=env_var,
        temperature=0,
        max_tokens=2500,
    )


async def _try_cloud_fallback(
    original_err: Exception,
    provider_name: str,
    system_prompt: str,
    user_content: str,
) -> StructuringLLMResponse:
    """Attempt cloud fallback when primary (usually ollama) fails entirely."""
    _cloud_fallback = (
        os.environ.get("OLLAMA_CLOUD_FALLBACK", "").strip() if provider_name == "ollama" else ""
    )
    if not _cloud_fallback:
        raise original_err
    # PHI egress gate: block cloud fallback unless explicitly allowed.
    from infra.llm.egress import check_cloud_egress
    check_cloud_egress(_cloud_fallback, "structuring", original_error=original_err)
    log(f"[structuring:ollama] all retries failed ({original_err}); trying cloud fallback={_cloud_fallback}")
    _cloud_provider = _PROVIDERS.get(_cloud_fallback)
    if _cloud_provider is None:
        raise original_err

    # Set the cloud provider as a temporary env override for structured_call
    _cloud_timeout = float(os.environ.get("STRUCTURING_CLOUD_FALLBACK_TIMEOUT", "3.0"))
    try:
        # Use the cloud provider name directly as the env var value won't work;
        # set a temporary env var for the call.
        old_val = os.environ.get("_STRUCTURING_CLOUD_FALLBACK", "")
        os.environ["_STRUCTURING_CLOUD_FALLBACK"] = _cloud_fallback
        try:
            return await asyncio.wait_for(
                _structured_call_for_structuring(
                    system_prompt, user_content,
                    env_var="_STRUCTURING_CLOUD_FALLBACK",
                ),
                timeout=_cloud_timeout,
            )
        finally:
            if old_val:
                os.environ["_STRUCTURING_CLOUD_FALLBACK"] = old_val
            else:
                os.environ.pop("_STRUCTURING_CLOUD_FALLBACK", None)
    except asyncio.TimeoutError:
        log("[structuring] cloud fallback timed out")
        raise


_NO_CLINICAL_CONTENT = "__NO_CLINICAL_CONTENT__"


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
        log(f"[structuring:{provider_name}] content was empty, returning sentinel")
    return data


def _validate_structured(structured: object) -> object:
    """Validate and clean the structured dict; return None if invalid."""
    if not isinstance(structured, dict):
        return None
    # Keep only recognized outpatient field keys
    _VALID_KEYS = {
        "visit_type", "chief_complaint", "present_illness", "past_history",
        "allergy_history", "personal_history", "marital_reproductive",
        "family_history", "physical_exam", "specialist_exam",
        "auxiliary_exam", "diagnosis", "treatment_plan", "orders_followup",
    }
    cleaned = {k: str(v) for k, v in structured.items() if k in _VALID_KEYS and v}
    return cleaned if cleaned else None


def _validate_and_coerce_fields(data: dict, text: str, provider_name: str) -> dict:
    """Validate required fields and coerce types to match MedicalRecord schema."""
    if isinstance(data, list):
        data = data[0] if data else {}

    if not isinstance(data, dict) or "content" not in data:
        log("[structuring] WARNING: LLM response missing 'content' field")
        if not isinstance(data, dict):
            data = {}
        data.setdefault("content", _NO_CLINICAL_CONTENT)

    data.pop("specialty_scores", None)

    data = _coerce_content(data, text, provider_name)

    # Validate structured field
    data["structured"] = _validate_structured(data.get("structured"))

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
    doctor_id: Optional[str] = None,
) -> MedicalRecord:
    """将文本转换为结构化 MedicalRecord。"""
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _resolve_provider(provider_name)
    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[structuring:{provider_name}:{model_name}]"
    log(f"{_tag} request: {text[:80]}")

    # Ensure STRUCTURING_LLM is set for structured_call provider resolution
    # (original default is "deepseek", but structured_call defaults to "groq")
    if not os.environ.get("STRUCTURING_LLM"):
        os.environ["STRUCTURING_LLM"] = provider_name

    system_prompt = await _build_system_prompt()

    # Use structured_call (instructor) for reliable structured output.
    # Falls back to cloud provider if primary (ollama) fails.
    try:
        result = await _structured_call_for_structuring(
            system_prompt, text, env_var="STRUCTURING_LLM",
        )
    except Exception as primary_err:
        result = await _try_cloud_fallback(
            primary_err, provider_name, system_prompt, text,
        )

    # Convert instructor result to dict for existing validation/coercion pipeline
    data = result.model_dump()
    log(f"{_tag} response: {data}")

    data = _validate_and_coerce_fields(data, text, provider_name)

    return MedicalRecord.model_validate(data)
