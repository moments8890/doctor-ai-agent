"""Unified doctor-reply logic.

Single function that handles everything when a doctor responds to a patient,
regardless of which UI triggered it (TaskPage send, PatientDetail reply, etc.):

1. Save outbound message
2. Mark draft as sent/stale
3. Mark inbound messages as handled
4. Update last_activity_at
5. Audit log
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import update

from db.engine import AsyncSessionLocal
from db.crud.patient_message import save_patient_message
from db.models.patient_message import PatientMessage

logger = logging.getLogger(__name__)


async def send_doctor_reply(
    doctor_id: str,
    patient_id: int,
    text: str,
    draft_id: Optional[int] = None,
    ai_disclosure: Optional[str] = None,
) -> int:
    """Send a doctor reply to a patient and clean up all related state.

    Args:
        doctor_id: The doctor's ID.
        patient_id: The patient's ID.
        text: The reply text to send.
        draft_id: If replying from a draft, the draft ID to mark as sent.
        ai_disclosure: Optional AI disclosure label to append.

    Returns:
        The saved message ID.
    """
    # Build final text
    full_text = text
    if ai_disclosure:
        full_text = f"{text}\n\n{ai_disclosure}"

    async with AsyncSessionLocal() as db:
        # 1. Save outbound message
        msg = await save_patient_message(
            db,
            patient_id=patient_id,
            doctor_id=doctor_id,
            content=full_text,
            direction="outbound",
            source="doctor",
            sender_id=doctor_id,
        )

        # 2. Mark specific draft as sent (if provided)
        draft = None
        if draft_id:
            from db.models.message_draft import MessageDraft, DraftStatus
            draft = await db.get(MessageDraft, draft_id)
            if draft and draft.doctor_id == doctor_id:
                draft.status = DraftStatus.sent.value

        # 2b. Log edit pair for persona learning (non-fatal)
        try:
            from domain.knowledge.teaching import log_doctor_edit
            if draft_id and draft and draft.doctor_id == doctor_id:
                await log_doctor_edit(
                    db,
                    doctor_id=doctor_id,
                    entity_type="draft_reply",
                    entity_id=draft_id,
                    original_text=draft.draft_text or "",
                    edited_text=text,
                )
            elif not draft_id:
                await log_doctor_edit(
                    db,
                    doctor_id=doctor_id,
                    entity_type="manual_reply",
                    entity_id=msg.id,
                    original_text="",
                    edited_text=text,
                )
        except Exception as edit_exc:
            logger.warning("[reply] edit logging failed (non-fatal): %s", edit_exc)

        # 3. Mark ALL pending drafts for this patient as stale
        from db.models.message_draft import MessageDraft, DraftStatus
        stale_stmt = (
            update(MessageDraft)
            .where(
                MessageDraft.patient_id == patient_id,
                MessageDraft.doctor_id == doctor_id,
                MessageDraft.status.in_([
                    DraftStatus.generated.value,
                    DraftStatus.edited.value,
                ]),
            )
            .values(status=DraftStatus.stale.value)
        )
        if draft_id:
            # Don't mark the one we just sent as stale
            stale_stmt = stale_stmt.where(MessageDraft.id != draft_id)
        await db.execute(stale_stmt)

        # 4. Mark inbound messages as handled
        await db.execute(
            update(PatientMessage)
            .where(
                PatientMessage.patient_id == patient_id,
                PatientMessage.doctor_id == doctor_id,
                PatientMessage.direction == "inbound",
                PatientMessage.ai_handled == False,  # noqa: E712
            )
            .values(ai_handled=True)
        )

        await db.commit()

    # 5. Update last_activity_at (non-fatal)
    try:
        from db.crud.patient import touch_patient_activity
        async with AsyncSessionLocal() as act_db:
            await touch_patient_activity(act_db, patient_id)
    except Exception:
        logger.warning("[reply] failed to update last_activity_at | patient_id=%s", patient_id)

    logger.info("[reply] doctor=%s patient=%s msg=%s draft=%s", doctor_id, patient_id, msg.id, draft_id)
    return msg.id
