"""
神经专科病例结构化提取：将口述或文本转为 NeuroCaseDB 所需的结构化 JSON。
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional, Tuple

from openai import AsyncOpenAI

from db.models.neuro_case import ExtractionLog, NeuroCase, NeuroCVDSurgicalContext
from services.ai.llm_client import _PROVIDERS
from services.ai.llm_resilience import call_with_retry_and_fallback
from utils.log import log

# Module-level singleton cache: one HTTP connection pool per provider.
_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}

async def _get_system_prompt() -> str:
    from utils.prompt_loader import get_prompt
    return await get_prompt("neuro-cvd")



_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_fenced_json(text: str) -> Optional[str]:
    """Return the content of the first ```json ... ``` block, or None."""
    m = _FENCED_JSON_RE.search(text)
    return m.group(1).strip() if m else None


def _clamp_numeric_cvd_scores(ctx: NeuroCVDSurgicalContext) -> NeuroCVDSurgicalContext:
    """Clear out-of-range numeric CVD scores and return updated context."""
    _ranges = [
        ("gcs_score", 3, 15),
        ("hunt_hess_grade", 1, 5),
        ("wfns_grade", 1, 5),
        ("fisher_grade", 1, 4),
        ("modified_fisher_grade", 0, 4),
        ("ich_score", 0, 6),
        ("mrs_score", 0, 6),
        ("suzuki_stage", 1, 6),
        ("spetzler_martin_grade", 1, 5),
    ]
    for field, lo, hi in _ranges:
        val = getattr(ctx, field, None)
        if val is not None and not (lo <= val <= hi):
            log(f"[CVD] {field}={val} out of range [{lo},{hi}]; clearing")
            ctx = ctx.model_copy(update={field: None})
    return ctx


def _enforce_cvd_cross_field_rules(ctx: NeuroCVDSurgicalContext) -> NeuroCVDSurgicalContext:
    """Clear subtype-specific fields when diagnosis_subtype does not match."""
    subtype = ctx.diagnosis_subtype
    if not subtype:
        return ctx
    # SAH-only scores
    if subtype != "SAH":
        if ctx.hunt_hess_grade is not None:
            log(f"[CVD] hunt_hess_grade set for non-SAH subtype={subtype}; clearing")
            ctx = ctx.model_copy(update={"hunt_hess_grade": None})
        if ctx.wfns_grade is not None:
            log(f"[CVD] wfns_grade set for non-SAH subtype={subtype}; clearing")
            ctx = ctx.model_copy(update={"wfns_grade": None})
    # Moyamoya-only scores
    if subtype != "moyamoya" and ctx.suzuki_stage is not None:
        ctx = ctx.model_copy(update={"suzuki_stage": None})
    # AVM-only scores
    if subtype != "AVM" and ctx.spetzler_martin_grade is not None:
        ctx = ctx.model_copy(update={"spetzler_martin_grade": None})
    return ctx


def _validate_cvd_constraints(ctx: NeuroCVDSurgicalContext) -> NeuroCVDSurgicalContext:
    """Enforce clinical range constraints and cross-field consistency rules."""
    ctx = _clamp_numeric_cvd_scores(ctx)
    ctx = _enforce_cvd_cross_field_rules(ctx)
    return ctx


def _split_markdown_sections(md: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Split a three-section LLM Markdown response into (case_json, log_json, cvd_json) strings."""
    case_json_str: Optional[str] = None
    log_json_str: Optional[str] = None
    cvd_json_str: Optional[str] = None
    if "## Structured_JSON" in md or "## Extraction_Log" in md:
        parts = re.split(r"^##\s+", md, flags=re.MULTILINE)
        for part in parts:
            title, _, body = part.partition("\n")
            title = title.strip()
            if title == "Structured_JSON":
                case_json_str = _extract_fenced_json(body) or body.strip()
            elif title == "Extraction_Log":
                log_json_str = _extract_fenced_json(body) or body.strip()
            elif title == "CVD_Surgical_Context":
                cvd_json_str = _extract_fenced_json(body) or body.strip()
    if case_json_str is None:
        case_json_str = _extract_fenced_json(md) or md.strip()
    return case_json_str, log_json_str, cvd_json_str


def _parse_cvd_context(cvd_json_str: str) -> Optional[NeuroCVDSurgicalContext]:
    """Parse and validate a CVD surgical context JSON string; returns None on any failure."""
    try:
        cvd_data = json.loads(cvd_json_str)
        cvd_context = NeuroCVDSurgicalContext.model_validate(cvd_data)
        cvd_context = _validate_cvd_constraints(cvd_context)
        return cvd_context if cvd_context.has_data() else None
    except (json.JSONDecodeError, Exception):
        return None


def _parse_markdown_output(md: str) -> Tuple[NeuroCase, ExtractionLog, Optional[NeuroCVDSurgicalContext]]:
    """Parse the three-section Markdown response from the LLM.

    Sections expected:
      ## Structured_JSON       ```json ... ```
      ## Extraction_Log        ```json ... ```
      ## CVD_Surgical_Context  ```json ... ```

    Fallback: if no ## sections found, treat entire response as NeuroCase JSON.
    """
    case_json_str, log_json_str, cvd_json_str = _split_markdown_sections(md)

    try:
        case_data = json.loads(case_json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"NeuroCase JSON parse error: {exc}") from exc
    neuro_case = NeuroCase.model_validate(case_data)

    extraction_log = ExtractionLog()
    if log_json_str:
        try:
            extraction_log = ExtractionLog.model_validate(json.loads(log_json_str))
        except (json.JSONDecodeError, Exception):
            pass

    cvd_context: Optional[NeuroCVDSurgicalContext] = None
    if cvd_json_str:
        cvd_context = _parse_cvd_context(cvd_json_str)

    return neuro_case, extraction_log, cvd_context


async def extract_neuro_case(text: str) -> Tuple[NeuroCase, ExtractionLog, Optional[NeuroCVDSurgicalContext]]:
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = dict(_PROVIDERS[provider_name])
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
    log(f"[NeuroLLM:{provider_name}] calling API: {text[:80]}")

    if provider_name not in _CLIENT_CACHE or os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        _CLIENT_CACHE[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("NEURO_LLM_TIMEOUT", "60")),
            max_retries=0,
        )
    client = _CLIENT_CACHE[provider_name]
    system_prompt = await _get_system_prompt()
    async def _call(model_name: str):
        return await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=3000,
            temperature=0,
        )

    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    completion = await call_with_retry_and_fallback(
        _call,
        primary_model=provider["model"],
        fallback_model=fallback_model,
        max_attempts=int(os.environ.get("NEURO_LLM_ATTEMPTS", "3")),
        op_name="neuro.chat_completion",
    )
    raw_md = completion.choices[0].message.content
    log(f"[NeuroLLM:{provider_name}] response length={len(raw_md)}")
    return _parse_markdown_output(raw_md)


def _resolve_neuro_provider(provider_name: str) -> tuple[dict, AsyncOpenAI]:
    """解析提供商配置并返回 (provider_dict, client)，使用模块级客户端缓存。"""
    provider = dict(_PROVIDERS[provider_name])
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
    is_test = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", "")
    if provider_name not in _CLIENT_CACHE or is_test:
        _CLIENT_CACHE[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("NEURO_LLM_TIMEOUT", "60")),
            max_retries=0,
        )
    return provider, _CLIENT_CACHE[provider_name]


async def extract_fast_cvd_context(text: str) -> Optional[NeuroCVDSurgicalContext]:
    """Fast CVD-only extraction (~400 tokens max). Use for short dictations with explicit scores.

    Returns None if extraction fails or no CVD data found.
    """
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider, client = _resolve_neuro_provider(provider_name)

    from utils.prompt_loader import get_prompt
    fast_cvd_prompt = await get_prompt("neuro-fast-cvd")

    async def _call(model_name: str):
        return await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": fast_cvd_prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=600,
            temperature=0,
        )

    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    try:
        completion = await call_with_retry_and_fallback(
            _call,
            primary_model=provider["model"],
            fallback_model=fallback_model,
            max_attempts=2,
            op_name="neuro.fast_cvd",
        )
        raw = completion.choices[0].message.content or ""
        json_str = _extract_fenced_json(raw) or raw.strip()
        data = json.loads(json_str)
        ctx = NeuroCVDSurgicalContext.model_validate(data)
        ctx = _validate_cvd_constraints(ctx)
        return ctx if ctx.has_data() else None
    except Exception as exc:
        log(f"[FastCVD] extraction failed (non-fatal): {exc}")
        return None
