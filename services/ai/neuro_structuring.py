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
- 若原文提及进行了某项影像或化验检查但未给出具体结论，imaging/labs 数组必须为空列表，不得填入推测性结论

【输出格式】必须严格按照以下三个 Markdown 节输出，不得省略任何节标题：

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
    "text": "主诉文本，格式：症状+持续时间，20字以内；若原文无主诉，返回null",
    "duration": "时间描述或null"
  },
  "hpi": {
    "onset": "起病情况或null",
    "progression": "病情进展或null",
    "associated_symptoms": [],
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
    "primary": "主要诊断或null（只使用原文中的诊断，不得推断）",
    "secondary": [],
    "stroke_type": "ischemic/hemorrhagic/tia/unknown",
    "territory": "MCA/ACA/PCA/PICA/AICA/BA/watershed/其他或null",
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
  "vasospasm_status": "none|clinical|radiographic|severe 或 null（仅SAH亚型填写）",
  "nimodipine_regimen": "尼莫地平方案描述（途径/剂量/疗程）或 null（仅SAH亚型填写）",

  "hydrocephalus_status": "none|acute|chronic|shunt_dependent 或 null（仅ICH/SAH亚型填写）",

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
  "bypass_type": "direct_sta_mca|indirect_edas|combined|other 或 null（仅烟雾病亚型填写）",
  "perfusion_status": "normal|mildly_reduced|severely_reduced|improved 或 null（仅烟雾病亚型填写）",

  "surgery_type": null,
  "surgery_date": null,
  "surgery_status": "planned|done|cancelled|conservative 或 null",
  "surgical_approach": null,

  "mrs_score": null,
  "barthel_index": null
}
```

【字段说明】

imaging 数组中每个元素格式：
{"modality": "MRI/CT/CTA/MRA/DSA/TCD/颈动脉超声/其他", "datetime": null, "summary": "影像结论", "findings": [{"vessel": "血管名称", "lesion_type": "stenosis/occlusion/aneurysm/moyamoya/other", "severity_percent": null, "side": "left/right/bilateral", "collateral": null, "notes": null}]}

labs 数组中每个元素格式：
{"name": "检验项目名称", "datetime": null, "result": "结果值", "unit": "单位", "flag": "high/low/normal/unknown", "source_text": "原始文本片段"}

plan.orders 数组中每个元素格式：
{"type": "lab/imaging/medication/procedure/consult/followup/other", "name": "医嘱名称", "frequency": null, "notes": null}

【CVD字段约束】
- `hemorrhage_etiology`：仅当 `diagnosis_subtype` 为 `ICH` 时填写，其他亚型返回 null
- `hunt_hess_grade` / `wfns_grade` / `fisher_grade` / `modified_fisher_grade` / `vasospasm_status` / `nimodipine_regimen`：仅 SAH 亚型相关，其他亚型返回 null
- `hydrocephalus_status`：仅 ICH 或 SAH 亚型填写，缺血性亚型返回 null（除非原文明确提及梗阻性脑积水）
- `spetzler_martin_grade`：仅 AVM 亚型填写，其他亚型返回 null
- `suzuki_stage` / `bypass_type` / `perfusion_status`：仅烟雾病（moyamoya）亚型相关，其他亚型返回 null
- `phases_score`：仅未破裂动脉瘤填写（`diagnosis_subtype: aneurysm`），其他亚型返回 null
- `diagnosis.etiology_toast`（Structured_JSON节）：仅当 `diagnosis_subtype` 为 `ischemic` 时填写，出血性病变/AVM/烟雾病返回 null

【跨节一致性】CVD_Surgical_Context.diagnosis_subtype 须与 Structured_JSON.diagnosis.stroke_type 保持一致：
- diagnosis_subtype = "ischemic" → stroke_type = "ischemic"
- diagnosis_subtype = "ICH" 或 "SAH" → stroke_type = "hemorrhagic"
- diagnosis_subtype = "AVM" / "aneurysm" → stroke_type 根据实际是否破裂出血填写

【保留专业缩写】NIHSS、mRS、TOAST、tPA、rt-PA、TIA、DVT、AF、INR、APTT、CTA、MRA、DSA、TCD、ASPECTS、ICH、SAH、AVM、GCS、Hunt-Hess、Fisher、WFNS、Spetzler-Martin、PHASES、Raymond-Roy、Suzuki、DCI、EVD、CPP、EDAS、STA-MCA、DWI、FLAIR、SWI、GRE、PWI、CTP、ADC、EVT、mTICI、TICI、DNT、DPT、LKW、CEA、CAS、DAPT 等缩写不得翻译或展开。
"""

async def _get_system_prompt() -> str:
    from utils.prompt_loader import get_prompt
    return await get_prompt("structuring.neuro_cvd", _SEED_PROMPT)



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


_FAST_CVD_PROMPT = """\
从以下脑血管病专科记录中提取结构化字段。只输出合法JSON对象，不加markdown代码块，无额外文字。

【严禁虚构】所有字段只能使用原文中有明确对应文字的信息。
- 数值字段（GCS、Hunt-Hess、ICH评分等）必须有原文出现的具体数字，不得估算
- 枚举字段只能选择原文已描述的状态，不得根据诊断名推断
- 未提及的字段必须返回 null（JSON null，非字符串"null"），不得填写任何推断或默认值

输出格式（枚举选项用 | 分隔，最终值选其一或填 null）：
{
  "diagnosis_subtype": "ICH" | "SAH" | "ischemic" | "AVM" | "aneurysm" | "moyamoya" | "other" | null,
  "hemorrhage_location": null,
  "gcs_score": null,
  "hunt_hess_grade": null,
  "wfns_grade": null,
  "fisher_grade": null,
  "modified_fisher_grade": null,
  "ich_score": null,
  "ich_volume_ml": null,
  "hemorrhage_etiology": "hypertensive" | "caa" | "avm" | "coagulopathy" | "tumor" | "unknown" | null,
  "vasospasm_status": "none" | "clinical" | "radiographic" | "severe" | null,
  "hydrocephalus_status": "none" | "acute" | "chronic" | "shunt_dependent" | null,
  "aneurysm_location": null,
  "aneurysm_size_mm": null,
  "aneurysm_neck_width_mm": null,
  "aneurysm_treatment": "clipping" | "coiling" | "pipeline" | "conservative" | null,
  "suzuki_stage": null,
  "bypass_type": "direct_sta_mca" | "indirect_edas" | "combined" | "other" | null,
  "perfusion_status": "normal" | "mildly_reduced" | "severely_reduced" | "improved" | null,
  "surgery_status": "planned" | "done" | "cancelled" | "conservative" | null,
  "mrs_score": null
}

【约束】hunt_hess/wfns/fisher/modified_fisher/vasospasm_status 仅限SAH亚型；suzuki/bypass_type/perfusion_status 仅限moyamoya亚型；hemorrhage_etiology 仅限ICH亚型；非对应亚型的上述字段输出null。
"""


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
    fast_cvd_prompt = await get_prompt("structuring.fast_cvd", _FAST_CVD_PROMPT)

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
