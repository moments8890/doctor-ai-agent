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
from domain.patients.interview_turn import release_session_lock as _release_session_lock
from domain.patients.interview_session import (
    load_session as _load_session,
    save_session as _save_session,
)


async def _load_session_state(session_id: str) -> SessionState:
    raw = await _load_session(session_id)
    if raw is None:
        raise LookupError(f"session {session_id} not found")
    return SessionState(
        id=raw.id,
        doctor_id=raw.doctor_id,
        patient_id=raw.patient_id,
        mode=raw.mode,
        status=raw.status,
        template_id=raw.template_id,
        collected=raw.collected,
        conversation=raw.conversation,
        turn_count=raw.turn_count,
    )


async def _save_session_state(sess: SessionState) -> None:
    raw = await _load_session(sess.id)
    if raw is None:
        return
    raw.status = sess.status
    raw.collected = sess.collected
    raw.conversation = sess.conversation
    raw.turn_count = sess.turn_count
    raw.patient_id = sess.patient_id
    await _save_session(raw)


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
        """Confirm the session. Runs batch re-extract, persist, then
        best-effort hooks. Marks the session confirmed.

        Doctor-mode callers may pass `override_patient_name` to force the
        patient name into `_patient_name` before batch extract (preserves
        the current behavior at confirm.py:76-77).
        """
        sess = await _load_session_state(session_id)
        template = get_template(sess.template_id)

        collected = dict(sess.collected)

        if override_patient_name:
            collected["_patient_name"] = override_patient_name.strip()

        if doctor_edits:
            collected = template.extractor.merge(collected, doctor_edits)

        if template.batch_extractor is not None:
            ctx = {
                "name": collected.get("_patient_name", ""),
                "gender": collected.get("_patient_gender", ""),
                "age": collected.get("_patient_age", ""),
            }
            re_extracted = await template.batch_extractor.extract(
                sess.conversation, ctx, sess.mode,
            )
            if re_extracted:
                # Preserve engine-level underscore metadata across re-extract.
                for k, v in collected.items():
                    if k.startswith("_") and k not in re_extracted:
                        re_extracted[k] = v
                collected = re_extracted

        ref = await template.writer.persist(sess, collected)

        for hook in template.post_confirm_hooks[sess.mode]:
            try:
                await hook.run(sess, ref, collected)
            except Exception as e:
                from utils.log import log
                log(
                    f"[engine-confirm] hook {hook.name} failed: {e}",
                    level="warning",
                )

        # Mark confirmed and release lock
        sess_updated = sess.model_copy(update={"status": "confirmed"})
        await _save_session_state(sess_updated)
        _release_session_lock(session_id)

        return ref
