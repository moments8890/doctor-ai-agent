"""Layer 2: Entity extraction — pull entities from classification result with provenance."""

from __future__ import annotations

from typing import Optional

from services.ai.intent import Intent, IntentResult
from services.domain.chat_constants import (
    CLINICAL_CONTENT_HINTS as _CLINICAL_CONTENT_HINTS,
    REMINDER_IN_MSG_RE as _REMINDER_IN_MSG_RE,
)
from services.domain.name_utils import (
    is_valid_patient_name,
    leading_name_with_clinical_context,
    patient_name_from_history,
)
from services.session import get_session

from .models import EntityResolution, EntitySlot

# Intents where patient_name is meaningful.
_PATIENT_INTENTS: frozenset[Intent] = frozenset({
    Intent.add_record,
    Intent.query_records,
    Intent.update_record,
    Intent.create_patient,
    Intent.delete_patient,
    Intent.update_patient,
    Intent.export_records,
    Intent.export_outpatient_report,
    Intent.schedule_follow_up,
    Intent.schedule_appointment,
    Intent.import_history,
})


def extract_entities(
    raw: IntentResult,
    decision_source: str,
    text: str,
    history: list[dict],
    doctor_id: str,
    *,
    followup_name: Optional[str] = None,
) -> EntityResolution:
    """Extract entities from the raw IntentResult with provenance tracking.

    Name resolution priority:
    1. followup_name (previous turn asked for name, user replied)
    2. IntentResult.patient_name (from LLM or fast_route)
    3. Leading name pattern in text (add_record only)
    4. Patient name from recent history
    5. Session current_patient_name
    6. Candidate / not-found from session (weak)
    """
    intent = raw.intent

    # Gender & age from classification
    gender: Optional[EntitySlot] = (
        EntitySlot(value=raw.gender, source=decision_source) if raw.gender else None
    )
    age: Optional[EntitySlot] = (
        EntitySlot(value=raw.age, source=decision_source) if raw.age else None
    )

    # Patient name — multi-source resolution
    name_slot: Optional[EntitySlot] = None

    if followup_name:
        name_slot = EntitySlot(value=followup_name, source="followup")
    elif raw.patient_name and is_valid_patient_name(raw.patient_name):
        # Propagate patient_source from fast_router session backfill if present
        _ps = (raw.extra_data or {}).get("patient_source", decision_source)
        name_slot = EntitySlot(value=raw.patient_name, source=_ps)

    # Fallback cascade — only for intents where patient matters
    if name_slot is None and intent in _PATIENT_INTENTS:
        name_slot = _name_fallback_cascade(text, history, doctor_id, intent)

    # If name came from candidate, also capture candidate gender/age
    if name_slot and name_slot.source == "candidate":
        sess = get_session(doctor_id)
        if not gender:
            _cg = getattr(sess, "candidate_patient_gender", None)
            if _cg:
                gender = EntitySlot(value=_cg, source="candidate")
        if not age:
            _ca = getattr(sess, "candidate_patient_age", None)
            if _ca:
                age = EntitySlot(value=_ca, source="candidate")

    extra = dict(raw.extra_data or {})

    # Enrich with content signals for planner compound detection.
    if any(hint in (text or "") for hint in _CLINICAL_CONTENT_HINTS):
        extra["has_clinical_content"] = True
    if _REMINDER_IN_MSG_RE.search(text or ""):
        extra["has_reminder"] = True

    return EntityResolution(
        patient_name=name_slot,
        gender=gender,
        age=age,
        is_emergency=raw.is_emergency,
        extra_data=extra,
    )


def _name_fallback_cascade(
    text: str,
    history: list[dict],
    doctor_id: str,
    intent: Intent,
) -> Optional[EntitySlot]:
    """Try secondary name sources when the primary (LLM/fast_route) didn't provide one."""
    # Text pattern: leading name with clinical context (add_record only)
    if intent == Intent.add_record:
        leading = leading_name_with_clinical_context(text)
        if leading:
            return EntitySlot(value=leading, source="text_leading_name")

    # History: recent turns mentioned a patient
    hist_name = patient_name_from_history(history)
    if hist_name:
        return EntitySlot(value=hist_name, source="history")

    # Session: active patient
    sess = get_session(doctor_id)
    sess_name = getattr(sess, "current_patient_name", None)
    if sess_name and is_valid_patient_name(sess_name):
        return EntitySlot(value=sess_name, source="session", confidence=0.9)

    # Candidate patient (from recent create/query — weak)
    cand_name = getattr(sess, "candidate_patient_name", None)
    if cand_name and is_valid_patient_name(cand_name):
        return EntitySlot(value=cand_name, source="candidate", confidence=0.6)

    # Not-found patient (from recent failed lookup — weakest)
    nf_name = getattr(sess, "patient_not_found_name", None)
    if nf_name and is_valid_patient_name(nf_name):
        return EntitySlot(value=nf_name, source="not_found", confidence=0.4)

    return None
