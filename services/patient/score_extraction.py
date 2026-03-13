"""
专科量表提取：快速关键词检测 + LLM 精确提取。

支持量表：NIHSS、mRS、UPDRS、MMSE、MoCA、GCS、HAMD、HAMA。
快速路径：若文本中无任何量表关键词，直接跳过 LLM 调用。
"""
from __future__ import annotations

import json
import os
from typing import List

from openai import AsyncOpenAI
from services.ai.llm_client import _PROVIDERS
from utils.log import log

# Keyword fast-path — O(n) string scan, no LLM cost if nothing matches
_SCORE_KEYWORD_SETS: list[tuple[str, frozenset[str]]] = [
    ("NIHSS", frozenset({"nihss", "神经功能缺损评分", "神经功能缺损"})),
    ("mRS", frozenset({"mrs", "改良rankin", "改良 rankin", "rankin"})),
    ("UPDRS", frozenset({"updrs", "统一帕金森评定", "帕金森评分"})),
    ("MMSE", frozenset({"mmse", "简易精神状态", "简易智能"})),
    ("MoCA", frozenset({"moca", "蒙特利尔认知", "蒙特利尔"})),
    ("GCS", frozenset({"gcs", "格拉斯哥", "昏迷评分"})),
    ("HAMD", frozenset({"hamd", "汉密尔顿抑郁", "hamilton抑郁"})),
    ("HAMA", frozenset({"hama", "汉密尔顿焦虑", "hamilton焦虑"})),
]

_EXTRACTION_PROMPT = """\
从以下医疗文本中提取所有专科量表评分，以 JSON 对象返回结果。

输出格式：{"scores": [...]}
每个量表条目：{"score_type": "NIHSS", "score_value": 8, "raw_text": "NIHSS评分8分"}

规则：
- score_type: 量表名称，只使用以下之一：NIHSS、mRS、UPDRS、MMSE、MoCA、GCS、HAMD、HAMA
- score_value: 数值（整数或小数），若原文只提到量表名但未给出具体分值则为 null
- raw_text: 原文中的相关片段（不超过50字）
- 若无任何量表信息，返回 {"scores": []}

只输出合法 JSON 对象，不加任何解释或 markdown。
"""


def detect_score_keywords(text: str) -> bool:
    """Return True if text contains any specialty scale keyword (case-insensitive)."""
    text_lower = text.lower()
    for _name, keywords in _SCORE_KEYWORD_SETS:
        for kw in keywords:
            if kw in text_lower:
                return True
    return False


def _resolve_score_provider(provider_name: str) -> "Optional[dict]":
    """根据提供商名称构建并返回带运行时覆盖的 provider 配置字典。"""
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        return None
    provider = dict(provider)
    if provider_name == "ollama":
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
    return provider


def _parse_score_response(raw: str) -> List[dict]:
    """将 LLM 的 JSON 响应解析为量表条目列表。"""
    data = json.loads(raw)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("scores") or []
        if not isinstance(items, list):
            items = []
    else:
        items = []
    return [s for s in items if isinstance(s, dict) and s.get("score_type")]


async def extract_specialty_scores(text: str) -> List[dict]:
    """调用 LLM 从文本中提取专科量表评分；仅在 detect_score_keywords() 为 True 时调用。

    Uses the shared retry/fallback infrastructure to match the main routing
    stack's resilience behavior (exponential backoff + circuit breaker).
    """
    from services.ai.llm_resilience import call_with_retry_and_fallback

    provider_name = os.environ.get("STRUCTURING_LLM", "deepseek")
    provider = _resolve_score_provider(provider_name)
    if provider is None:
        return []

    from utils.prompt_loader import get_prompt
    extraction_prompt = await get_prompt("extraction.specialty_scores", _EXTRACTION_PROMPT)

    async def _call_for_model(model: str) -> List[dict]:
        extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
        client = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=15.0,
            max_retries=0,
            default_headers=extra_headers,
        )
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": extraction_prompt},
                {"role": "user", "content": text[:2000]},
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0,
        )
        return _parse_score_response(completion.choices[0].message.content)

    try:
        fallback_model = os.environ.get("OLLAMA_FALLBACK_MODEL") if provider_name != "ollama" else None
        return await call_with_retry_and_fallback(
            _call_for_model,
            primary_model=provider["model"],
            fallback_model=fallback_model,
            max_attempts=2,
            op_name="score_extraction",
        )
    except Exception as exc:
        log(f"[ScoreExtraction] LLM call failed after retries: {exc}")
        return []
