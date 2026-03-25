"""WeChat flow helpers — notify control, menu events, and media background handlers."""
from __future__ import annotations

from typing import NamedTuple, Optional

from channels.wechat import wechat_media_pipeline as wmp
from channels.wechat.wechat_media_pipeline import download_media
from channels.wechat.wechat_notify import _get_config, _get_access_token, _send_customer_service_msg
from channels.wechat.infra import KB_CONTEXT_CACHE as _KB_CONTEXT_CACHE, KB_CONTEXT_TTL as _KB_CONTEXT_TTL, get_kb_lock as _get_kb_lock
from infra.llm.vision import extract_text_from_image
from domain.knowledge.pdf_extract import extract_text_from_pdf
from domain.tasks.scheduler import (
    parse_notify_command, get_notify_pref, set_notify_mode, set_notify_interval,
    set_notify_cron, set_notify_immediate, format_notify_pref,
)
from channels.wechat import wechat_domain as wd
from utils.log import log


# ── WeChatReply type ─────────────────────────────────────────────────────────

class WeChatReply(NamedTuple):
    """Structured reply carrying an optional switch notification."""
    notification: Optional[str]
    text: str


def _plain(text: str) -> WeChatReply:
    """Wrap a plain string as a WeChatReply with no notification."""
    return WeChatReply(notification=None, text=text)


# ── Menu event ───────────────────────────────────────────────────────────────

async def handle_menu_event(event_key: str, doctor_id: str) -> str:
    """Handle a WeChat menu click event."""
    return await wd.handle_menu_event(event_key, doctor_id)


# ── Notify control ───────────────────────────────────────────────────────────

async def handle_notify_control_command(doctor_id: str, text: str) -> str:
    """Parse and execute notification control commands."""
    from channels.wechat import router as _w
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


# ── Media background handlers ────────────────────────────────────────────────

async def handle_image_bg(media_id: str, doctor_id: str, open_kfid: str = ""):
    """Process an uploaded image in background."""
    from channels.wechat import router as _w
    await wmp.handle_image_bg(
        media_id, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_image_text=extract_text_from_image,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w.handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def handle_pdf_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    """Process an uploaded PDF in background."""
    from channels.wechat import router as _w
    await wmp.handle_pdf_file_bg(
        media_id, filename, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_pdf_text=extract_text_from_pdf,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w.handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def handle_word_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    """Process an uploaded Word doc in background."""
    from domain.knowledge.word_extract import extract_text_from_docx
    from channels.wechat import router as _w
    await wmp.handle_word_file_bg(
        media_id, filename, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media, extract_word_text=extract_text_from_docx,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_intent_bg=lambda text, uid: _w.handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def _handle_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    """Route an uploaded file to the appropriate handler by extension."""
    from channels.wechat import router as _w
    await wmp.handle_file_bg(
        media_id, filename, doctor_id,
        get_config=_get_config, get_access_token=_get_access_token,
        download_media=download_media,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_pdf_file_bg_fn=lambda mid, fname, uid: handle_pdf_file_bg(mid, fname, uid, open_kfid=open_kfid),
        handle_word_file_bg_fn=lambda mid, fname, uid: handle_word_file_bg(mid, fname, uid, open_kfid=open_kfid),
        log=log,
    )
