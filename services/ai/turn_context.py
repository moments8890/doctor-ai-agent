"""
Per-turn context assembly — DoctorTurnContext.

Implements the two-tier context model from the architecture review:

  AUTHORITATIVE  — workflow state (patient binding, pending records, interview state)
                   Snapshot taken under the per-doctor session lock.
                   Never subject to TTL eviction.

  ADVISORY       — compressed memory, knowledge snippet, conversation history
                   Loaded OUTSIDE the session lock to keep lock scope narrow.
                   May be stale; the LLM treats it as background context only.

Usage:
    ctx = await assemble_turn_context(doctor_id)
    # ctx.workflow  → authoritative, safe for routing / persistence decisions
    # ctx.advisory  → advisory, safe for LLM context injection
    # ctx.provenance → which sources were actually used (for observability)

If the caller already holds the session lock, pass already_locked=True to
prevent re-entrant deadlock:
    async with get_session_lock(doctor_id):
        ctx = await assemble_turn_context(doctor_id, already_locked=True)
        ...
"""

from __future__ import annotations

import time
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from services.patient.interview import InterviewState
    from services.patient.cvd_scale_interview import CVDScaleSession

# ---------------------------------------------------------------------------
# Advisory context cache (TTL-based, in-process)
# Caches advisory-only data: compressed summary message.
# NEVER cache workflow-critical state (patient binding, pending records).
# ---------------------------------------------------------------------------
_ADVISORY_CACHE_TTL = int(os.environ.get("ADVISORY_CACHE_TTL_SECONDS", "300"))
# doctor_id → (expire_monotonic, context_message_or_None)
_context_msg_cache: Dict[str, Tuple[float, Optional[dict]]] = {}


def _get_cached_context_message(doctor_id: str) -> Tuple[bool, Optional[dict]]:
    """Return (hit, context_message). hit=False means cache miss or expired."""
    entry = _context_msg_cache.get(doctor_id)
    if entry and time.monotonic() < entry[0]:
        return True, entry[1]
    return False, None


def _set_cached_context_message(doctor_id: str, msg: Optional[dict]) -> None:
    _context_msg_cache[doctor_id] = (time.monotonic() + _ADVISORY_CACHE_TTL, msg)


def invalidate_context_message_cache(doctor_id: str) -> None:
    """Call after a successful compression to ensure the next session loads fresh summary."""
    _context_msg_cache.pop(doctor_id, None)


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

@dataclass
class WorkflowState:
    """Authoritative doctor workflow state — snapshotted under session lock.

    These fields directly control routing decisions and DB writes.
    They must NOT be subject to TTL eviction or advisory caching.
    """
    current_patient_id: Optional[int] = None
    current_patient_name: Optional[str] = None
    pending_record_id: Optional[str] = None
    pending_create_name: Optional[str] = None
    interview: Optional["InterviewState"] = None
    pending_cvd_scale: Optional["CVDScaleSession"] = None


@dataclass
class AdvisoryContext:
    """Advisory context — loaded outside the session lock.

    May be stale. The LLM should treat these as background knowledge,
    not as authoritative state. Must never influence patient binding
    or pending-write decisions.
    """
    recent_history: List[dict] = field(default_factory=list)
    # Compressed long-term summary from memory.load_context_message(); None if no prior compression.
    context_message: Optional[dict] = None   # {"role": "system", "content": "..."}
    knowledge_snippet: str = ""


@dataclass
class Provenance:
    """Records which context sources were used for this turn — for observability."""
    # How was current_patient determined?
    # "session"   — from in-memory DoctorSession (hydrated from DB)
    # "none"      — no patient currently active
    current_patient_source: str = "none"
    memory_used: bool = False      # compressed summary was injected
    knowledge_used: bool = False   # knowledge snippet was injected


@dataclass
class DoctorTurnContext:
    """Complete per-turn context for a single doctor request.

    Callers assemble this once via assemble_turn_context() and pass it
    through the routing/dispatch pipeline instead of scattering individual
    session field accesses across multiple call sites.
    """
    doctor_id: str
    doctor_name: Optional[str]
    specialty: Optional[str]
    workflow: WorkflowState
    advisory: AdvisoryContext
    provenance: Provenance


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

async def assemble_turn_context(
    doctor_id: str,
    *,
    already_locked: bool = False,
) -> DoctorTurnContext:
    """Assemble a DoctorTurnContext for a single turn.

    Lock discipline:
      1. Acquire session lock (unless already_locked=True)
      2. Snapshot authoritative WorkflowState + session metadata
      3. Copy advisory fields that are cheap to grab under lock (history ref)
      4. Release lock
      5. Load advisory context outside lock (load_context_message DB call, knowledge cache)
      6. Return fully populated DoctorTurnContext
    """
    from services.session import get_session, get_session_lock
    from services.ai.memory import load_context_message

    # ---- Step 1-3: snapshot under lock ----
    async def _snapshot() -> tuple[WorkflowState, str | None, str | None, list[dict]]:
        sess = get_session(doctor_id)
        workflow = WorkflowState(
            current_patient_id=sess.current_patient_id,
            current_patient_name=sess.current_patient_name,
            pending_record_id=sess.pending_record_id,
            pending_create_name=sess.pending_create_name,
            interview=sess.interview,
            pending_cvd_scale=sess.pending_cvd_scale,
        )
        # Copy list reference (safe — push_turn appends, never replaces under this lock)
        history_snapshot = list(sess.conversation_history)
        return workflow, sess.doctor_name, sess.specialty, history_snapshot

    if already_locked:
        workflow, doctor_name, specialty, history_snapshot = await _snapshot()
    else:
        async with get_session_lock(doctor_id):
            workflow, doctor_name, specialty, history_snapshot = await _snapshot()

    # ---- Step 4: determine provenance for workflow ----
    patient_source = "session" if workflow.current_patient_name else "none"

    # ---- Step 5: load advisory context outside lock ----
    context_message: Optional[dict] = None
    memory_used = False
    if not history_snapshot:
        # Fresh session — inject compressed long-term summary if available.
        # Use TTL cache to avoid a DB round-trip on every fresh-session turn.
        cache_hit, cached_msg = _get_cached_context_message(doctor_id)
        if cache_hit:
            context_message = cached_msg
        else:
            context_message = await load_context_message(doctor_id)
            _set_cached_context_message(doctor_id, context_message)
        memory_used = context_message is not None

    # Knowledge snippet — loaded lazily from caller (knowledge loading requires DB + patient context)
    # Callers may enrich advisory.knowledge_snippet after assembly if needed.

    return DoctorTurnContext(
        doctor_id=doctor_id,
        doctor_name=doctor_name,
        specialty=specialty,
        workflow=workflow,
        advisory=AdvisoryContext(
            recent_history=history_snapshot,
            context_message=context_message,
            knowledge_snippet="",
        ),
        provenance=Provenance(
            current_patient_source=patient_source,
            memory_used=memory_used,
            knowledge_used=False,  # updated by caller after knowledge loading
        ),
    )
