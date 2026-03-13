"""
WeChat 域处理流程：意图分发、待确认病历、通知控制和媒体后台任务的辅助函数。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import NamedTuple, Optional

from db.engine import AsyncSessionLocal
from db.crud import (
    create_patient,
    find_patient_by_name,
    save_record,
    get_all_patients,
    get_pending_record,
    abandon_pending_record,
)
from services.ai.intent import Intent, IntentResult
from services.ai.vision import extract_text_from_image
from services.knowledge.pdf_extract import extract_text_from_pdf
from services.notify.notify_control import (
    parse_notify_command, get_notify_pref, set_notify_mode, set_notify_interval,
    set_notify_cron, set_notify_immediate, format_notify_pref,
)
from services.notify.tasks import create_follow_up_task
from services.session import get_session, set_current_patient, clear_pending_record_id
from services.observability.audit import audit
from services.wechat import wechat_domain as wd
from services.domain.intent_handlers import (
    handle_add_record as _shared_add_record,
    handle_create_patient as _shared_create_patient,
    handle_query_records as _shared_query_records,
    HandlerResult as _HandlerResult,
)
from services.wechat import wechat_media_pipeline as wmp
from services.wechat.wechat_notify import _get_config, _get_access_token, _send_customer_service_msg
from services.wechat.wechat_voice import download_media
from routers.wechat_infra import KB_CONTEXT_CACHE as _KB_CONTEXT_CACHE, KB_CONTEXT_TTL as _KB_CONTEXT_TTL, get_kb_lock as _get_kb_lock
from utils.log import log, safe_create_task


# ── WeChatReply type ─────────────────────────────────────────────────────────

class WeChatReply(NamedTuple):
    """Structured reply from intent dispatch, carrying an optional switch notification."""
    notification: Optional[str]
    text: str


def _hr_to_parts(hr: _HandlerResult) -> WeChatReply:
    """Convert a shared-layer HandlerResult to a WeChatReply."""
    return WeChatReply(notification=hr.switch_notification, text=hr.reply)


def _plain(text: str) -> WeChatReply:
    """Wrap a plain string as a WeChatReply with no notification."""
    return WeChatReply(notification=None, text=text)


# ── WeCom domain binding (legacy compatibility shim) ─────────────────────────
# TODO: remove this monkeypatch layer.  wechat_domain.py should import DB
# functions directly instead of receiving them via runtime attribute injection.
# This coupling makes wechat_domain depend on router import order and makes
# the service layer non-standalone.

def sync_wechat_domain_bindings() -> None:
    from routers import wechat as _w
    wd.AsyncSessionLocal = _w.AsyncSessionLocal
    wd.structure_medical_record = _w.structure_medical_record
    wd.create_patient = create_patient
    wd.find_patient_by_name = find_patient_by_name
    wd.save_record = save_record
    wd.get_all_patients = _w.get_all_patients
    wd.create_follow_up_task = create_follow_up_task


# ── Shared handler helper ─────────────────────────────────────────────────────

from services.domain.adapters import WeChatAdapter as _WeChatAdapter
_wechat_adapter = _WeChatAdapter()


async def _hr_to_text(hr: _HandlerResult) -> str:
    """Convert HandlerResult to WeChat plain-text, prepending switch notification."""
    return await _wechat_adapter.format_reply(hr)


# ── Domain handler shims (unique-to-WeChat functions) ─────────────────────────

async def handle_create_patient(doctor_id: str, intent_result, *, text: str = "") -> str:
    return await _hr_to_text(await _shared_create_patient(
        doctor_id, intent_result, body_text=text or None, original_text=text or None,
    ))


async def handle_add_record(text: str, doctor_id: str, intent_result, history: list = None) -> str:
    return await _hr_to_text(await _shared_add_record(text, doctor_id, history or [], intent_result))


async def handle_query_records(doctor_id: str, intent_result) -> str:
    return await _hr_to_text(await _shared_query_records(doctor_id, intent_result))


async def handle_all_patients(doctor_id: str) -> str:
    sync_wechat_domain_bindings()
    return await wd.handle_all_patients(doctor_id)


async def handle_pending_create(text: str, doctor_id: str) -> Optional[str]:
    """Delegate to the shared pending-create handler and return plain text.

    Returns None when the handler auto-created the patient and the text
    should fall through to background workflow processing.
    """
    from services.session import get_session, clear_pending_create
    from services.domain.name_utils import name_only_text, is_blocked_write_cancel
    from services.domain.intent_handlers import handle_create_patient, handle_pending_create_reply
    sess = get_session(doctor_id)
    pending_name = sess.pending_create_name
    if not pending_name:
        return "好的，已取消。"

    stripped = text.strip()

    # Cancel — use the shared precheck set for consistency
    from services.intent_workflow.precheck import _PENDING_CANCEL_TEXTS
    if is_blocked_write_cancel(stripped) or stripped in _PENDING_CANCEL_TEXTS:
        clear_pending_create(doctor_id)
        return "好的，已取消。"

    # __pending__ sentinel (set by Web/Voice dispatch when no name was parsed).
    # Expect a bare patient name; if not, clear sentinel and fall through.
    if pending_name == "__pending__":
        bare_name = name_only_text(stripped)
        if bare_name:
            clear_pending_create(doctor_id)
            from services.ai.intent import Intent, IntentResult
            _ir = IntentResult(intent=Intent.create_patient, patient_name=bare_name)
            hr = await handle_create_patient(doctor_id, _ir, body_text=text, original_text=text)
            return hr.reply
        # Not a name → clear sentinel, fall through to normal workflow
        clear_pending_create(doctor_id)
        return None

    # Real name path: demographics or clinical auto-create
    hr = await handle_pending_create_reply(text, doctor_id, pending_name)
    if hr is None:
        return None  # caller should fall through to workflow
    return hr.reply


async def handle_menu_event(event_key: str, doctor_id: str) -> str:
    sync_wechat_domain_bindings()
    return await wd.handle_menu_event(event_key, doctor_id)


async def handle_name_lookup(name: str, doctor_id: str) -> str:
    """Resolve a bare patient name: query records if found, or start pending create."""
    from services.session import set_pending_create
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
    if patient:
        _prev = set_current_patient(doctor_id, patient.id, patient.name)
        log(f"[WeChat] name lookup hit: {name} -> patient_id={patient.id}")
        fake = IntentResult(intent=Intent.query_records, patient_name=name)
        result = await _hr_to_text(await _shared_query_records(doctor_id, fake))
        if _prev:
            result = f"🔄 已从【{_prev}】切换到【{patient.name}】\n{result}"
        return result
    set_pending_create(doctor_id, name)
    log(f"[WeChat] name lookup miss: {name} -> pending create")
    return f"没找到{name}这位患者，请问性别和年龄？（或发送「取消」放弃）"


# ── Notify control ───────────────────────────────────────────────────────────

async def handle_notify_control_command(doctor_id: str, text: str) -> str:
    from routers import wechat as _w
    parsed = parse_notify_command(text)
    if not parsed:
        return ""
    action, payload = parsed
    if action == "show":
        pref = await get_notify_pref(doctor_id)
        return format_notify_pref(pref)
    if action == "set_mode":
        pref = await _w.set_notify_mode(doctor_id, payload["notify_mode"])
        mode_text = "自动" if pref.notify_mode == "auto" else "手动"
        return "✅ 通知模式已更新为：{0}".format(mode_text)
    if action == "set_interval":
        pref = await set_notify_interval(doctor_id, int(payload["interval_minutes"]))
        return "✅ 通知频率已更新：每{0}分钟自动检查".format(pref.interval_minutes)
    if action == "set_cron":
        try:
            pref = await set_notify_cron(doctor_id, str(payload["cron_expr"]))
            return "✅ 通知计划已更新：{0}".format(pref.cron_expr or "")
        except ValueError as e:
            return "⚠️ {0}".format(str(e))
    if action == "set_immediate":
        await set_notify_immediate(doctor_id)
        return "✅ 通知计划已更新为：实时检查"
    if action == "trigger_now":
        result = await _w.run_due_task_cycle(doctor_id=doctor_id, include_manual=True, force=True)
        return (
            "✅ 待办通知已触发\n"
            "due={0} eligible={1}\n"
            "sent={2} failed={3}"
        ).format(
            result.get("due_count", 0), result.get("eligible_count", 0),
            result.get("sent_count", 0), result.get("failed_count", 0),
        )
    return ""


# ── Knowledge context loading ────────────────────────────────────────────────

async def load_knowledge_context(doctor_id: str, text: str) -> str:
    """Return cached or freshly loaded knowledge context string."""
    async with _get_kb_lock(doctor_id):
        _kb_cached, _kb_expiry = _KB_CONTEXT_CACHE.get(doctor_id, ("", 0.0))
        if _kb_expiry > time.perf_counter():
            return _kb_cached
        try:
            async with AsyncSessionLocal() as session:
                # Use lazy import via routers.wechat to allow test patching
                from routers import wechat as _w
                ctx = await _w.load_knowledge_context_for_prompt(session, doctor_id, text)
            _KB_CONTEXT_CACHE[doctor_id] = (ctx, time.perf_counter() + _KB_CONTEXT_TTL)
            return ctx
        except Exception as e:
            log(f"[WeChat] knowledge context load FAILED doctor={doctor_id}: {e}")
            return ""


# ── Pending record confirmation ──────────────────────────────────────────────

async def confirm_pending_record(doctor_id: str, pending_id: str) -> str:
    """Delegate to the shared confirm_pending_record and return plain text."""
    from services.intent_workflow.precheck import confirm_pending_record as _shared_confirm
    hr = await _shared_confirm(doctor_id, pending_id)
    return hr.reply


async def _try_draft_correction(text: str, doctor_id: str, pending: object) -> Optional[str]:
    """Delegate to the shared try_draft_correction and return plain text."""
    from services.intent_workflow.precheck import try_draft_correction as _shared_correction
    hr = await _shared_correction(text, doctor_id, pending)
    if hr is None:
        return None
    return hr.reply


async def _reroute_with_context(text: str, doctor_id: str) -> str:
    """Reroute text through _handle_intent with full context (matching bg path)."""
    from services.ai.turn_context import assemble_turn_context
    ctx = await assemble_turn_context(doctor_id, already_locked=False)
    history = list(ctx.advisory.recent_history)
    if ctx.advisory.context_message:
        history = [ctx.advisory.context_message] + history
    knowledge = await load_knowledge_context(doctor_id, text)
    from routers import wechat as _wechat_router
    parts = await _wechat_router.handle_intent(
        text, doctor_id, history=history,
        turn_context=ctx, knowledge_context=knowledge,
    )
    return parts.text


async def handle_pending_record_reply(text: str, doctor_id: str, sess) -> str:
    """Route doctor reply when a pending record draft awaits confirmation.

    NOTE: This function is only used by the legacy sync XML reply path
    (_handle_stateful_sync).  The async background paths now go through
    run_stateful_prechecks() directly.
    """
    pending_id = sess.pending_record_id
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, doctor_id)
    if pending is None:
        clear_pending_record_id(doctor_id)
        log(f"[WeChat] pending record {pending_id} not found or expired, doctor={doctor_id}")
        return await _reroute_with_context(text, doctor_id)
    from services.intent_workflow.precheck import _PENDING_CANCEL_TEXTS, _PENDING_CONFIRM_TEXTS
    stripped = text.strip()
    if stripped in _PENDING_CANCEL_TEXTS:
        async with AsyncSessionLocal() as session:
            await abandon_pending_record(session, pending_id, doctor_id=doctor_id)
        clear_pending_record_id(doctor_id)
        safe_create_task(audit(doctor_id, "DELETE", "pending_record", str(pending_id)))
        return "已撤销。"
    if stripped in _PENDING_CONFIRM_TEXTS:
        return await confirm_pending_record(doctor_id, pending_id)
    correction_reply = await _try_draft_correction(text, doctor_id, pending)
    if correction_reply is not None:
        return correction_reply
    async with AsyncSessionLocal() as session:
        await abandon_pending_record(session, pending_id, doctor_id=doctor_id)
    clear_pending_record_id(doctor_id)
    _pname = pending.patient_name or "未关联患者"
    log(f"[WeChat] pending record abandoned on context switch, doctor={doctor_id} patient={_pname}")
    rerouted = await _reroute_with_context(text, doctor_id)
    return f"⚠️ 【{_pname}】的病历草稿已放弃。\n\n{rerouted}"


# ── Intent dispatch helpers ──────────────────────────────────────────────────

from services.domain.chat_constants import HELP_REPLY as _HELP_TEXT, UNCLEAR_INTENT_REPLY as _FALLBACK_TEXT


async def dispatch_intent_result(text: str, doctor_id: str, intent_result, history: list) -> WeChatReply:
    """Route an IntentResult to the appropriate domain handler."""
    from services.domain.intent_handlers import dispatch_intent

    i = intent_result.intent

    # Channel-specific overrides (WeChat export/import/help/unknown)
    if i == Intent.export_records:
        return _plain(await wd.handle_export_records(doctor_id, intent_result))
    if i == Intent.export_outpatient_report:
        return _plain(await wd.handle_export_outpatient_report(doctor_id, intent_result))
    if i == Intent.import_history:
        return _plain(await wd.handle_import_history(text, doctor_id, intent_result))
    if i == Intent.help:
        return _plain(_HELP_TEXT)
    if i == Intent.unknown:
        return await handle_unknown_intent(text, doctor_id, intent_result, history)

    # Shared dispatch for everything else
    hr = await dispatch_intent(text, doctor_id, history or [], intent_result, original_text=text)
    return _hr_to_parts(hr)


async def handle_unknown_intent(text: str, doctor_id: str, intent_result, history: list) -> WeChatReply:
    """Handle Intent.unknown — return fallback reply.

    Previously this function contained a shadow write path that synthesized
    add_record for symptom-like text and an ad-hoc name_lookup branch that
    mutated workflow state.  Both bypassed the 5-layer pipeline (planner/gate)
    and existed only on WeChat, creating cross-channel inconsistency.
    Removed in favour of letting the formal intent model handle these cases.
    """
    return _plain(intent_result.chat_reply or _FALLBACK_TEXT)


# ── Media background handlers ────────────────────────────────────────────────

async def handle_image_bg(media_id: str, doctor_id: str, open_kfid: str = ""):
    from routers import wechat as _w
    await wmp.handle_image_bg(
        media_id, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_image_text=extract_text_from_image,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w.handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def handle_pdf_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    from routers import wechat as _w
    await wmp.handle_pdf_file_bg(
        media_id, filename, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_pdf_text=extract_text_from_pdf,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w.handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def handle_word_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    from services.knowledge.word_extract import extract_text_from_docx
    from routers import wechat as _w
    await wmp.handle_word_file_bg(
        media_id, filename, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_word_text=extract_text_from_docx,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w.handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def _handle_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    from routers import wechat as _w
    await wmp.handle_file_bg(
        media_id, filename, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_pdf_file_bg_fn=lambda mid, fname, uid: handle_pdf_file_bg(mid, fname, uid, open_kfid=open_kfid),
        handle_word_file_bg_fn=lambda mid, fname, uid: handle_word_file_bg(mid, fname, uid, open_kfid=open_kfid),
        log=log,
    )
