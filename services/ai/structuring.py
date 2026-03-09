"""
将医生口述或文字转换为结构化病历 JSON，支持多轮提示和系统提示覆盖。
"""

from __future__ import annotations

import json
import os
import re
import time
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

# Seed value — written to DB on first startup. After that, DB is the source of truth.
# To reset to defaults: delete the 'structuring' row in /admin → System Prompts.
_SEED_PROMPT = """\
你是医生的智能助手，将医生口述或文字记录整理为一段简洁的临床笔记，并提取关键词标签。
输入可能是语音转写（含噪音）、口语化文字或缩写，请准确识别并规范化。
输入若以引号或"记录一下"开头，忽略引导语，直接处理临床内容。

【严禁虚构】只能使用原文中明确出现的信息，不得推断或补充任何未提及的内容。

【输出格式】只输出合法 JSON 对象，包含以下两个字段：

  "content"（必填）
    · 整理后的中文临床笔记，字符串，自由文本
    · 清理 ASR 噪音（"嗯""啊"等语气词）、修复口语化表达
    · 保留所有临床信息：症状、诊断、用药、检查结果、随访安排等
    · 保持医学术语规范（STEMI、PCI、BNP、EF、EGFR 等缩写保留）
    · 以简洁的第三人称或无主语方式书写
    · 示例："患者复诊。血压 142/90 mmHg，控制尚可。继续氨氯地平 5 mg。3 个月后随访。"
    · 若输入极简，直接整理为一句话，不得返回空字符串

  "tags"（必填，可为空数组）
    · 关键词字符串数组，只提取原文明确出现的信息
    · 诊断名称：如 "高血压" "急性STEMI" "2型糖尿病"
    · 药品（含剂量）：如 "氨氯地平5mg" "阿司匹林100mg"
    · 随访时间：如 "随访3个月" "1周后复诊" "下周随访"
    · 数量：3～8 个标签，无法确定时返回 []

  "record_type"（选填）
    · 本次记录类型，从以下取值：
      "outpatient"（门诊）| "inpatient"（住院）| "emergency"（急诊）|
      "followup"（随访/复诊）| "consultation"（会诊）| "discharge_summary"（出院小结）|
      "procedure_note"（操作记录）| "other"
    · 无法判断时省略此字段

  "specialty_scores"（选填，仅含明确出现的评分）
    · 只列出原文中有明确数值的专科评分，JSON对象，键为评分名，值为整数
    · 常见：{"NIHSS": 8, "GCS": 14, "mRS": 3, "Hunt-Hess": 2, "ICH_score": 4}
    · 未提及的评分不得填入，无评分时省略此字段

不加任何解释或 markdown，只输出 JSON。
"""

_CONSULTATION_SUFFIX = """

【问诊对话模式】
输入为医生与患者的问诊对话转写文本，非单人口述。

提取规则：
- 将医患双方的有效信息整合写入 content（症状、确认的既往史、体征、检查、诊断、用药、随访）
- 严禁将医生的询问性语言作为已确认信息，疑问句须有患者明确应答才能记录
- tags 从整合后的信息中提取
"""

_FOLLOWUP_SUFFIX = """

【复诊记录模式】
本次为复诊/随访记录，重点关注：
- 自上次就诊以来症状的变化（好转/加重/无变化）
- 用药依从性和副作用
- 新发或加重的体征/检查结果
- 治疗方案调整（剂量、药物变化）
- 下次随访计划
content 以「复诊：」开头，简洁记录间期变化，无需重复既往完整病史。"""

_FOLLOWUP_KEYWORDS = frozenset({
    "复诊", "随访", "复查", "上次", "那次", "上回", "继续上次",
    "之前开的药", "药吃完", "回来复查", "按时随访",
})

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
    except Exception as exc:
        log("[Structuring] load prompt from DB failed, falling back to seed prompt: {0}".format(exc))
        content = _SEED_PROMPT
    _PROMPT_CACHE = (time.time(), content)
    return content




def detect_followup_from_text(text: str) -> bool:
    """Return True if the text suggests a follow-up/return visit."""
    return any(kw in text for kw in _FOLLOWUP_KEYWORDS)


async def structure_medical_record(
    text: str,
    consultation_mode: bool = False,
    encounter_type: str = "unknown",
) -> MedicalRecord:
    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        allowed = ", ".join(sorted(_PROVIDERS.keys()))
        raise RuntimeError("Unsupported STRUCTURING_LLM provider: {0} (allowed: {1})".format(provider_name, allowed))
    provider = dict(provider)
    if provider_name == "ollama":
        # OLLAMA_STRUCTURING_MODEL overrides OLLAMA_MODEL for the structuring call,
        # allowing a larger/more accurate model (e.g. 14b) while routing uses 7b.
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

    client = _get_structuring_client(provider_name, provider)
    with trace_block("llm", "structuring.load_prompt"):
        system_prompt = await _get_system_prompt()
    if consultation_mode:
        system_prompt = system_prompt + _CONSULTATION_SUFFIX
    if encounter_type == "follow_up":
        system_prompt = system_prompt + _FOLLOWUP_SUFFIX
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

    # Coerce content to string if model returns unexpected type
    content_val = data.get("content")
    if content_val is None or not isinstance(content_val, str):
        if isinstance(content_val, list):
            data["content"] = "；".join(str(x) for x in content_val if x)
        elif isinstance(content_val, dict):
            data["content"] = "；".join(f"{k}：{v}" for k, v in content_val.items())
        elif content_val is not None:
            data["content"] = str(content_val)

    # Hard fallback: content must never be empty
    if not (data.get("content") or "").strip():
        stripped = re.sub(r'^[\u4e00-\u9fff]{2,4}[，,]?(男|女)?[，,]?\d+岁[，,]?', '', text).strip()
        data["content"] = stripped[:200] or "门诊就诊"
        log(f"[LLM:{provider_name}] content was empty, derived from input")

    # Ensure tags is a list of strings
    tags_val = data.get("tags")
    if not isinstance(tags_val, list):
        data["tags"] = []
    else:
        data["tags"] = [str(t) for t in tags_val if t]

    return MedicalRecord.model_validate(data)
