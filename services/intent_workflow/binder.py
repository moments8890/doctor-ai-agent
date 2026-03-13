"""Layer 3: Patient binding — resolve entity name to binding status.

Read-only: performs DB lookups but never creates or modifies records.
The handler is responsible for patient creation on 'has_name' status.
"""

from __future__ import annotations

from services.ai.intent import Intent
from services.session import get_session

from .models import PATIENT_INTENTS as _PATIENT_INTENTS, BindingDecision, EntityResolution, IntentDecision


async def bind_patient(
    decision: IntentDecision,
    entities: EntityResolution,
    doctor_id: str,
    *,
    session: object | None = None,
) -> BindingDecision:
    """Resolve patient entity to a binding decision.

    Outcomes:
    - 'bound': patient_id resolved from DB or session
    - 'has_name': name available but not yet looked up (handler will resolve)
    - 'no_name': no patient context available
    - 'not_applicable': intent doesn't need a patient

    Args:
        session: Optional session-like object (duck-typed). When provided,
            used instead of ``get_session()`` for snapshot consistency.
    """
    if decision.intent not in _PATIENT_INTENTS:
        return BindingDecision(status="not_applicable", source="none")

    name_slot = entities.patient_name
    if name_slot is not None:
        needs_review = name_slot.source in ("candidate", "not_found")
        return BindingDecision(
            patient_name=name_slot.value,
            status="has_name",
            source=name_slot.source,
            needs_review=needs_review,
        )

    # No name — check session for patient_id (e.g. set by prior create/query)
    _sess = session or get_session(doctor_id)
    _pid = getattr(_sess, "current_patient_id", None)
    if _pid:
        return BindingDecision(
            patient_id=_pid,
            patient_name=getattr(_sess, "current_patient_name", None),
            status="bound",
            source="session_id",
        )

    return BindingDecision(status="no_name", source="none")
