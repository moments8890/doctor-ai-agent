"""Understand → Execute → Compose runtime (ADR 0012).

Public API
----------
process_turn(envelope_or_doctor_id, text?, *, message_id?) -> TurnResult
has_pending_draft(doctor_id) -> bool
clear_pending_draft_id(doctor_id) -> None
CONFIRM_RE / ABANDON_RE — compiled regex for confirm/abandon detection
"""
from __future__ import annotations

from services.runtime.context import clear_pending_draft_id, has_pending_draft
from services.runtime.models import ActionPayload, TurnEnvelope, TurnResult
from services.runtime.turn import ABANDON_RE, CONFIRM_RE, process_turn

__all__ = [
    "ABANDON_RE",
    "ActionPayload",
    "CONFIRM_RE",
    "TurnEnvelope",
    "TurnResult",
    "clear_pending_draft_id",
    "has_pending_draft",
    "process_turn",
]
