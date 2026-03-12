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
    handle_cancel_task as _shared_cancel_task,
    handle_create_patient as _shared_create_patient,
    handle_complete_task as _shared_complete_task,
    handle_delete_patient as _shared_delete_patient,
    handle_list_patients as _shared_list_patients,
    handle_list_tasks as _shared_list_tasks,
    handle_postpone_task as _shared_postpone_task,
    handle_query_records as _shared_query_records,
    handle_schedule_appointment as _shared_schedule_appointment,
    handle_schedule_follow_up as _shared_schedule_follow_up,
    handle_update_patient as _shared_update_patient,
    handle_update_record as _shared_update_record,
    HandlerResult as _HandlerResult,
)
from services.wechat import wechat_media_pipeline as wmp
from services.wechat.wechat_notify import _get_config, _get_access_token, _send_customer_service_msg
from services.wechat.wechat_voice import download_media
from routers.wechat_infra import KB_CONTEXT_CACHE as _KB_CONTEXT_CACHE, KB_CONTEXT_TTL as _KB_CONTEXT_TTL, get_kb_lock as _get_kb_lock
from utils.log import log


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


# ── WeCom domain binding ─────────────────────────────────────────────────────

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

async def handle_create_patient(doctor_id: str, intent_result) -> str:
    return await _hr_to_text(await _shared_create_patient(doctor_id, intent_result))


async def handle_add_record(text: str, doctor_id: str, intent_result, history: list = None) -> str:
    return await _hr_to_text(await _shared_add_record(text, doctor_id, history or [], intent_result))


async def handle_query_records(doctor_id: str, intent_result) -> str:
    return await _hr_to_text(await _shared_query_records(doctor_id, intent_result))


async def handle_all_patients(doctor_id: str) -> str:
    sync_wechat_domain_bindings()
    return await wd.handle_all_patients(doctor_id)


async def start_interview(doctor_id: str) -> str:
    sync_wechat_domain_bindings()
    return await wd.start_interview(doctor_id)


async def handle_interview_step(text: str, doctor_id: str) -> str:
    sync_wechat_domain_bindings()
    return await wd.handle_interview_step(text, doctor_id)


async def handle_pending_create(text: str, doctor_id: str) -> str:
    sync_wechat_domain_bindings()
    return await wd.handle_pending_create(text, doctor_id)


async def build_reply(content: str) -> str:
    sync_wechat_domain_bindings()
    return await wd.build_reply(content)


async def handle_menu_event(event_key: str, doctor_id: str) -> str:
    from routers import wechat as _w
    sync_wechat_domain_bindings()
    original_all = wd.handle_all_patients
    original_start = wd.start_interview
    wd.handle_all_patients = _w._handle_all_patients
    wd.start_interview = _w._start_interview
    try:
        return await wd.handle_menu_event(event_key, doctor_id)
    finally:
        wd.handle_all_patients = original_all
        wd.start_interview = original_start


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


async def route_with_fallback(text: str, doctor_id: str, history: list, knowledge_context: str):
    """Call route_message; on failure fall back to structuring or generic error."""
    try:
        from routers import wechat as _w
        return await _w.route_message(
            text, doctor_id, history or [], knowledge_context=knowledge_context, channel="wechat",
        )
    except Exception as e:
        log(f"[WeChat] agent dispatch FAILED: {e}, falling back to structuring")
        from services.observability.routing_metrics import record as _record_metric
        _record_metric("fallback:structuring")
        try:
            # Use lazy import via routers.wechat to allow test patching
            from routers import wechat as _w
            record = await _w.structure_medical_record(text)
            return wd.format_record(record)
        except ValueError:
            return "没能识别病历内容，请重新描述一下。"
        except Exception as ex:
            log(f"[WeChat] structuring fallback FAILED doctor={doctor_id}: {ex}")
            _record_metric("fallback:error")
            return "不好意思，出了点问题，能再说一遍吗？"


# ── Pending record confirmation ──────────────────────────────────────────────

async def confirm_pending_record(doctor_id: str, pending_id: str) -> str:
    """Save the pending draft to medical_records, fire follow-up tasks, clear session state."""
    from datetime import timezone as _tz, timedelta as _td
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, doctor_id)
        _now_utc = datetime.now(_tz.utc)
        if pending is not None and pending.expires_at:
            _exp_at = pending.expires_at if pending.expires_at.tzinfo is not None else pending.expires_at.replace(tzinfo=_tz.utc)
            expired = (_exp_at - _td(seconds=5)) <= _now_utc
        else:
            expired = False
        if pending is None or pending.status != "awaiting" or expired:
            clear_pending_record_id(doctor_id)
            if expired and pending is not None:
                try:
                    import json as _json
                    _draft = _json.loads(pending.draft_json or "{}")
                    _snippet = (_draft.get("content") or "")[:60]
                    _pname = pending.patient_name or "未关联患者"
                    if _snippet:
                        return f"⚠️ 草稿已过期（{_pname}：{_snippet}…）\n请重新录入病历。"
                except Exception:
                    pass
            return "⚠️ 草稿已过期\n请重新录入病历。"
    result = await wd.save_pending_record(doctor_id, pending)
    clear_pending_record_id(doctor_id)
    asyncio.create_task(audit(doctor_id, "WRITE", "pending_record", str(pending.id)))
    if result is None:
        return "⚠️ 草稿解析失败\n请重新录入。"
    patient_name, record_id = result
    import json as _json
    try:
        _draft = _json.loads(pending.draft_json)
        _cvd_raw = _draft.get("cvd_context")
        _content = _draft.get("content", "")
    except Exception:
        _cvd_raw, _content = None, ""
    from services.patient.cvd_scale_interview import build_cvd_scale_session
    cvd_sess = build_cvd_scale_session(record_id, pending.patient_id, _content, _cvd_raw)
    if cvd_sess:
        get_session(doctor_id).pending_cvd_scale = cvd_sess
        return f"✅ 病历已保存！患者：【{patient_name}】\n\n{cvd_sess.question()}"
    return f"✅ 病历已保存！患者：【{patient_name}】"


async def handle_pending_record_reply(text: str, doctor_id: str, sess) -> str:
    """Route doctor reply when a pending record draft awaits confirmation."""
    pending_id = sess.pending_record_id
    # Always re-fetch from DB — in-memory pending_record_id may be stale or expired
    async with AsyncSessionLocal() as session:
        pending = await get_pending_record(session, pending_id, doctor_id)
    if pending is None:
        clear_pending_record_id(doctor_id)
        log(f"[WeChat] pending record {pending_id} not found or expired, doctor={doctor_id}")
        from routers import wechat as _wechat_router
        _fallback = await _wechat_router._handle_intent(text, doctor_id)
        return _fallback.text
    stripped = text.strip()
    if stripped in ("撤销", "取消", "cancel", "Cancel", "不要", "放弃", "no", "No"):
        async with AsyncSessionLocal() as session:
            await abandon_pending_record(session, pending_id, doctor_id=doctor_id)
        clear_pending_record_id(doctor_id)
        asyncio.create_task(audit(doctor_id, "DELETE", "pending_record", str(pending_id)))
        return "已撤销。"
    if stripped in ("确认", "确定", "保存", "ok", "OK", "好的", "yes", "Yes"):
        return await confirm_pending_record(doctor_id, pending_id)
    # Explicit-confirmation only: abandon unconfirmed draft (UX principle 5).
    async with AsyncSessionLocal() as session:
        await abandon_pending_record(session, pending_id, doctor_id=doctor_id)
    clear_pending_record_id(doctor_id)
    _pname = pending.patient_name or "未关联患者"
    log(f"[WeChat] pending record abandoned on context switch, doctor={doctor_id} patient={_pname}")
    from routers import wechat as _wechat_router
    _new_parts = await _wechat_router._handle_intent(text, doctor_id)
    return f"⚠️ 【{_pname}】的病历草稿已放弃。\n\n{_new_parts.text}"


# ── Intent dispatch helpers ──────────────────────────────────────────────────

_HELP_TEXT = (
    "📥 导入患者（最常用）\n"
    "  直接发送 PDF / 图片 — 自动识别并创建\n"
    "  粘贴聊天记录 — 将微信问诊记录直接发过来，自动提取患者信息和病历\n"
    "  支持：出院小结、门诊病历、检验报告、问诊截图\n\n"
    "📋 患者管理\n"
    "  创建[姓名] — 创建新患者\n"
    "  查看[姓名] — 查看患者病历\n"
    "  删除[姓名] — 删除患者\n"
    "  患者列表 — 显示全部患者\n\n"
    "📝 病历\n"
    "  [描述病情] — 自动保存结构化病历\n"
    "  补充：... — 补充当前患者记录\n"
    "  刚才写错了，应该是... — 修正上一条\n\n"
    "📌 任务\n"
    "  待办任务 — 查看所有任务\n"
    "  完成 3 — 标记任务#3完成\n"
    "  3个月后随访 — 安排随访提醒\n\n"
    "📊 其他\n"
    "  开始问诊 — 开启结构化问诊流程\n"
    "  PDF:患者姓名 — 导出病历PDF"
)

_FALLBACK_TEXT = "没太理解您的意思，能说得更具体一些吗？发送「帮助」可查看完整功能列表。"


async def dispatch_intent_result(text: str, doctor_id: str, intent_result, history: list) -> WeChatReply:
    """Route an IntentResult to the appropriate domain handler."""
    from routers import wechat as _w
    i = intent_result.intent
    if i == Intent.create_patient:
        return _hr_to_parts(await _shared_create_patient(doctor_id, intent_result))
    if i == Intent.add_record:
        return await handle_add_record_intent(text, doctor_id, intent_result, history)
    if i == Intent.query_records:
        return _hr_to_parts(await _shared_query_records(doctor_id, intent_result))
    if i == Intent.list_patients:
        return _hr_to_parts(await _shared_list_patients(doctor_id))
    if i == Intent.delete_patient:
        return _hr_to_parts(await _shared_delete_patient(doctor_id, intent_result))
    if i == Intent.list_tasks:
        return _hr_to_parts(await _shared_list_tasks(doctor_id))
    if i == Intent.complete_task:
        return _hr_to_parts(await _shared_complete_task(doctor_id, intent_result))
    if i == Intent.schedule_appointment:
        return _hr_to_parts(await _shared_schedule_appointment(doctor_id, intent_result))
    if i == Intent.export_records:
        return _plain(await wd.handle_export_records(doctor_id, intent_result))
    if i == Intent.export_outpatient_report:
        return _plain(await wd.handle_export_outpatient_report(doctor_id, intent_result))
    if i == Intent.schedule_follow_up:
        return _hr_to_parts(await _shared_schedule_follow_up(doctor_id, intent_result))
    if i == Intent.cancel_task:
        return _hr_to_parts(await _shared_cancel_task(doctor_id, intent_result))
    if i == Intent.postpone_task:
        return _hr_to_parts(await _shared_postpone_task(doctor_id, intent_result))
    if i == Intent.import_history:
        return _plain(await wd.handle_import_history(text, doctor_id, intent_result))
    if i == Intent.update_record:
        return _hr_to_parts(await _shared_update_record(doctor_id, intent_result))
    if i == Intent.update_patient:
        return _hr_to_parts(await _shared_update_patient(doctor_id, intent_result))
    if i == Intent.help:
        return _plain(_HELP_TEXT)
    if i == Intent.unknown:
        return await handle_unknown_intent(text, doctor_id, intent_result, history)
    return _plain(intent_result.chat_reply or _FALLBACK_TEXT)


async def handle_add_record_intent(text: str, doctor_id: str, intent_result, history: list) -> WeChatReply:
    """Resolve patient context for add_record intent then delegate to shared handler."""
    from routers import wechat as _w
    sess = get_session(doctor_id)
    if intent_result.patient_name or sess.current_patient_id:
        return _hr_to_parts(await _shared_add_record(text, doctor_id, history or [], intent_result))
    async with AsyncSessionLocal() as db:
        patients = await get_all_patients(db, doctor_id)
    if len(patients) == 1:
        only = patients[0]
        set_current_patient(doctor_id, only.id, only.name)
        intent_result.patient_name = only.name
        log(f"[WeChat] single-patient auto-bind: {only.name} doctor={doctor_id}")
        return _hr_to_parts(await _shared_add_record(text, doctor_id, history or [], intent_result))
    candidate_name = wd.name_token_or_none(text)
    if candidate_name:
        return _plain(await _w._handle_name_lookup(candidate_name, doctor_id))
    return _plain("请问这位患者叫什么名字？")


async def handle_unknown_intent(text: str, doctor_id: str, intent_result, history: list) -> WeChatReply:
    """Handle Intent.unknown: try name lookup, symptom shortcut, then fallback."""
    from routers import wechat as _w
    explicit_name = wd.explicit_name_or_none(text)
    if explicit_name:
        looked_up = await _w._handle_name_lookup(explicit_name, doctor_id)
        if looked_up:
            return _plain(looked_up)
    sess = get_session(doctor_id)
    if sess.current_patient_id and wd.looks_like_symptom_note(text):
        synthetic = IntentResult(
            intent=Intent.add_record,
            patient_name=sess.current_patient_name,
            structured_fields={"content": text.strip()},
            chat_reply=(
                f"已记录【{sess.current_patient_name}】\n"
                f"症状：{text.strip()[:18]}\n"
                "可继续补充时长/诱因完善病历"
            ),
        )
        return _hr_to_parts(await _shared_add_record(text, doctor_id, history or [], synthetic))
    return _plain(intent_result.chat_reply or _FALLBACK_TEXT)


# ── Media background handlers ────────────────────────────────────────────────

async def handle_image_bg(media_id: str, doctor_id: str, open_kfid: str = ""):
    from routers import wechat as _w
    await wmp.handle_image_bg(
        media_id, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_image_text=extract_text_from_image,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w._handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def handle_pdf_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    from routers import wechat as _w
    await wmp.handle_pdf_file_bg(
        media_id, filename, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_pdf_text=extract_text_from_pdf,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w._handle_intent_bg(text, uid, open_kfid=open_kfid),
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
        handle_intent_bg=lambda text, uid: _w._handle_intent_bg(text, uid, open_kfid=open_kfid),
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
