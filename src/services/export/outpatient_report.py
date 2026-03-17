"""
卫医政发〔2010〕11号 门诊病历标准格式报告生成。

功能：
1. extract_outpatient_fields(records, patient, doctor_id) → dict[str, str]
   用 LLM 从病历记录中提取标准字段；
   若医生上传了自定义模板，将模板内容作为附加上下文传入 LLM。

2. generate_outpatient_report_pdf(fields, patient_name, patient_info, clinic_name, doctor_name) → bytes
   按表单样式渲染 PDF（标题行 + 患者信息行 + 各字段分节）。

字段列表（卫医政发〔2010〕11号 + 国卫办医政发〔2024〕16号）：
  就诊类型 / 科别 /
  主诉 / 现病史 / 既往史 / 过敏史 / 个人史 / 家族史 /
  体格检查 / 辅助检查 / 初步诊断（含ICD编码）/ 治疗方案 / 医嘱及随访
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from openai import AsyncOpenAI

from services.ai.llm_resilience import call_with_retry_and_fallback
from services.medical_record_schema import OUTPATIENT_FIELD_META, FIELD_KEYS, OutpatientRecord, PatientInfo
from utils.log import log

# ---------------------------------------------------------------------------
# Standard field definitions (imported from shared schema)
# ---------------------------------------------------------------------------

OUTPATIENT_FIELDS = OUTPATIENT_FIELD_META

# Fields rendered in the PDF header row rather than as full sections
_HEADER_ONLY_FIELDS = {"department"}

_FIELD_KEYS = FIELD_KEYS

# ---------------------------------------------------------------------------
# LLM client singleton (reuse connection pool across requests)
# ---------------------------------------------------------------------------

_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}


def _get_llm_client() -> tuple[AsyncOpenAI, str]:
    """Return (client, model_name) using the shared _PROVIDERS registry."""
    from services.ai.llm_client import _PROVIDERS

    provider_name = os.environ.get("STRUCTURING_LLM", "ollama")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        provider_name = "ollama"
        provider = _PROVIDERS["ollama"]

    base_url = provider["base_url"]
    api_key = os.environ.get(provider["api_key_env"], "nokeyneeded")
    model = provider.get("model", "qwen2.5:14b")

    # Bypass singleton in test env so mock patches work
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        return (
            AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=0),
            model,
        )

    cache_key = f"{base_url}:{model}"
    if cache_key not in _CLIENT_CACHE:
        _CLIENT_CACHE[cache_key] = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=60, max_retries=0
        )
    return _CLIENT_CACHE[cache_key], model


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


class ExtractionError(RuntimeError):
    """Raised when LLM is unavailable and no fields could be extracted."""


async def _build_extraction_prompt(
    records: list,
    doctor_id: Optional[str],
    patient: Any = None,
) -> str:
    """拼装门诊病历字段提取 prompt（含结构化元数据和自定义模板）。"""
    parts: list[str] = []
    for rec in records:
        lines: list[str] = []
        content = (getattr(rec, "content", None) or "").strip()
        tags = getattr(rec, "tags", None)
        if tags:
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = []
            if isinstance(tags, list) and tags:
                lines.append(f"[标签: {', '.join(tags)}]")
        if content:
            lines.append(content)
        if lines:
            parts.append("\n".join(lines))
    records_text = "\n---\n".join(parts) if parts else ""
    # Wrap record content in delimiters to isolate from prompt instructions
    if records_text:
        records_text = f"<record_content>\n{records_text}\n</record_content>"

    # Patient demographics hint
    patient_hint = ""
    if patient:
        hint_parts: list[str] = []
        name = getattr(patient, "name", None)
        if name:
            hint_parts.append(f"姓名: {name}")
        gender = getattr(patient, "gender", None)
        if gender:
            hint_parts.append(f"性别: {gender}")
        yob = getattr(patient, "year_of_birth", None)
        if yob:
            from datetime import date
            age = date.today().year - int(yob)
            hint_parts.append(f"年龄: {age}岁")
        if hint_parts:
            patient_hint = f"\n\n【患者信息】\n{', '.join(hint_parts)}"

    from utils.prompt_loader import get_prompt
    extract_prompt_template = await get_prompt("report-extract")
    prompt = extract_prompt_template.format(records_text=records_text)

    if patient_hint:
        prompt += patient_hint

    template_text = await _get_custom_template(doctor_id)
    if template_text:
        prompt += f"\n\n【自定义模板参考格式（仅作参考，字段定义以上文为准）】\n{template_text[:500]}"
    return prompt


def _merge_structured_fields(records: list) -> Optional[dict[str, str]]:
    """Merge stored structured data from multiple records; return None if any record lacks it."""
    # Cumulative fields: merge across all records
    _CUMULATIVE = {"past_history", "allergy_history", "family_history", "marital_reproductive", "personal_history"}

    parsed: list[dict] = []
    for rec in records:
        raw = getattr(rec, "structured", None)
        if not raw:
            return None  # at least one record has no structured data → fall back to LLM
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        if not isinstance(raw, dict) or not raw:
            return None
        parsed.append(raw)

    # Start with empty fields, apply in chronological order (oldest first)
    result: dict[str, str] = {k: "" for k in _FIELD_KEYS}
    cumulative: dict[str, list[str]] = {k: [] for k in _CUMULATIVE}

    for struct in parsed:
        for key in _FIELD_KEYS:
            val = str(struct.get(key, "") or "").strip()
            if not val:
                continue
            if key in _CUMULATIVE:
                if val not in cumulative[key]:  # deduplicate
                    cumulative[key].append(val)
            else:
                result[key] = val  # override: latest wins

    for key in _CUMULATIVE:
        if cumulative[key]:
            result[key] = "；".join(cumulative[key])

    return result


async def extract_outpatient_fields(
    records: list,
    patient: Any = None,
    doctor_id: Optional[str] = None,
) -> dict[str, str]:
    """提取门诊标准字段：优先使用已存储的 structured 数据，否则调用 LLM。"""
    # Fast path: merge stored structured data if all records have it
    merged = _merge_structured_fields(records)
    if merged is not None:
        log(f"[outpatient-report] using stored structured data ({len(records)} records)")
        return merged

    prompt = await _build_extraction_prompt(records, doctor_id, patient=patient)
    client, model = _get_llm_client()
    _provider = os.environ.get("STRUCTURING_LLM", "ollama")
    _tag = f"[outpatient-report:{_provider}:{model}]"
    fallback_model = os.environ.get("STRUCTURING_LLM_FALLBACK_MODEL", "")

    async def _call(model_name: str):
        return await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000,
        )

    try:
        log(f"{_tag} request: len={len(prompt)}")
        resp = await call_with_retry_and_fallback(
            _call,
            primary_model=model,
            fallback_model=fallback_model or None,
            max_attempts=2,
            op_name="outpatient_report.extract_fields",
        )
        raw = resp.choices[0].message.content or "{}"
        log(f"{_tag} response: {raw[:200]}")
        data = json.loads(raw)
        result = {k: str(data.get(k, "") or "") for k in _FIELD_KEYS}
        return result
    except Exception as exc:
        log(f"{_tag} extraction failed doctor={doctor_id}: {exc}")
        raise ExtractionError(f"LLM field extraction failed: {exc}") from exc


async def export_as_json(
    records: list,
    patient: Any = None,
    doctor_id: Optional[str] = None,
) -> dict:
    """Extract fields and return as OutpatientRecord dict."""
    fields = await extract_outpatient_fields(records, patient, doctor_id)
    patient_info = PatientInfo()
    if patient:
        patient_info.name = getattr(patient, "name", None)
        patient_info.gender = getattr(patient, "gender", None)
        yob = getattr(patient, "year_of_birth", None)
        if yob:
            from datetime import date
            patient_info.age = date.today().year - int(yob)
    record = OutpatientRecord(patient=patient_info, **fields)
    return record.model_dump()


async def _get_custom_template(doctor_id: Optional[str]) -> str:
    """
    Load custom template stored in system_prompts with key report.template.{doctor_id}.
    Returns empty string if not found or on error.
    """
    if not doctor_id:
        return ""
    try:
        from db.engine import AsyncSessionLocal
        from db.crud import get_system_prompt
        async with AsyncSessionLocal() as db:
            row = await get_system_prompt(db, f"report.template.{doctor_id}")
            if row and row.content:
                return row.content
    except Exception as exc:
        log(f"[OutpatientReport] template load failed: {exc}")
    return ""
