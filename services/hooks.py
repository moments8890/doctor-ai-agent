"""Lightweight hook mechanism for the intent workflow pipeline.

Allows external modules to register callbacks at key pipeline stages without
modifying core workflow code.  Inspired by chatgpt-on-wechat's 4-stage event
pipeline, but deliberately minimal: no plugin loader, no git installer — just
``register_hook()`` / ``emit()``.

Usage::

    from services.hooks import HookStage, register_hook

    async def log_classification(ctx):
        print(f"Intent: {ctx['intent']} via {ctx['source']}")

    register_hook(HookStage.POST_CLASSIFY, log_classification)

Hooks are non-blocking by default: async callbacks are spawned as tasks, and
exceptions in any callback do *not* propagate to the caller.
"""

from __future__ import annotations

import asyncio
import enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.log import log


class HookStage(str, enum.Enum):
    """Pipeline stages where hooks can fire."""

    POST_CLASSIFY = "post_classify"
    POST_EXTRACT = "post_extract"
    POST_BIND = "post_bind"
    POST_PLAN = "post_plan"
    POST_GATE = "post_gate"
    PRE_REPLY = "pre_reply"


# Internal registry: stage → list of (priority, callback).
# Lower priority number = runs first.
_hooks: Dict[HookStage, List[Tuple[int, Callable]]] = {
    stage: [] for stage in HookStage
}


def register_hook(
    stage: HookStage,
    callback: Callable,
    priority: int = 100,
) -> None:
    """Register a hook callback for a pipeline stage.

    Args:
        stage: Which pipeline stage to listen on.
        callback: Sync or async callable.  Receives a single ``dict`` context.
        priority: Lower number = runs first.  Default 100.
    """
    _hooks[stage].append((priority, callback))
    _hooks[stage].sort(key=lambda t: t[0])


def unregister_hook(stage: HookStage, callback: Callable) -> bool:
    """Remove a previously registered hook.  Returns True if found."""
    before = len(_hooks[stage])
    _hooks[stage] = [(p, cb) for p, cb in _hooks[stage] if cb is not callback]
    return len(_hooks[stage]) < before


def clear_hooks(stage: Optional[HookStage] = None) -> None:
    """Remove all hooks, or hooks for a specific stage (useful in tests)."""
    if stage is not None:
        _hooks[stage] = []
    else:
        for s in HookStage:
            _hooks[s] = []


def list_hooks(stage: Optional[HookStage] = None) -> Dict[str, int]:
    """Return a mapping of ``stage_name → hook_count`` for introspection."""
    if stage is not None:
        return {stage.value: len(_hooks[stage])}
    return {s.value: len(_hooks[s]) for s in HookStage}


async def emit(stage: HookStage, context: Dict[str, Any]) -> None:
    """Fire all registered hooks for *stage* with the given *context* dict.

    - Async callbacks are awaited in priority order.
    - Sync callbacks are called directly.
    - Exceptions are logged but never propagate — hooks must not break the
      pipeline.
    """
    entries = _hooks.get(stage)
    if not entries:
        return

    for _priority, callback in entries:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(context)
            else:
                callback(context)
        except Exception:
            log(
                f"[hooks] callback {getattr(callback, '__name__', callback)} "
                f"failed on {stage.value}",
                exc_info=True,
            )


async def emit_background(stage: HookStage, context: Dict[str, Any]) -> None:
    """Fire hooks as a background task — does not block the caller.

    Use this for PRE_REPLY hooks where latency matters.
    """
    entries = _hooks.get(stage)
    if not entries:
        return

    async def _run() -> None:
        await emit(stage, context)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        # No running loop — fall back to synchronous emit.
        await emit(stage, context)
