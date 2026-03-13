"""
Unified intent dispatch — routes IntentResult to shared domain handlers.

All channels (web, voice, WeChat) delegate here for the common routing table
and compound-intent logic.  Channel-specific intents (export, import, help)
should be handled by the router *before* calling ``dispatch_intent``.
"""
from __future__ import annotations

from typing import Optional

from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult
from services.domain.intent_handlers._add_record import handle_add_record
from services.domain.intent_handlers._create_patient import handle_create_patient
from services.domain.intent_handlers._query_records import handle_query_records
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
from utils.log import log

from services.domain.chat_constants import UNCLEAR_INTENT_REPLY as _FALLBACK_TEXT


# ---------------------------------------------------------------------------
# Compound helpers
# ---------------------------------------------------------------------------

async def _compound_create_and_record(
    text: str,
    original_text: str,
    doctor_id: str,
    history: list,
    intent_result: IntentResult,
) -> HandlerResult:
    """Create patient, then immediately create a record draft from the same message."""
    hr_create = await handle_create_patient(
        doctor_id, intent_result, body_text=text, original_text=original_text,
    )
    if not hr_create.reply or "⚠️" in hr_create.reply or not intent_result.patient_name:
        return hr_create

    from services.domain.text_cleanup import strip_leading_create_demographics
    clinical_text = strip_leading_create_demographics(text, intent_result) or text
    add_ir = IntentResult(
        intent=Intent.add_record,
        patient_name=intent_result.patient_name,
    )
    hr_record = await handle_add_record(clinical_text, doctor_id, history, add_ir)

    combined_reply = hr_create.reply
    if hr_record.reply:
        combined_reply += "\n" + hr_record.reply
    return HandlerResult(
        reply=combined_reply,
        record=hr_record.record,
        pending_id=hr_record.pending_id,
        pending_patient_name=hr_record.pending_patient_name,
        pending_expires_at=hr_record.pending_expires_at,
        switch_notification=hr_create.switch_notification or hr_record.switch_notification,
    )


async def _handle_export_import(
    text: str,
    doctor_id: str,
    intent: Intent,
    intent_result: "IntentResult",
) -> HandlerResult:
    """Delegate export/import intents to existing handlers.

    These handlers live in the WeChat service layer but are channel-agnostic
    (they fetch data from DB and format text; PDF sending fails gracefully
    with a text fallback on non-WeChat channels).
    """
    from services.wechat.wechat_export import (
        handle_export_records,
        handle_export_outpatient_report,
    )
    from services.wechat.wechat_import import handle_import_history

    if intent == Intent.export_records:
        reply = await handle_export_records(doctor_id, intent_result)
    elif intent == Intent.export_outpatient_report:
        reply = await handle_export_outpatient_report(doctor_id, intent_result)
    else:
        reply = await handle_import_history(text, doctor_id, intent_result)
    return HandlerResult(reply=reply)


async def _maybe_compound_task(
    original_text: str,
    doctor_id: str,
    intent_result: IntentResult,
    hr: HandlerResult,
) -> HandlerResult:
    """If add_record message also contains a reminder, create a task alongside."""
    compound = (intent_result.extra_data or {}).get("compound_actions") or []
    if "create_task" not in compound:
        return hr
    if not hr.pending_id:
        return hr  # record didn't produce a draft; skip task creation

    from services.domain.chat_constants import REMINDER_IN_MSG_RE
    match = REMINDER_IN_MSG_RE.search(original_text)
    if not match:
        return hr

    from services.notify.tasks import create_general_task
    from services.session import get_session as _get_session
    task_title_raw = match.group(1).strip().rstrip("。！")
    pname = intent_result.patient_name or "未关联患者"
    task_title = f"【{pname}】{task_title_raw}"
    _patient_id = getattr(_get_session(doctor_id), "current_patient_id", None)
    try:
        task = await create_general_task(doctor_id, task_title, patient_id=_patient_id)
        return HandlerResult(
            reply=(hr.reply or "") + f"\n📋 已创建提醒任务：{task_title}（编号 {task.id}）",
            record=hr.record,
            pending_id=hr.pending_id,
            pending_patient_name=hr.pending_patient_name,
            pending_expires_at=hr.pending_expires_at,
            switch_notification=hr.switch_notification,
        )
    except Exception as e:
        log(f"[dispatch] compound create_task FAILED doctor={doctor_id}: {e}")
        return hr


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def dispatch_intent(
    text: str,
    doctor_id: str,
    history: list,
    intent_result: IntentResult,
    *,
    original_text: Optional[str] = None,
) -> HandlerResult:
    """Route an IntentResult to the appropriate shared domain handler.

    Export/import intents (export_records, export_outpatient_report,
    import_history) are handled directly here via _handle_export_import().
    The help intent should still be intercepted by the channel router.
    """
    original_text = original_text or text
    intent = intent_result.intent

    # -- create_patient (+ optional compound add_record) --------------------
    if intent == Intent.create_patient:
        compound = (intent_result.extra_data or {}).get("compound_actions") or []
        if "add_record" in compound:
            return await _compound_create_and_record(
                text, original_text, doctor_id, history, intent_result,
            )
        return await handle_create_patient(
            doctor_id, intent_result, body_text=text, original_text=original_text,
        )

    # -- add_record (+ optional compound create_task) -----------------------
    if intent == Intent.add_record:
        hr = await handle_add_record(text, doctor_id, history, intent_result)
        return await _maybe_compound_task(original_text, doctor_id, intent_result, hr)

    # -- simple intents -----------------------------------------------------
    if intent == Intent.query_records:
        return await handle_query_records(doctor_id, intent_result)
    if intent == Intent.list_patients:
        return await handle_list_patients(doctor_id)
    if intent == Intent.delete_patient:
        return await handle_delete_patient(doctor_id, intent_result)
    if intent == Intent.list_tasks:
        return await handle_list_tasks(doctor_id, intent_result)
    if intent == Intent.complete_task:
        return await handle_complete_task(doctor_id, intent_result, text=original_text)
    if intent == Intent.schedule_appointment:
        return await handle_schedule_appointment(doctor_id, intent_result)
    if intent == Intent.update_patient:
        return await handle_update_patient(doctor_id, intent_result)
    if intent == Intent.update_record:
        return await handle_update_record(doctor_id, intent_result, text=original_text)
    if intent == Intent.schedule_follow_up:
        return await handle_schedule_follow_up(doctor_id, intent_result)
    if intent == Intent.cancel_task:
        return await handle_cancel_task(doctor_id, intent_result)
    if intent == Intent.postpone_task:
        return await handle_postpone_task(doctor_id, intent_result)

    # -- export / import (available on all channels) -------------------------
    if intent in (Intent.export_records, Intent.export_outpatient_report, Intent.import_history):
        return await _handle_export_import(text, doctor_id, intent, intent_result)

    # -- fallback -----------------------------------------------------------
    return HandlerResult(reply=intent_result.chat_reply or _FALLBACK_TEXT)
