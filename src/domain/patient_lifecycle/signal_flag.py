"""Always-on red-flag classifier.

Runs on every patient turn regardless of ChatSessionState. Independent
of triage routing — a patient asking 怎么改预约 in the same turn as
胸口剧痛 should have BOTH the routine intent handled AND the red-flag
fired.

API surface is one function: `await detect(message, patient_context)`
returns True iff the message contains an urgent clinical signal. No
session/state argument by design — the classifier is per-turn.

Implementation reuses the existing triage `classify()` machinery so we
don't double-prompt the LLM: triage already produces a category, and
`urgent` is the red-flag signal we care about. Phase 0 ships this as
a thin wrapper; Phase 1+ may swap in a dedicated cheaper classifier
once we have data on which phrases reliably fire `urgent`.
"""
from __future__ import annotations


async def detect(message: str, patient_context: dict) -> bool:
    """Return True if the message contains a red-flag (urgent) signal.

    Per Codex round 2: must run on every turn, must not depend on
    conversational state. The signature is intentionally narrow so
    callers can't accidentally pass in (and depend on) a session arg.
    """
    return await _classify_urgent(message, patient_context)


async def _classify_urgent(message: str, patient_context: dict) -> bool:
    """Reuse the existing triage classifier. Returns True iff
    category == TriageCategory.urgent. Easy to mock in tests.
    """
    from domain.patient_lifecycle.triage import classify, TriageCategory

    result = await classify(message, patient_context)
    return result.category == TriageCategory.urgent
