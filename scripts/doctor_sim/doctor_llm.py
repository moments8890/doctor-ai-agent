"""LLM-driven doctor turn generator for interactive simulation personas.

Instead of scripted turn_plan entries, the doctor LLM reads:
  - the full clinical case (ground truth the doctor knows)
  - the agent's latest response (collected fields, progress, suggestions, missing)
  - what has already been entered

...and decides what to type next, like a real doctor building a record
incrementally.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

import httpx


# ---------------------------------------------------------------------------
# LLM provider — reuse the same pool idea from patient_sim.validator
# ---------------------------------------------------------------------------

_DOCTOR_LLM_POOL = [
    {
        "label": "qwen3-32b (openrouter)",
        "model": "qwen/qwen3-32b",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    {
        "label": "qwen3-32b (groq)",
        "model": "qwen-qwq-32b",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
    },
]


def _pick_doctor_llm() -> dict:
    """Pick the first available LLM provider for doctor turn generation."""
    for p in _DOCTOR_LLM_POOL:
        if os.environ.get(p["api_key_env"]):
            return p
    raise RuntimeError(
        "No API keys for doctor LLM (need OPENROUTER_API_KEY or GROQ_API_KEY)"
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_DOCTOR_TURN_PROMPT = """\
/no_think
你是一位神经外科医生，正在使用AI助手录入病历。

## 你的患者情况
{clinical_case}

## 系统当前状态
已采集字段：{collected_summary}
缺失字段：{missing_fields}
系统建议：{suggestions}

## 之前你已输入的内容
{previous_inputs}

## 规则
- 根据缺失字段，输入下一段临床信息
- 使用真实临床用语，可以用缩写（BP, EF, CTA等）
- 每次输入1-3个字段的信息
- 不要重复你已经输入过的内容
- 如果所有必填字段已完成，只输入"确认生成"
- 只输出医生会输入的原始文本，不要加任何解释或标记

请输入下一段病历内容："""


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

async def generate_doctor_input(
    clinical_case: str,
    collected: Optional[Dict[str, Any]] = None,
    missing: Optional[List[str]] = None,
    suggestions: Optional[str] = None,
    previous_inputs: Optional[List[str]] = None,
    is_first_turn: bool = False,
    patient_info: Optional[Dict[str, str]] = None,
) -> str:
    """Generate the next doctor input turn using an LLM.

    Parameters
    ----------
    clinical_case:
        Full clinical case description (the ground truth the doctor knows).
    collected:
        Dict of currently collected SOAP fields from the agent's last response.
    missing:
        List of missing field names from the agent's last response.
    suggestions:
        Any suggestions the agent returned (e.g. "请补充体格检查").
    previous_inputs:
        List of texts the doctor has already entered in prior turns.
    is_first_turn:
        If True, the LLM should start with chief complaint + demographics.
    patient_info:
        Dict with name/gender/age for the first turn header.

    Returns
    -------
    str
        The text the doctor would type into the system.
    """
    # Build collected summary
    if collected:
        collected_lines = []
        for field, value in collected.items():
            if value and str(value).strip():
                preview = str(value)[:80]
                collected_lines.append(f"  - {field}: {preview}...")
        collected_summary = "\n".join(collected_lines) if collected_lines else "（尚无）"
    else:
        collected_summary = "（尚无）"

    missing_fields = "、".join(missing) if missing else "（无缺失）"
    suggestions_text = suggestions or "（无）"

    if previous_inputs:
        prev_text = "\n---\n".join(
            f"[第{i+1}轮] {t}" for i, t in enumerate(previous_inputs)
        )
    else:
        prev_text = "（这是第一轮输入）"

    prompt = _DOCTOR_TURN_PROMPT.format(
        clinical_case=clinical_case,
        collected_summary=collected_summary,
        missing_fields=missing_fields,
        suggestions=suggestions_text,
        previous_inputs=prev_text,
    )

    # If first turn, prepend a hint to include patient demographics
    if is_first_turn and patient_info:
        name = patient_info.get("name", "患者")
        gender = patient_info.get("gender", "")
        age = patient_info.get("age", "")
        prompt = (
            f"注意：这是第一轮输入，请以患者基本信息开头："
            f"新患者 {name} {gender} {age}岁 神经外科\n"
            f"然后输入主诉和现病史。\n\n" + prompt
        )

    provider = _pick_doctor_llm()
    api_key = os.environ.get(provider["api_key_env"], "")

    data = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{provider['base_url']}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": provider["model"],
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                            }
                        ],
                        "temperature": 0.4,
                        "max_tokens": 1024,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                break
        except Exception:
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))
            else:
                raise

    if data is None:
        raise RuntimeError("generate_doctor_input: no response after 3 attempts")

    content = data["choices"][0]["message"]["content"]

    # Strip any <think>...</think> blocks that reasoning models may emit
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    return content
