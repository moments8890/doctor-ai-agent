"""Deterministic intent dispatcher — routes RoutingResult to handlers."""
from __future__ import annotations

from typing import Callable, Dict

from agent.types import IntentType, HandlerResult, TurnContext
from infra.observability.observability import trace_block
from utils.log import log

HandlerFn = Callable[[TurnContext], HandlerResult]

HANDLERS: Dict[IntentType, HandlerFn] = {}


def register(intent: IntentType):
    """Decorator to register a handler for an intent."""
    def decorator(fn: HandlerFn) -> HandlerFn:
        HANDLERS[intent] = fn
        return fn
    return decorator


async def dispatch(ctx: TurnContext) -> HandlerResult:
    """Dispatch to the registered handler for ctx.routing.intent."""
    intent = ctx.routing.intent
    handler = HANDLERS.get(intent)

    if handler is None:
        log(f"[dispatcher] no handler for intent={intent.value}, using general")
        handler = HANDLERS.get(IntentType.general)

    if handler is None:
        return HandlerResult(reply="抱歉，我没有理解您的意思。请再试一次。")

    log(f"[dispatcher] intent={intent.value} → {handler.__name__}")

    with trace_block("agent", f"handler.{intent.value}", {"patient": ctx.routing.patient_name}):
        result = await handler(ctx)

    if ctx.routing.deferred:
        result = HandlerResult(
            reply=f"{result.reply}\n\n您还提到：{ctx.routing.deferred}——请单独发送以处理。",
            data=result.data,
        )

    return result
