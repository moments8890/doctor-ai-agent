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
  主诉 / 现病史 / 既往史 / 个人史 / 家族史 /
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
# LLM prompt
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """\
你是门诊病历整理助手。根据下方病历记录，填写"卫医政发〔2010〕11号门诊病历"标准表格的各项字段。

【要求】
- 仅使用原文中明确出现的信息，不得推断或虚构。
- 若某字段在原文中未提及，将值设为空字符串 ""。
- 输出合法 JSON 对象，以下 12 个字段全部必须出现。
- 诊断字段须标注 ICD-10 编码（国卫办医政发〔2024〕16号规定）。

【字段说明与示例】
- encounter_type（就诊类型）：仅填 "初诊" 或 "复诊"，根据记录判断。首次就诊或无法判断时填 "初诊"。
  示例：{{"encounter_type": "初诊"}}
- department（科别）：就诊科室名称，如 "神经内科"、"心血管内科" 等。无法判断时填 ""。
  示例：{{"department": "神经内科"}}
- chief_complaint（主诉）：患者就诊的主要症状及持续时间，简明扼要。
  示例：{{"chief_complaint": "胸闷气促 3 天"}}
- present_illness（现病史）：主诉相关的详细病史，包括症状特点、演变及伴随症状。
  示例：{{"present_illness": "3 天前无诱因出现胸闷，活动后加重，伴轻度气促，无发热。"}}
- past_history（既往史）：既往重要病史、手术史、过敏史。复诊且原文未提及时可填 ""。
  示例：{{"past_history": "高血压病史 10 年，无药物过敏。"}}
- personal_history（个人史）：吸烟、饮酒、婚育、职业等。
  示例：{{"personal_history": "吸烟 20 年，已戒 5 年。"}}
- family_history（家族史）：直系亲属遗传性疾病史。
  示例：{{"family_history": "父亲患冠心病。"}}
- physical_exam（体格检查）：生命体征、心肺腹神经系统体格检查结果。
  示例：{{"physical_exam": "BP 145/90 mmHg，心率 88 次/分，律齐，双肺呼吸音清。"}}
- aux_exam（辅助检查）：化验、影像、心电图等结果。
  示例：{{"aux_exam": "BNP 980 pg/mL，心脏超声 EF 50%。"}}
- diagnosis（初步诊断）：主要诊断及次要诊断，须附 ICD-10 编码（国卫办医政发〔2024〕16号）。
  示例：{{"diagnosis": "1. 心力衰竭 I50.900\\n2. 高血压病 I10.x00"}}
- treatment（治疗方案）：用药、手术、操作等治疗措施。
  示例：{{"treatment": "氨氯地平 5 mg qd，呋塞米 20 mg qd，低钠低脂饮食。"}}
- followup（医嘱及随访）：出院医嘱、复诊时间、注意事项。
  示例：{{"followup": "1 个月后门诊随访，监测血压及 BNP。"}}

【病历记录】
{records_text}
"""

# ---------------------------------------------------------------------------
# LLM client singleton (reuse connection pool across requests)
# ---------------------------------------------------------------------------

_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}


def _get_llm_client() -> tuple[AsyncOpenAI, str]:
    """Return (client, model_name). Cached singleton, bypassed in pytest."""
    base_url = os.environ.get("STRUCTURING_LLM_BASE_URL") or os.environ.get(
        "OLLAMA_BASE_URL", "http://localhost:11434/v1"
    )
    api_key = os.environ.get("STRUCTURING_LLM_API_KEY", "nokeyneeded")
    model = os.environ.get("STRUCTURING_LLM_MODEL", "qwen2.5:14b")

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


async def extract_outpatient_fields(
    records: list,
    patient: Any = None,
    doctor_id: Optional[str] = None,
) -> dict[str, str]:
    """
    Use LLM to extract 10 standard outpatient fields from records.

    Returns dict keyed by field key (see OUTPATIENT_FIELDS).
    Raises ExtractionError if the LLM is completely unavailable so callers
    can surface a meaningful error instead of silently returning a blank form.
    """
    # Collect record text
    parts: list[str] = []
    for rec in records:
        content = (getattr(rec, "content", None) or "").strip()
        if content:
            parts.append(content)
    records_text = "\n---\n".join(parts) if parts else ""

    # Optionally append custom template text (first 500 chars only)
    template_text = await _get_custom_template(doctor_id)

    prompt = _EXTRACT_PROMPT.format(records_text=records_text)
    if template_text:
        prompt += f"\n\n【自定义模板参考格式（仅作参考，字段定义以上文为准）】\n{template_text[:500]}"

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
        # Normalise encounter_type to only accept 初诊/复诊
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
