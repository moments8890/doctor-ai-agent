"""Routing LLM — classifies doctor messages into intents.

Uses instructor + tool-calling protocol for reliable structured output.
The LLM is forced to return a validated RoutingResult via function calling,
eliminating JSON mode reliability issues with Qwen3/Groq.
"""
from __future__ import annotations

from typing import List, Dict

from agent.llm import structured_call
from agent.types import IntentType, RoutingResult
from utils.log import log
from utils.prompt_loader import get_prompt_sync


async def route(
    text: str,
    doctor_id: str,
    history: List[Dict[str, str]],
) -> RoutingResult:
    """Classify a doctor message into an intent with extracted entities.

    Returns RoutingResult. On any error, falls back to IntentType.general
    so the conversation never breaks.
    """
    system_prompt = get_prompt_sync("routing")
    messages = [
        {"role": "system", "content": system_prompt},
        *history[-5:],
        {"role": "user", "content": text},
    ]

    try:
        result = await structured_call(
            response_model=RoutingResult,
            messages=messages,
            op_name="routing",
            temperature=0.1,
            max_tokens=512,
            max_retries=2,
        )
        log(f"[router] intent={result.intent.value} patient={result.patient_name} deferred={result.deferred}")
        return result
    except Exception as exc:
        log(f"[router] classification failed, falling back to general: {exc}", level="warning")
        return RoutingResult(intent=IntentType.general)
