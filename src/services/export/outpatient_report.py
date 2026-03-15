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
from utils.log import log

# ---------------------------------------------------------------------------
# Standard field definitions
# ---------------------------------------------------------------------------

OUTPATIENT_FIELDS = [
    ("encounter_type",     "就诊类型"),   # 初诊 / 复诊
    ("department",         "科别"),        # 卫医政发〔2010〕11号 required header field
    ("chief_complaint",    "主诉"),
    ("present_illness",    "现病史"),
    ("past_history",       "既往史"),
    ("allergy_history",    "过敏史"),
    ("personal_history",   "个人史"),
    ("family_history",     "家族史"),
    ("physical_exam",      "体格检查"),
    ("aux_exam",           "辅助检查"),
    ("diagnosis",          "初步诊断"),   # 国卫办医政发〔2024〕16号: ICD编码 required
    ("treatment",          "治疗方案"),
    ("followup",           "医嘱及随访"),
]

# Fields rendered in the PDF header row rather than as full sections
_HEADER_ONLY_FIELDS = {"encounter_type", "department"}

_FIELD_KEYS = [k for k, _ in OUTPATIENT_FIELDS]

# ---------------------------------------------------------------------------
# LLM client singleton (reuse connection pool across requests)
# ---------------------------------------------------------------------------

_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}


def _get_llm_client() -> tuple[AsyncOpenAI, str]:
    """Return (client, model_name). Cached singleton, bypassed in pytest."""
    base_url = (
        os.environ.get("STRUCTURING_LLM_BASE_URL")
        or os.environ.get("OLLAMA_BASE_URL")
        or "http://192.168.0.123:11434/v1"
    )
    api_key = os.environ.get("STRUCTURING_LLM_API_KEY") or os.environ.get("OLLAMA_API_KEY", "ollama")
    model = os.environ.get("STRUCTURING_LLM_MODEL") or os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

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
        enc = getattr(rec, "encounter_type", None)
        if enc:
            _enc_label = {"first_visit": "初诊", "follow_up": "复诊"}.get(enc, enc)
            lines.append(f"[就诊类型: {_enc_label}]")
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


async def extract_outpatient_fields(
    records: list,
    patient: Any = None,
    doctor_id: Optional[str] = None,
) -> dict[str, str]:
    """调用 LLM 从病历记录中提取门诊标准字段；LLM 不可用时抛出 ExtractionError。"""
    prompt = await _build_extraction_prompt(records, doctor_id, patient=patient)
    client, model = _get_llm_client()
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
        resp = await call_with_retry_and_fallback(
            _call,
            primary_model=model,
            fallback_model=fallback_model or None,
            max_attempts=2,
            op_name="outpatient_report.extract_fields",
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        result = {k: str(data.get(k, "") or "") for k in _FIELD_KEYS}
        if result.get("encounter_type") not in ("初诊", "复诊"):
            result["encounter_type"] = "初诊"
        log(
            f"[OutpatientReport] extraction ok doctor={doctor_id} "
            f"non_empty={sum(1 for v in result.values() if v)}/{len(_FIELD_KEYS)}"
        )
        return result
    except Exception as exc:
        log(f"[OutpatientReport] field extraction failed doctor={doctor_id}: {exc}")
        raise ExtractionError(f"LLM field extraction failed: {exc}") from exc


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
