"""Built-in hook registrations for observability.

Registers lightweight logging/metrics hooks that validate the hook pipeline
end-to-end and provide pipeline observability out of the box.

STATUS: DORMANT — this module is not imported at runtime (main.py lifespan
does not import it, and no workflow stage emits hook events).  To activate,
add ``import services.hooks_builtin`` to main.py lifespan or a startup hook.

    import services.hooks_builtin  # noqa: F401 — side-effect registration
"""

from __future__ import annotations

from services.hooks import HookStage, register_hook
from utils.log import log


# ---------------------------------------------------------------------------
# POST_CLASSIFY — log the intent classification decision
# ---------------------------------------------------------------------------

def _log_classification(ctx: dict) -> None:
    """Log intent routing decisions for debugging and metrics."""
    decision = ctx.get("decision")
    intent = getattr(decision, "intent", "?") if decision else "?"
    source = getattr(decision, "source", "?") if decision else "?"
    doctor_id = ctx.get("doctor_id", "?")
    latency = ctx.get("latency_ms")
    latency_str = f" {latency:.0f}ms" if latency is not None else ""
    log(f"[hook:classify] doctor={doctor_id} intent={intent} source={source}{latency_str}")


# ---------------------------------------------------------------------------
# POST_GATE — log gate decisions (especially blocks)
# ---------------------------------------------------------------------------

def _log_gate(ctx: dict) -> None:
    """Log execution gate decisions — highlights blocks for debugging."""
    gate = ctx.get("gate")
    allowed = getattr(gate, "approved", True) if gate else True
    reason = getattr(gate, "reason", "") if gate else ""
    doctor_id = ctx.get("doctor_id", "?")
    decision = ctx.get("decision")
    intent = getattr(decision, "intent", "?") if decision else "?"
    if not allowed:
        log(f"[hook:gate] BLOCKED doctor={doctor_id} intent={intent} reason={reason}")


# ---------------------------------------------------------------------------
# Registration (runs on import)
# ---------------------------------------------------------------------------

register_hook(HookStage.POST_CLASSIFY, _log_classification, priority=50)
register_hook(HookStage.POST_GATE, _log_gate, priority=50)
