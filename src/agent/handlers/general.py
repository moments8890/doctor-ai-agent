"""Handler for general/chitchat messages — calls LLM for natural replies."""
from __future__ import annotations

from agent.dispatcher import register
from agent.llm import llm_call
from agent.prompt_composer import compose_for_intent
from agent.types import IntentType, HandlerResult, TurnContext
from utils.log import log


@register(IntentType.general)
async def handle_general(ctx: TurnContext) -> HandlerResult:
    """Generate a natural conversational reply via LLM."""
    try:
        messages = await compose_for_intent(
            IntentType.general,
            doctor_id=ctx.doctor_id,
            doctor_message=ctx.text,
            history=ctx.history[-5:],
        )
        reply = await llm_call(
            messages=messages,
            op_name="general",
            temperature=0.5,
            max_tokens=200,
        )
        return HandlerResult(reply=reply.strip())
    except Exception as exc:
        log(f"[general] LLM failed, using fallback: {exc}", level="warning")
        return HandlerResult(reply="您好！请问有什么可以帮您？")
