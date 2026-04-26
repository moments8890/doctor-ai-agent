"""Priority resolution for patient-reply drafts.

When the AI emits the defer-to-doctor pattern (per locked plan rule 19),
the draft must surface as urgent in the doctor's review queue. After-hours
defers escalate to "critical".

Office hours default: 06:00-22:00 local. Outside this window, defers are
critical because the doctor SLA is unclear (Codex round-5 review).

This is intentionally simple. A future iteration can:
- Read per-doctor availability windows from a settings table
- Wire critical priority to a push notification / SMS
- Add a backup-on-call escalation path
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Optional


# Office hours window. Outside this range, defer-pattern drafts are
# escalated to critical. Doctor-configurable later; hardcoded for v1.
_OFFICE_OPEN = time(hour=6, minute=0)
_OFFICE_CLOSE = time(hour=22, minute=0)


def is_after_hours(now: Optional[datetime] = None) -> bool:
    """True if current local time is outside 06:00-22:00."""
    t = (now or datetime.now()).time()
    return not (_OFFICE_OPEN <= t < _OFFICE_CLOSE)


def resolve_draft_priority(
    *,
    deferred_to_doctor: bool,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Return the priority label for a freshly generated draft.

    - None  / "normal":  not deferred (regular draft)
    - "urgent":          deferred during office hours
    - "critical":        deferred AND after-hours

    The DB column is nullable; None means normal-priority. We return None
    rather than the literal "normal" so existing rows without the column
    populated remain identical to new normal rows in queries.
    """
    if not deferred_to_doctor:
        return None
    if is_after_hours(now):
        return "critical"
    return "urgent"
