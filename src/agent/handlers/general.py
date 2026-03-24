"""Fallback handler for general/chitchat messages."""
from __future__ import annotations

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext


@register(IntentType.general)
async def handle_general(ctx: TurnContext) -> HandlerResult:
    """Simple conversational reply — no DB, no LLM for now."""
    return HandlerResult(reply="您好！我是您的AI医疗助手，请问有什么可以帮您？")
