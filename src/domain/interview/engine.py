"""InterviewEngine — template-agnostic orchestrator.

Spec §5c (next_turn), §5d (confirm). Phase 1 forwards heavy lifting to
legacy functions; Phase 2 inlines them using the template's protocols.
"""
from __future__ import annotations

from typing import Any

from domain.interview.protocols import (
    CompletenessState, PersistRef, SessionState, Template, TurnResult,
)
from domain.interview.templates import get_template

# Legacy imports — renamed with leading underscore to make Phase 2 sweep obvious.
from domain.patients.interview_turn import interview_turn as _legacy_interview_turn
from domain.patients.interview_session import (
    load_session as _load_session,
    save_session as _save_session,
)


class InterviewEngine:
    """Generic engine. One instance serves every template.

    Phase 1: turn loop forwards to domain.patients.interview_turn.interview_turn.
    Phase 2: inlines the loop using template.extractor.* methods.
    """

    async def next_turn(
        self,
        session_id: str,
        user_input: str,
    ) -> TurnResult:
        """Execute one turn. Phase 1 is a structural passthrough."""
        raw = await _legacy_interview_turn(session_id, user_input)

        state = CompletenessState(
            can_complete=bool(raw.ready_to_review),
            required_missing=[],
            recommended_missing=list(raw.missing or []),
            optional_missing=[],
            next_focus=(raw.missing[0] if raw.missing else None),
        )

        metadata: dict[str, Any] = {}
        if raw.patient_name:
            metadata["patient_name"] = raw.patient_name
        if raw.patient_gender:
            metadata["patient_gender"] = raw.patient_gender
        if raw.patient_age:
            metadata["patient_age"] = raw.patient_age

        return TurnResult(
            reply=raw.reply,
            suggestions=list(raw.suggestions or []),
            state=state,
            metadata=metadata,
        )

    async def confirm(
        self,
        session_id: str,
        doctor_edits: dict[str, str] | None = None,
        override_patient_name: str | None = None,
    ) -> PersistRef:
        """Defined in Task 10. Raises NotImplementedError in Task 9."""
        raise NotImplementedError  # Task 10 fills this in
