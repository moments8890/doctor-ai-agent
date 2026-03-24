"""Main entry point — Plan-and-Act routing pipeline."""
from __future__ import annotations

from typing import Optional

from agent.identity import set_current_identity
from agent.router import route
from agent.dispatcher import dispatch
from agent.types import TurnContext, HandlerResult
from agent.session import get_session_history, append_to_history
from infra.observability.observability import trace_block
from utils.log import log

# Ensure handler registry is populated
import agent.handlers  # noqa: F401


async def handle_turn(
    text: str,
    role: str,
    identity: str,
    *,
    action_hint: Optional[str] = None,
) -> HandlerResult:
    """One turn of the Plan-and-Act pipeline.

    Channels (web, wechat) call this directly.
    Returns HandlerResult with reply text + optional data (session_id, progress, etc.)
    """
    set_current_identity(identity)

    # Load recent history for routing context
    history = get_session_history(identity)

    with trace_block("agent", "handle_turn", {"identity": identity, "role": role}):
        # Route
        routing = await route(text, identity, history)
        log(f"[turn] identity={identity} role={role} intent={routing.intent.value}")

        # Build context
        ctx = TurnContext(
            doctor_id=identity,
            text=text,
            history=history,
            routing=routing,
        )

        # Dispatch
        result: HandlerResult = await dispatch(ctx)

    # Persist turn
    append_to_history(identity, text, result.reply)

    return result
