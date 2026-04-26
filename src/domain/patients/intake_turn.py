"""Intake turn handler — DEPRECATED shim.

Phase 2.5 moved the turn loop into domain.intake.engine.IntakeEngine.
This module now forwards to the engine and re-exports legacy symbols for
callers not yet migrated. Delete one release after Phase 2.5 ships.
"""
from __future__ import annotations

import asyncio as _asyncio_lock
import warnings

warnings.warn(
    "domain.patients.intake_turn is deprecated; use "
    "domain.intake.engine.IntakeEngine.next_turn instead.",
    DeprecationWarning,
    stacklevel=2,
)

# ---- session lock registry (engine uses this; still central) ----------------

_session_locks: dict[str, "_asyncio_lock.Lock"] = {}
_SESSION_LOCK_CAP = 500


def get_session_lock(session_id: str) -> "_asyncio_lock.Lock":
    """Get or create the per-session asyncio.Lock."""
    if len(_session_locks) >= _SESSION_LOCK_CAP:
        keys = list(_session_locks.keys())
        for k in keys[: len(keys) // 2]:
            _session_locks.pop(k, None)
    return _session_locks.setdefault(session_id, _asyncio_lock.Lock())


def release_session_lock(session_id: str) -> None:
    """Remove the session lock entry when a session is finalized."""
    _session_locks.pop(session_id, None)


# ---- legacy symbol re-exports ----------------------------------------------

from domain.patients.intake_models import (
    MAX_TURNS,
    ExtractedClinicalFields,
    FIELD_LABELS,
    IntakeLLMResponse,
    IntakeResponse,
    _build_progress,
)


# ---- intake_turn: forward to engine -------------------------------------

async def intake_turn(session_id: str, patient_text: str) -> IntakeResponse:
    """DEPRECATED — use IntakeEngine.next_turn directly.

    Forwards to the engine and rebuilds a legacy IntakeResponse from the
    engine's TurnResult + a session reload. Identical behavior, longer call path.
    """
    from domain.intake.engine import IntakeEngine
    from domain.patients.intake_session import load_session

    engine = IntakeEngine()
    result = await engine.next_turn(session_id, patient_text)

    reloaded = await load_session(session_id)
    if reloaded is None:
        return IntakeResponse(
            reply=result.reply, collected={},
            progress={"filled": 0, "total": 0}, status="error",
            missing=list(result.state.required_missing + result.state.recommended_missing),
            suggestions=list(result.suggestions),
            ready_to_review=result.state.can_complete,
        )

    return IntakeResponse(
        reply=result.reply,
        collected=reloaded.collected,
        progress=_build_progress(reloaded.collected, reloaded.mode),
        status=reloaded.status,
        missing=list(result.state.required_missing + result.state.recommended_missing),
        suggestions=list(result.suggestions),
        ready_to_review=result.state.can_complete,
        patient_name=result.metadata.get("patient_name"),
        patient_gender=result.metadata.get("patient_gender"),
        patient_age=result.metadata.get("patient_age"),
    )


__all__ = [
    "MAX_TURNS",
    "ExtractedClinicalFields",
    "IntakeLLMResponse",
    "IntakeResponse",
    "FIELD_LABELS",
    "_build_progress",
    "intake_turn",
    "get_session_lock",
    "release_session_lock",
]
