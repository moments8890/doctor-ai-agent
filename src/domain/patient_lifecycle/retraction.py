"""Red-flag retraction.

When signal_flag.detect fires within an intake segment, mark all prior AI whitelist
replies in that segment as retracted=True so they render struck-through with a
"已撤回" tag in both patient and doctor views.

Usage::

    from domain.patient_lifecycle.retraction import retract_recent_whitelist_replies

    count = await retract_recent_whitelist_replies(session, intake_segment_id=seg_id)
"""
from __future__ import annotations

from sqlalchemy import update

from db.models.patient_message import PatientMessage


async def retract_recent_whitelist_replies(session, intake_segment_id: str) -> int:
    """Mark all AI whitelist replies in the given segment as retracted.

    Only targets messages where:
    - ``intake_segment_id`` matches the given segment
    - ``source == "ai"`` (AI-authored)
    - ``is_whitelist_reply == True`` (auto-reply from whitelist path)
    - ``retracted == False`` (not already retracted)

    Returns the number of rows updated.
    """
    result = await session.execute(
        update(PatientMessage)
        .where(
            PatientMessage.intake_segment_id == intake_segment_id,
            PatientMessage.source == "ai",
            PatientMessage.is_whitelist_reply == True,  # noqa: E712
            PatientMessage.retracted == False,  # noqa: E712
        )
        .values(retracted=True)
    )
    await session.flush()
    return result.rowcount
