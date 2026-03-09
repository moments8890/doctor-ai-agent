"""
神经专科病例结构化提取：将口述或文本转为 NeuroCaseDB 所需的结构化 JSON。
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional, Tuple

from openai import AsyncOpenAI

from db.models.neuro_case import ExtractionLog, NeuroCase, NeuroCVDSurgicalContext
from services.ai.llm_client import _PROVIDERS
from services.ai.llm_resilience import call_with_retry_and_fallback
from utils.log import log

# Module-level singleton cache: one HTTP connection pool per provider.
_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}

# ---------------------------------------------------------------------------
# Seed prompt — written to DB on first startup. After that, DB is the source of truth.
# To reset: delete the 'structuring.neuro_cvd' row in /admin → System Prompts.
# ---------------------------------------------------------------------------
_SEED_PROMPT = """\
你是神经/脑血管疾病专科电子病历结构化系统。将医生口述或书面记录转为规范化的脑血管病病历结构化JSON。
输入内容来自神经内科、神经外科或卒中单元，可能含有专业缩写、影像报告、实验室结果等。

【严禁虚构】所有字段只能使用医生原话中明确出现的信息。
- 严禁补充未提及的数值（NIHSS、血压、血糖等）
- 严禁推断未提及的治疗方案或检查安排
- 若某字段在原话中无对应信息，必须返回 null 或空列表，不得填写任何内容

【输出格式】必须严格按照以下两个 Markdown 节输出，不得省略任何节标题：

## Structured_JSON

```json
{
  "case_id": "可选的病例编号或null",
  "patient_profile": {
    "name": "姓名或null",
    "gender": "male/female/unknown",
    "age": 年龄数字或null,
    "id_number": null
  },
  "encounter": {
    "type": "inpatient/outpatient/emergency/unknown",
    "admission_date": "YYYY-MM-DD或null",
    "discharge_date": null,
    "ward": null,
    "attending": null
  },
  "chief_complaint": {
    "text": "主诉文本，格式：症状+持续时间，20字以内",
    "duration": "时间描述或null"
  },
  "hpi": {
    "onset": "起病情况",
    "progression": "病情进展",
    "associated_symptoms": ["伴随症状列表"],
    "prior_treatment": null
  },
  "past_history": {
    "stroke_tia": null,
    "cardiac": null,
    "other": null,
    "medications": null,
    "allergies": null,
    "surgeries": null
  },
  "risk_factors": {
    "hypertension": {
      "has_htn": "yes/no/unknown",
      "years": null,
      "control_status": "controlled/uncontrolled/unknown"
    },
    "diabetes": "yes/no/unknown",
    "hyperlipidemia": "yes/no/unknown",
    "smoking": "yes/no/unknown",
    "drinking": "yes/no/unknown",
    "family_history_cvd": "yes/no/unknown"
  },
  "physical_exam": {
    "bp_systolic": null,
    "bp_diastolic": null,
    "heart_rate": null,
    "temperature": null,
    "gcs": null,
    "other": null
  },
  "neuro_exam": {
    "nihss_total": null,
    "consciousness": null,
    "speech": null,
    "motor_left": null,
    "motor_right": null,
    "facial_palsy": null,
    "ataxia": null,
    "sensory": null,
    "neglect": null,
    "visual": null,
    "other": null
  },
  "imaging": [],
  "labs": [],
  "diagnosis": {
    "primary": "主要诊断",
    "secondary": [],
    "stroke_type": "ischemic/hemorrhagic/tia/unknown",
    "territory": null,
    "etiology_toast": null
  },
  "plan": {
    "orders": [],
    "thrombolysis": null,
    "thrombectomy": null,
    "antiplatelet": null,
    "anticoagulation": null,
    "bp_target": null,
    "notes": null
  },
  "provenance": {
    "source": "dictation/text/ocr/unknown",
    "recorded_at": null
  }
}
```

## Extraction_Log

```json
{
  "missing_fields": ["未能提取的字段列表"],
  "ambiguities": ["有歧义的内容描述"],
  "normalization_notes": ["规范化说明"],
  "confidence_by_module": {
    "patient_profile": 0.0,
    "neuro_exam": 0.0,
    "imaging": 0.0,
    "labs": 0.0,
    "diagnosis": 0.0
  }
}
```

【字段说明】

imaging 数组中每个元素格式：
{"modality": "MRI/CT/CTA/MRA/DSA/TCD/颈动脉超声/其他", "datetime": null, "summary": "影像结论", "findings": [{"vessel": "血管名称", "lesion_type": "stenosis/occlusion/aneurysm/moyamoya/other", "severity_percent": null, "side": "left/right/bilateral", "collateral": null, "notes": null}]}

labs 数组中每个元素格式：
{"name": "检验项目名称", "datetime": null, "result": "结果值", "unit": "单位", "flag": "high/low/normal/unknown", "source_text": "原始文本片段"}

plan.orders 数组中每个元素格式：
{"type": "lab/imaging/medication/procedure/consult/followup/other", "name": "医嘱名称", "frequency": null, "notes": null}

## CVD_Surgical_Context

```json
{
  "diagnosis_subtype": "ICH|SAH|ischemic|AVM|aneurysm|moyamoya|other 或 null",
  "hemorrhage_location": "解剖部位（基底节/小脑/脑干/蛛网膜下腔等）或 null",

  "ich_score": null,
  "ich_volume_ml": null,
  "hemorrhage_etiology": "hypertensive|caa|avm|coagulopathy|tumor|unknown 或 null（仅ICH亚型填写）",

  "hunt_hess_grade": null,
  "fisher_grade": null,
  "wfns_grade": null,
  "modified_fisher_grade": null,
  "vasospasm_status": "none|clinical|radiographic|severe 或 null（SAH术后监测状态）",
  "nimodipine_regimen": "尼莫地平方案描述（途径/剂量/疗程）或 null",

  "hydrocephalus_status": "none|acute|chronic|shunt_dependent 或 null（ICH/SAH共用）",

  "spetzler_martin_grade": null,
  "gcs_score": null,

  "aneurysm_location": null,
  "aneurysm_size_mm": null,
  "aneurysm_neck_width_mm": null,
  "aneurysm_morphology": "saccular|fusiform|other 或 null",
  "aneurysm_daughter_sac": "yes|no 或 null",
  "aneurysm_treatment": "clipping|coiling|pipeline|conservative 或 null",
  "phases_score": null,

  "suzuki_stage": null,
  "bypass_type": "direct_sta_mca|indirect_edas|combined|other 或 null（烟雾病/复杂动脉瘤）",
  "perfusion_status": "normal|mildly_reduced|severely_reduced|improved 或 null（烟雾病灌注状态）",

  "surgery_type": null,
  "surgery_date": null,
  "surgery_status": "planned|done|cancelled|conservative 或 null",
  "surgical_approach": null,

  "mrs_score": null,
  "barthel_index": null
}
```

【CVD字段约束】
- `hemorrhage_etiology`：仅当 `diagnosis_subtype` 为 `ICH` 时填写，其他亚型返回 null
- `hunt_hess_grade` / `wfns_grade` / `fisher_grade` / `modified_fisher_grade`：仅 SAH 亚型相关
- `suzuki_stage` / `bypass_type` / `perfusion_status`：仅烟雾病（moyamoya）亚型相关
- `phases_score`：仅未破裂动脉瘤填写（`diagnosis_subtype: aneurysm`）
- `diagnosis.etiology_toast`（Structured_JSON节）：仅当 `diagnosis_subtype` 为 `ischemic` 时填写，出血性病变/AVM/烟雾病返回 null

【保留专业缩写】NIHSS、mRS、TOAST、tPA、rt-PA、TIA、DVT、AF、INR、APTT、CTA、MRA、DSA、TCD、ASPECT、ICH、SAH、AVM、GCS、Hunt-Hess、Fisher、WFNS、Spetzler-Martin、PHASES、Raymond-Roy、Suzuki、DCI、EVD、CPP、EDAS、STA-MCA 等缩写不得翻译或展开。
"""

_PROMPT_CACHE: Optional[Tuple[float, str]] = None
_PROMPT_CACHE_TTL = 60  # seconds


async def _get_system_prompt() -> str:
    global _PROMPT_CACHE
    if _PROMPT_CACHE and time.time() - _PROMPT_CACHE[0] < _PROMPT_CACHE_TTL:
        return _PROMPT_CACHE[1]
    try:
        from db.crud import get_system_prompt
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            row = await get_system_prompt(db, "structuring.neuro_cvd")
        content = row.content if row else _SEED_PROMPT
    except Exception as exc:
        log("[NeuroLLM] load prompt from DB failed, falling back to seed prompt: {0}".format(exc))
        content = _SEED_PROMPT
    _PROMPT_CACHE = (time.time(), content)
    return content



_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_fenced_json(text: str) -> Optional[str]:
    """Return the content of the first ```json ... ``` block, or None."""
    m = _FENCED_JSON_RE.search(text)
    return m.group(1).strip() if m else None


def _parse_markdown_output(md: str) -> Tuple[NeuroCase, ExtractionLog, Optional[NeuroCVDSurgicalContext]]:
    """Parse the three-section Markdown response from the LLM.

    Sections expected:
      ## Structured_JSON       ```json ... ```
      ## Extraction_Log        ```json ... ```
      ## CVD_Surgical_Context  ```json ... ```

    Fallback: if no ## sections found, treat entire response as NeuroCase JSON.
    """
    case_json_str: Optional[str] = None
    log_json_str: Optional[str] = None
    cvd_json_str: Optional[str] = None

    if "## Structured_JSON" in md or "## Extraction_Log" in md:
        parts = re.split(r"^##\s+", md, flags=re.MULTILINE)
        for part in parts:
            title, _, body = part.partition("\n")
            title = title.strip()
            if title == "Structured_JSON":
                case_json_str = _extract_fenced_json(body)
                if case_json_str is None:
                    case_json_str = body.strip()
            elif title == "Extraction_Log":
                log_json_str = _extract_fenced_json(body)
                if log_json_str is None:
                    log_json_str = body.strip()
            elif title == "CVD_Surgical_Context":
                cvd_json_str = _extract_fenced_json(body)
                if cvd_json_str is None:
                    cvd_json_str = body.strip()

    if case_json_str is None:
        raw = _extract_fenced_json(md) or md.strip()
        case_json_str = raw

    # Parse NeuroCase
    try:
        case_data = json.loads(case_json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"NeuroCase JSON parse error: {exc}") from exc

    neuro_case = NeuroCase.model_validate(case_data)

    # Parse ExtractionLog (optional)
    extraction_log = ExtractionLog()
    if log_json_str:
        try:
            extraction_log = ExtractionLog.model_validate(json.loads(log_json_str))
        except (json.JSONDecodeError, Exception):
            pass

    # Parse NeuroCVDSurgicalContext (optional)
    cvd_context: Optional[NeuroCVDSurgicalContext] = None
    if cvd_json_str:
        try:
            cvd_data = json.loads(cvd_json_str)
            cvd_context = NeuroCVDSurgicalContext.model_validate(cvd_data)
            if not cvd_context.has_data():
                cvd_context = None
        except (json.JSONDecodeError, Exception):
            pass

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


_FAST_CVD_PROMPT = """\
从以下神经外科脑血管病记录中提取结构化字段。只输出合法JSON对象，无额外文字。
所有字段只能使用原文中明确出现的信息，未提及的字段返回null。

输出格式：
{
  "diagnosis_subtype": "ICH|SAH|ischemic|AVM|aneurysm|moyamoya|other|null",
  "gcs_score": null,
  "hunt_hess_grade": null,
  "wfns_grade": null,
  "fisher_grade": null,
  "modified_fisher_grade": null,
  "ich_score": null,
  "hemorrhage_etiology": "hypertensive|caa|avm|coagulopathy|tumor|unknown|null（仅ICH）",
  "vasospasm_status": "none|clinical|radiographic|severe|null",
  "hydrocephalus_status": "none|acute|chronic|shunt_dependent|null",
  "aneurysm_location": null,
  "aneurysm_size_mm": null,
  "aneurysm_neck_width_mm": null,
  "phases_score": null,
  "suzuki_stage": null,
  "bypass_type": "direct_sta_mca|indirect_edas|combined|other|null",
  "perfusion_status": "normal|mildly_reduced|severely_reduced|improved|null",
  "surgery_status": "planned|done|cancelled|conservative|null",
  "mrs_score": null
}
"""


async def extract_fast_cvd_context(text: str) -> Optional[NeuroCVDSurgicalContext]:
    """Fast CVD-only extraction (~400 tokens max). Use for short dictations with explicit scores.

    Returns None if extraction fails or no CVD data found.
    """
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = dict(_PROVIDERS[provider_name])
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])

    if provider_name not in _CLIENT_CACHE or os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        _CLIENT_CACHE[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("NEURO_LLM_TIMEOUT", "60")),
            max_retries=0,
        )
    client = _CLIENT_CACHE[provider_name]

    async def _call(model_name: str):
        return await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": _FAST_CVD_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=400,
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
        return ctx if ctx.has_data() else None
    except Exception as exc:
        log(f"[FastCVD] extraction failed (non-fatal): {exc}")
        return None
