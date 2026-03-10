"""fast_router 会话上下文辅助函数：从会话状态回填患者姓名等字段。

Session-context helpers for fast_router.
No intra-package dependencies — safe to import directly everywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from services.ai.intent import Intent, IntentResult

if TYPE_CHECKING:
    from services.session import DoctorSession

# Intents for which patient_name is meaningful and should be backfilled from session
_PATIENT_NAME_INTENTS: frozenset[Intent] = frozenset({
    Intent.add_record,
    Intent.query_records,
    Intent.update_record,
    Intent.export_records,
    Intent.export_outpatient_report,
    Intent.schedule_follow_up,
    Intent.schedule_appointment,
    Intent.import_history,
})


def _apply_session_context(
    result: IntentResult,
    session: Optional["DoctorSession"],
) -> IntentResult:
    """Backfill patient_name from session when the result has none.

    Only applies to intents where a patient context is meaningful.
    Never overwrites an explicitly extracted name.
    """
    if session is None:
        return result
    if result.patient_name is not None:
        return result
    if result.intent not in _PATIENT_NAME_INTENTS:
        return result
    session_name: Optional[str] = getattr(session, "current_patient_name", None)
    if session_name:
        result = IntentResult(
            intent=result.intent,
            patient_name=session_name,
            gender=result.gender,
            age=result.age,
            is_emergency=result.is_emergency,
            extra_data=result.extra_data,
            chat_reply=result.chat_reply,
            structured_fields=result.structured_fields,
            confidence=result.confidence,
        )
    return result
