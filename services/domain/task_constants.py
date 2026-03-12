from __future__ import annotations

from typing import FrozenSet, Tuple


DOCTOR_TASK_TYPES: Tuple[str, ...] = (
    "follow_up",
    "emergency",
    "appointment",
    "general",
    "lab_review",
    "referral",
    "imaging",
    "medication",
)

DOCTOR_TASK_TYPE_SET: FrozenSet[str] = frozenset(DOCTOR_TASK_TYPES)


def doctor_task_types_check_sql() -> str:
    quoted = ",".join(f"'{task_type}'" for task_type in DOCTOR_TASK_TYPES)
    return f"task_type IN ({quoted})"
