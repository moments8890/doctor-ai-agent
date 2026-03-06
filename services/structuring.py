from __future__ import annotations

import json
import os
import re
import time
from typing import Optional, Tuple
from openai import AsyncOpenAI
from models.medical_record import MedicalRecord
from services.llm_resilience import call_with_retry_and_fallback
from services.observability import trace_block
from utils.log import log

# Seed value — written to DB on first startup. After that, DB is the source of truth.
# To reset to defaults: delete the 'structuring' row in /admin → System Prompts.
_SEED_PROMPT = """\
你是医院电子病历系统，依据《病历书写基本规范》（卫医政发〔2010〕11号）将医生口述或文字记录转为规范化门诊病历 JSON。
输入可能来自心血管内科或肿瘤科，含有专业术语、缩写和口语化表达，请准确识别并规范化。
输入若以引号或"记录一下"开头，忽略引导语，直接提取临床内容。

【严禁虚构】所有字段只能使用医生原话中明确出现的信息。
- 严禁补充未提及的数值（血压、心率、BNP、EF等）
- 严禁推断未提及的治疗方案或检查安排
- 严禁将口语化表达扩写为未提及的临床细节
- 若某字段在原话中无对应信息，必须返回 null，不得填写任何内容

【字段说明与书写要求】

必填字段（绝对不可为 null，哪怕描述极简也必须生成合理值）：

  chief_complaint（主诉）
    · 简明描述患者就诊最主要的症状或体征及持续时间，一般不超过 20 字
    · 例如："劳力性胸闷一周"、"突发胸痛 2 小时"、"化疗后乏力"
    · 术后复诊格式："XX术后N个月复诊"
    · 若描述极简，直接将核心问题作为主诉

  history_of_present_illness（现病史）
    · 按时间顺序描述本次疾病的发生、发展、诊疗经过
    · 包括：起病时间与诱因、主症性质/程度/部位/演变、伴随症状、已有诊疗经过
    · 纳入重要的化验趋势（如"CEA 从 12 降至 5"、"BNP 从 600 升至 980"、"EF 从 60% 降至 50%"）
    · 用药依从性问题须记录（如"昨日漏服利伐沙班一次"）

尽量填写（有依据时填写，无法确定时返回 null）：

  diagnosis（诊断）
    · 按规范书写疾病诊断名称，优先使用 ICD 标准名称
    · 多个诊断以"；"分隔，主要诊断列首位
    · 鉴别诊断/待排写作"待排：XX"；高度怀疑但未确定写"考虑：XX"
    · 急危重症须体现（如"急性 STEMI；血流动力学不稳定"）

  treatment_plan（治疗方案）
    · 包括药物（药名、剂量、用法）、非药物治疗、医嘱
    · 本次安排的检查/手术也放此处（如"安排心电图、TnI、BNP；急诊 PCI 绿色通道"）
    · 专科：化疗方案调整、靶向药、G-CSF、介入手术等

选填字段（文本中无相关信息时返回 null）：

  past_medical_history（既往史）
    · 既往重要疾病史、手术史（PCI、消融、肿瘤手术等）、药物及食物过敏史

  physical_examination（体格检查）
    · 生命体征（BP、HR、体重等）及阳性体征
    · 含血流动力学描述（如"BP 90/60 mmHg，大汗"）

  auxiliary_examinations（辅助检查）
    · 本次就诊时已有的实验室、影像、心电图等结果（含趋势）
    · 示例："ECG：前壁 ST 段抬高；BNP 980 pg/mL（上次 600）；EF 50%（上次 60%，趋势下降）"
    · 肿瘤标志物："CEA 5 ng/mL（上次 12，下降）；ANC 1.1×10⁹/L"

  follow_up_plan（随访计划）
    · 复诊时间、随访内容、患者教育要点、院外监测指标

【输出要求】
- 只输出合法 JSON 对象，不加任何解释或 markdown
- 字段值为字符串或 null，不使用数组或嵌套对象
- 保持医学术语规范，保留专业缩写（STEMI、PCI、BNP、EF、ANC、EGFR 等）
"""

_CONSULTATION_SUFFIX = """

【问诊对话模式】
输入为医生与患者的问诊对话转写文本，非单人口述。

提取规则：
- 患者描述的症状、时间、诱因 → history_of_present_illness
- 医生确认的既往史 → past_medical_history
- 医生检查的生命体征 → physical_examination
- 医生提及的检查结果 → auxiliary_examinations
- 医生的诊断倾向 → diagnosis
- 医生交代的用药/治疗 → treatment_plan
- 医生的随访安排 → follow_up_plan
- chief_complaint: 患者首诉主要不适（≤20字）

严禁将医生的询问性语言作为已确认信息。疑问句内容须有患者明确应答才能记录。
"""

_PROMPT_CACHE: Optional[Tuple[float, str]] = None  # (fetched_at, content)
_PROMPT_CACHE_TTL = 60  # seconds — changes take effect within 1 minute


async def _get_system_prompt() -> str:
    """Load structuring prompt from DB with optional extension.

    Combines two DB keys:
      'structuring'           — base prompt (seeded from _SEED_PROMPT on first start)
      'structuring.extension' — optional doctor-defined additions appended to the base

    Falls back to _SEED_PROMPT only if the DB has no base row at all.
    Cache TTL: 60 seconds — changes take effect within 1 minute.
    """
    global _PROMPT_CACHE
    if _PROMPT_CACHE and time.time() - _PROMPT_CACHE[0] < _PROMPT_CACHE_TTL:
        return _PROMPT_CACHE[1]
    try:
        from db.crud import get_system_prompt
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            base_row = await get_system_prompt(db, "structuring")
            ext_row = await get_system_prompt(db, "structuring.extension")
        base = base_row.content if base_row else _SEED_PROMPT
        extension = ext_row.content.strip() if ext_row and ext_row.content.strip() else None
        content = base + "\n\n" + extension if extension else base
    except Exception:
        content = _SEED_PROMPT
    _PROMPT_CACHE = (time.time(), content)
    return content


_PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "ollama": {
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://192.168.0.123:11434/v1"),
        "api_key_env": "OLLAMA_API_KEY",
        "model": "qwen2.5:7b",
    },
    "openai": {
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-5-codex",
    },
    "tencent_lkeap": {
        "base_url": os.environ.get("TENCENT_LKEAP_BASE_URL", "https://api.lkeap.cloud.tencent.com/v1"),
        "api_key_env": "TENCENT_LKEAP_API_KEY",
        "model": os.environ.get("TENCENT_LKEAP_MODEL", "deepseek-v3-1"),
    },
}


async def structure_medical_record(
    text: str,
    consultation_mode: bool = False,
) -> MedicalRecord:
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise RuntimeError("Unsupported STRUCTURING_LLM provider: {0} (allowed: {1})".format(provider_name, allowed))
    provider = dict(provider)
    if provider_name == "ollama":
        provider["model"] = os.environ.get("OLLAMA_MODEL", provider["model"])
    elif provider_name == "openai":
        provider["base_url"] = os.environ.get("OPENAI_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("OPENAI_MODEL", provider["model"])
    elif provider_name == "tencent_lkeap":
        provider["base_url"] = os.environ.get("TENCENT_LKEAP_BASE_URL", provider["base_url"])
        provider["model"] = os.environ.get("TENCENT_LKEAP_MODEL", provider["model"])
    strict_mode = os.environ.get("LLM_PROVIDER_STRICT_MODE", "true").strip().lower() not in {"0", "false", "no", "off"}
    if strict_mode and provider_name != "ollama":
        key_env = provider["api_key_env"]
        if not os.environ.get(key_env, "").strip():
            raise RuntimeError(
                "Selected provider '{0}' requires {1}, but it is empty; strict mode blocks fallback".format(
                    provider_name,
                    key_env,
                )
            )
    log(f"[LLM:{provider_name}] calling API: {text[:80]}")

    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("STRUCTURING_LLM_TIMEOUT", "30")),
        max_retries=0,
    )
    with trace_block("llm", "structuring.load_prompt"):
        system_prompt = await _get_system_prompt()
    if consultation_mode:
        system_prompt = system_prompt + _CONSULTATION_SUFFIX
    async def _call(model_name: str):
        with trace_block("llm", "structuring.chat_completion", {"provider": provider_name, "model": model_name}):
            return await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                max_tokens=1500,
                temperature=0,
            )

    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    completion = await call_with_retry_and_fallback(
        _call,
        primary_model=provider["model"],
        fallback_model=fallback_model,
        max_attempts=int(os.environ.get("STRUCTURING_LLM_ATTEMPTS", "3")),
        op_name="structuring.chat_completion",
    )
    raw = completion.choices[0].message.content
    log(f"[LLM:{provider_name}] response: {raw}")
    with trace_block("llm", "structuring.parse_response"):
        data = json.loads(raw)
    if isinstance(data, list):
        data = data[0] if data else {}

    # Coerce any non-string field values to strings (some models return arrays/dicts)
    _STR_FIELDS = [
        "history_of_present_illness", "past_medical_history", "physical_examination",
        "auxiliary_examinations", "diagnosis", "treatment_plan", "follow_up_plan",
    ]
    for field in _STR_FIELDS:
        val = data.get(field)
        if val is None or isinstance(val, str):
            continue
        if isinstance(val, list):
            data[field] = "；".join(str(item) for item in val if item)
        elif isinstance(val, dict):
            data[field] = "；".join(f"{k}：{v}" for k, v in val.items())
        else:
            data[field] = str(val)
        log(f"[LLM:{provider_name}] coerced {field} from {type(val).__name__} to str")

    # Hard fallback: chief_complaint must never be null
    if not data.get("chief_complaint"):
        # Strip leading name/demographics (e.g. "张三，男，58岁，") then take first clause
        stripped = re.sub(r'^[\u4e00-\u9fff]{2,4}[，,]?(男|女)?[，,]?\d+岁[，,]?', '', text).strip()
        first_clause = re.split(r'[，。；\n]', stripped)[0].strip()
        data["chief_complaint"] = first_clause[:40] or "门诊就诊"
        log(f"[LLM:{provider_name}] chief_complaint was null, derived: {data['chief_complaint']}")

    return MedicalRecord.model_validate(data)
