"""Routing LLM — classifies doctor messages into intents.

Uses composer for layered prompt assembly + instructor for structured output.
"""
from __future__ import annotations

from typing import List, Dict

from agent.llm import structured_call
from agent.prompt_composer import compose_for_routing
from agent.types import IntentType, RoutingResult
from utils.log import log


async def route(
    text: str,
    doctor_id: str,
    history: List[Dict[str, str]],
) -> RoutingResult:
    """Classify a doctor message into an intent with extracted entities."""
    messages = compose_for_routing(
        doctor_message=text,
        history=history[-5:],
    )

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
