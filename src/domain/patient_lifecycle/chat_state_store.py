"""Per-patient ChatSessionState persistence — snapshots ride on patient_messages.

Source-of-truth decision (Task 1.7): instead of a dedicated session-state table,
each newly-inserted PatientMessage that participates in the state machine
carries a JSON snapshot of the post-turn state in `chat_state_snapshot`. The
most recent non-NULL snapshot for a patient is the current state.

Why ride on messages:
  - Single source of truth — messages already exist; no separate writes to keep
    in sync.
  - Audit-trail anchor — every transition is tied to the message that caused it.
  - Forward-only — load_state simply reads the latest non-NULL snapshot, so
    legacy/back-filled rows naturally fall through to "idle".

Public API:
    state = await load_state(session, patient_id)   # ChatSessionState
    raw   = serialize_state(state)                  # JSON str for the column
"""
from __future__ import annotations

import dataclasses
import json
from typing import Optional  # noqa: F401 — kept for type-doc clarity

from sqlalchemy import desc, select

from db.models.patient_message import PatientMessage
from domain.patient_lifecycle.chat_state import ChatSessionState


async def load_state(session, patient_id: int) -> ChatSessionState:
    """Load the most recent ChatSessionState for a patient.

    Returns the parsed snapshot from the latest PatientMessage with a non-null
    `chat_state_snapshot`. Falls back to an idle ChatSessionState() when:
      - the patient has no messages, or
      - all of the patient's messages are legacy-path (NULL snapshot), or
      - the latest snapshot fails to deserialize (corrupt JSON / schema drift).

    The corrupt-snapshot branch is silent-and-idle by design: failing closed
    on bad data is preferable to wedging the chat endpoint on a broken row.
    """
    row = (await session.execute(
        select(PatientMessage)
        .where(
            PatientMessage.patient_id == patient_id,
            PatientMessage.chat_state_snapshot.is_not(None),
        )
        .order_by(desc(PatientMessage.created_at))
        .limit(1)
    )).scalar_one_or_none()
    if row is None or not row.chat_state_snapshot:
        return ChatSessionState()
    try:
        data = json.loads(row.chat_state_snapshot)
        return ChatSessionState(**data)
    except Exception:
        # Corrupt snapshot → fall back to idle so we don't loop on bad data.
        return ChatSessionState()


def serialize_state(state: ChatSessionState) -> str:
    """Serialize a ChatSessionState to a JSON string for the snapshot column."""
    return json.dumps(dataclasses.asdict(state), ensure_ascii=False)
