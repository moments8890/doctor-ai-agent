"""
Shared intent handlers — channel-agnostic business logic.

Re-exports key types and functions for convenient access.
"""

from __future__ import annotations

from services.domain.intent_handlers._types import HandlerResult
from services.domain.intent_handlers._confirm_pending import (
    save_pending_record,
    _parse_pending_draft,
    _persist_pending_record,
    _fire_post_save_tasks,
)
from services.domain.intent_handlers._query_records import (
    handle_query_records,
)
from services.domain.intent_handlers._simple_intents import (
    handle_cancel_task,
    handle_complete_task,
    handle_delete_patient,
    handle_list_patients,
    handle_list_tasks,
    handle_postpone_task,
    handle_schedule_appointment,
    handle_schedule_follow_up,
    handle_update_patient,
    handle_update_record,
)
from services.domain.intent_handlers._add_record import (
    handle_add_record,
)
from services.domain.intent_handlers._create_patient import (
    handle_create_patient,
)

__all__ = [
    "HandlerResult",
    "save_pending_record",
    "_parse_pending_draft",
    "_persist_pending_record",
    "_fire_post_save_tasks",
    "handle_add_record",
    "handle_create_patient",
    "handle_query_records",
    "handle_cancel_task",
    "handle_complete_task",
    "handle_delete_patient",
    "handle_list_patients",
    "handle_list_tasks",
    "handle_postpone_task",
    "handle_schedule_appointment",
    "handle_schedule_follow_up",
    "handle_update_patient",
    "handle_update_record",
]
