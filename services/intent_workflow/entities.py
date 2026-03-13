"""Layer 2: Entity extraction — pull entities from classification result with provenance."""

from __future__ import annotations

from typing import Optional

from services.ai.intent import Intent, IntentResult
from services.domain.chat_constants import REMINDER_IN_MSG_RE as _REMINDER_IN_MSG_RE
from services.domain.compound_normalizer import has_residual_clinical_content
from services.domain.name_utils import (
    detect_multiple_names,
    is_valid_patient_name,
    leading_name_with_clinical_context,
    patient_name_from_history,
)
from services.session import get_session

from .models import PATIENT_INTENTS as _PATIENT_INTENTS, EntityResolution, EntitySlot


def extract_entities(
    raw: IntentResult,
    decision_source: str,
    text: str,
    history: list[dict],
    doctor_id: str,
    *,
    session: object | None = None,
) -> EntityResolution:
    """Extract entities from the raw IntentResult with provenance tracking.

    Name resolution priority:
    1. IntentResult.patient_name (from LLM or fast_route)
    2. Leading name pattern in text (add_record only)
    3. Patient name from recent history
    4. Session current_patient_name
    5. Candidate / not-found from session (weak)

    Args:
        session: Optional session-like object (duck-typed). When provided,
            used instead of ``get_session()`` for snapshot consistency with
            the classification layer.
    """
    intent = raw.intent
    _sess = session or get_session(doctor_id)

    # Gender & age from classification
    gender: Optional[EntitySlot] = (
        EntitySlot(value=raw.gender, source=decision_source) if raw.gender else None
    )
    age: Optional[EntitySlot] = (
        EntitySlot(value=raw.age, source=decision_source) if raw.age else None
    )

    # Patient name — multi-source resolution
    name_slot: Optional[EntitySlot] = None

    if raw.patient_name and is_valid_patient_name(raw.patient_name):
        # Propagate patient_source from fast_router session backfill if present
        _ps = (raw.extra_data or {}).get("patient_source", decision_source)
        name_slot = EntitySlot(value=raw.patient_name, source=_ps)

    # Fallback cascade — only for intents where patient matters
    if name_slot is None and intent in _PATIENT_INTENTS:
        name_slot = _name_fallback_cascade(text, history, _sess, intent)

    # If name came from candidate, also capture candidate gender/age
    if name_slot and name_slot.source == "candidate":
        if not gender:
            _cg = getattr(_sess, "candidate_patient_gender", None)
            if _cg:
                gender = EntitySlot(value=_cg, source="candidate")
        if not age:
            _ca = getattr(_sess, "candidate_patient_age", None)
            if _ca:
                age = EntitySlot(value=_ca, source="candidate")

    extra = dict(raw.extra_data or {})

    # Enrich with content signals for planner compound detection.
    # Uses residual-text heuristic (compound_normalizer) instead of brittle keyword list.
    if intent == Intent.create_patient:
        _has_clinical, _ = has_residual_clinical_content(
            text or "", raw,
            patient_name=name_slot.value if name_slot else None,
            gender=raw.gender,
            age=raw.age,
        )
        if _has_clinical:
            extra["has_clinical_content"] = True
    if _REMINDER_IN_MSG_RE.search(text or ""):
        extra["has_reminder"] = True

    # Multi-patient conflict detection
    multi_names = detect_multiple_names(text or "")
    if len(multi_names) >= 2:
        extra["multi_patient_names"] = multi_names

    return EntityResolution(
        patient_name=name_slot,
        gender=gender,
        age=age,
        extra_data=extra,
    )


def _name_fallback_cascade(
    text: str,
    history: list[dict],
    sess: object,
    intent: Intent,
) -> Optional[EntitySlot]:
    """Try secondary name sources when the primary (LLM/fast_route) didn't provide one.

    Args:
        sess: Session-like object (real DoctorSession or snapshot proxy).
    """
    # Text pattern: leading name with clinical context (add_record only)
    if intent == Intent.add_record:
        leading = leading_name_with_clinical_context(text)
        if leading:
            return EntitySlot(value=leading, source="text_leading_name")

    # create_patient: skip history/session fallback — inheriting a stale name
    # silently reuses an existing patient instead of prompting for a new name.
    # Only candidate/not_found are valid (e.g. "张三" not found → "新建患者").
    _skip_stale = intent == Intent.create_patient

    # History: recent turns mentioned a patient (server-side only, never client-supplied)
    if not _skip_stale:
        _server_history = getattr(sess, "conversation_history", [])
        hist_name = patient_name_from_history(_server_history)
        if hist_name:
            return EntitySlot(value=hist_name, source="history")

    # Session: active patient
    if not _skip_stale:
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
