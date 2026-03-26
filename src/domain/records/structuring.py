"""
将医生口述或文字转换为结构化病历，使用 doctor-extract.md 提取字段，
再由 generate_content() 生成可读文本。
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from db.models.medical_record import MedicalRecord
from domain.patients.interview_summary import (
    DoctorExtractResult,
    generate_content,
    extract_tags,
)
from infra.llm.client import _PROVIDERS
from utils.log import log


_NO_CLINICAL_CONTENT = "__NO_CLINICAL_CONTENT__"


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


def _load_extract_prompt() -> str:
    """Load doctor-extract prompt template."""
    from utils.prompt_loader import get_prompt_sync
    return get_prompt_sync("intent/doctor-extract")


async def _extract_fields(
    text: str,
    env_var: str = "STRUCTURING_LLM",
) -> DoctorExtractResult:
    """Extract 14 clinical fields from raw text using doctor-extract.md."""
    from agent.llm import structured_call

    template = _load_extract_prompt()
    # Manual substitution — .format() breaks on JSON braces in prompt examples
    prompt = (
        template
        .replace("{name}", "未知")
        .replace("{gender}", "未知")
        .replace("{age}", "未知")
        .replace("{transcript}", text)
    )

    from utils.prompt_loader import get_prompt_sync
    base_prompt = get_prompt_sync("common/base", fallback="")

    messages = []
    if base_prompt:
        messages.append({"role": "system", "content": base_prompt})
    messages.append({"role": "user", "content": prompt})

    return await structured_call(
        response_model=DoctorExtractResult,
        messages=messages,
        op_name="structuring",
        env_var=env_var,
        temperature=0,
        max_tokens=2500,
    )


async def _try_cloud_fallback(
    original_err: Exception,
    provider_name: str,
    text: str,
) -> DoctorExtractResult:
    """Attempt cloud fallback when primary (usually ollama) fails entirely."""
    _cloud_fallback = (
        os.environ.get("OLLAMA_CLOUD_FALLBACK", "").strip() if provider_name == "ollama" else ""
    )
    if not _cloud_fallback:
        raise original_err
    from infra.llm.egress import check_cloud_egress
    check_cloud_egress(_cloud_fallback, "structuring", original_error=original_err)
    log(f"[structuring:ollama] all retries failed ({original_err}); trying cloud fallback={_cloud_fallback}")
    _cloud_provider = _PROVIDERS.get(_cloud_fallback)
    if _cloud_provider is None:
        raise original_err

    _cloud_timeout = float(os.environ.get("STRUCTURING_CLOUD_FALLBACK_TIMEOUT", "3.0"))
    old_val = os.environ.get("_STRUCTURING_CLOUD_FALLBACK", "")
    os.environ["_STRUCTURING_CLOUD_FALLBACK"] = _cloud_fallback
    try:
        return await asyncio.wait_for(
            _extract_fields(text, env_var="_STRUCTURING_CLOUD_FALLBACK"),
            timeout=_cloud_timeout,
        )
    finally:
        if old_val:
            os.environ["_STRUCTURING_CLOUD_FALLBACK"] = old_val
        else:
            os.environ.pop("_STRUCTURING_CLOUD_FALLBACK", None)


async def extract_fields_from_text(text: str) -> dict:
    """Extract 14 clinical fields from raw text. Returns dict of field→value."""
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _resolve_provider(provider_name)
    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[structuring:{provider_name}:{model_name}]"
    log(f"{_tag} request: {text[:80]}")

    if not os.environ.get("STRUCTURING_LLM"):
        os.environ["STRUCTURING_LLM"] = provider_name

    try:
        result = await _extract_fields(text, env_var="STRUCTURING_LLM")
    except Exception as primary_err:
        result = await _try_cloud_fallback(primary_err, provider_name, text)

    collected = {
        k: v.strip()
        for k, v in result.model_dump().items()
        if isinstance(v, str) and v.strip()
    }

    log(f"{_tag} extracted {len(collected)} fields: {list(collected.keys())}")
    return collected


async def text_to_interview(
    text: str,
    doctor_id: str,
    patient_id: Optional[int] = None,
) -> dict:
    """Extract fields from text → create interview session for doctor review.

    Returns dict with session_id and pre-populated fields.
    """
    fields = await extract_fields_from_text(text)

    from domain.patients.interview_session import create_session

    session = await create_session(
        doctor_id=doctor_id,
        patient_id=patient_id,
        mode="doctor",
        initial_fields=fields,
    )

    log(f"[structuring] session={session.id} pre-populated={len(fields)} fields")

    return {
        "session_id": session.id,
        "mode": "doctor",
        "source": "text_import",
        "pre_populated": fields,
    }


async def structure_medical_record(
    text: str,
    doctor_id: Optional[str] = None,
) -> MedicalRecord:
    """将文本转换为结构化 MedicalRecord (legacy — direct save without review)."""
    collected = await extract_fields_from_text(text)

    content = generate_content(collected)
    if not content:
        content = _NO_CLINICAL_CONTENT

    tags = extract_tags(collected)

    return MedicalRecord(
        content=content,
        structured=collected if collected else None,
        tags=tags,
        record_type="visit",
    )
