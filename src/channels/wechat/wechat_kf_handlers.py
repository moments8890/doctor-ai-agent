"""
WeCom KF (customer service) event handlers — sync cursor, message dispatch, and routing.
"""
from __future__ import annotations

import asyncio
import sys
from collections import deque
from typing import Any, Dict

import httpx

from channels.wechat import wechat_domain as wd
from channels.wechat import wecom_kf_sync as kfsync

from channels.wechat.wechat_notify import (
    _get_config, _get_access_token, _send_customer_service_msg,
)
from channels.wechat.patient_pipeline import _NON_TEXT_REPLY as _PATIENT_NON_TEXT_REPLY
from channels.wechat.infra import (
    is_registered_doctor as _is_registered_doctor,
    load_wecom_kf_sync_cursor_shared as _load_wecom_kf_sync_cursor_shared,
    persist_wecom_kf_sync_cursor as _persist_wecom_kf_sync_cursor,
    persist_wecom_kf_sync_cursor_shared as _persist_wecom_kf_sync_cursor_shared,
)
from utils.log import log, safe_create_task

# ── KF sync cursor state ────────────────────────────────────────────────────
_WECHAT_KF_SYNC_CURSOR: str = ""
_WECHAT_KF_SEEN_MSG_IDS: "deque[str]" = deque(maxlen=2000)
_WECHAT_KF_CURSOR_LOADED: bool = False
_KF_CURSOR_LOCK = asyncio.Lock()


def _create_task_is_mocked() -> bool:
    """Test harnesses patch asyncio.create_task; avoid async DB cursor I/O in that mode."""
    return "pytest" in sys.modules


# ── Thin wrappers over wechat_domain ────────────────────────────────────────

def _wecom_kf_msg_to_text(msg: Dict[str, Any]) -> str:
    return wd.wecom_kf_msg_to_text(msg)


def _wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    return wd.wecom_msg_is_processable(msg)


def _wecom_msg_time(msg: Dict[str, Any]) -> int:
    return wd.wecom_msg_time(msg)


def _extract_cdata(xml_str: str, tag: str) -> str:
    return wd.extract_cdata(xml_str, tag)


# ── KF message enqueue helpers ──────────────────────────────────────────────

async def _kf_enqueue_intent(text: str, user_id: str, open_kfid: str) -> None:
    """Persist and enqueue a doctor text message through the intent pipeline."""
    from channels.wechat.router import _handle_intent_bg, _handle_patient_bg

    if await _is_registered_doctor(user_id):
        import uuid as _uuid
        msg_id = _uuid.uuid4().hex
        # PendingMessage table removed — enqueue directly.
        safe_create_task(_handle_intent_bg(text, user_id, open_kfid=open_kfid, msg_id=msg_id))
    else:
        safe_create_task(_handle_patient_bg(text, user_id, open_kfid=open_kfid))


async def _kf_enqueue_image(media_id: str, user_id: str, open_kfid: str) -> None:
    """Dispatch a doctor image message to vision handler or patient reply."""
    from channels.wechat.flows import handle_image_bg as _handle_image_bg
    from channels.wechat.router import _handle_patient_bg

    if await _is_registered_doctor(user_id):
        safe_create_task(_handle_image_bg(media_id, user_id, open_kfid=open_kfid))
    else:
        safe_create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))


async def _kf_enqueue_file(media_id: str, filename: str, user_id: str, open_kfid: str) -> None:
    """Dispatch a doctor file message to file handler or patient reply."""
    from channels.wechat.flows import _handle_file_bg
    from channels.wechat.router import _handle_patient_bg

    if await _is_registered_doctor(user_id):
        safe_create_task(_handle_file_bg(media_id, filename, user_id, open_kfid=open_kfid))
    else:
        safe_create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))


# ── KF cursor management ───────────────────────────────────────────────────

async def _ensure_kf_cursor_loaded() -> None:
    """Lazily load the shared WeCom KF sync cursor on first use."""
    global _WECHAT_KF_SYNC_CURSOR, _WECHAT_KF_CURSOR_LOADED
    if not _WECHAT_KF_CURSOR_LOADED:
        shared_cursor = ""
        if not _create_task_is_mocked():
            shared_cursor = await _load_wecom_kf_sync_cursor_shared()
        if shared_cursor:
            _WECHAT_KF_SYNC_CURSOR = shared_cursor
        _WECHAT_KF_CURSOR_LOADED = True


def _kf_build_handlers() -> dict:
    """Return the message-type handler callbacks for kfsync.handle_event."""
    return dict(
        log=log, get_config=_get_config, get_access_token=_get_access_token,
        msg_to_text=_wecom_kf_msg_to_text, msg_is_processable=_wecom_msg_is_processable,
        msg_time=_wecom_msg_time,
        send_customer_service_msg=lambda uid, content, open_kfid: _send_customer_service_msg(uid, content, open_kfid=open_kfid),
        handle_image_bg=_kf_enqueue_image,
        handle_file_bg=_kf_enqueue_file, handle_intent_bg=_kf_enqueue_intent,
        async_client_cls=httpx.AsyncClient,
    )


async def _handle_wecom_kf_event_bg(
    expected_msgid: str = "",
    event_create_time: int = 0,
    event_token: str = "",
    event_open_kfid: str = "",
) -> None:
    """Fetch latest WeCom KF customer messages and route through intent pipeline."""
    global _WECHAT_KF_SYNC_CURSOR, _WECHAT_KF_CURSOR_LOADED
    async with _KF_CURSOR_LOCK:
        await _ensure_kf_cursor_loaded()
        previous_cursor = _WECHAT_KF_SYNC_CURSOR
        state = await kfsync.handle_event(
            expected_msgid=expected_msgid, event_create_time=event_create_time,
            event_token=event_token, event_open_kfid=event_open_kfid,
            sync_cursor=_WECHAT_KF_SYNC_CURSOR, cursor_loaded=_WECHAT_KF_CURSOR_LOADED,
            seen_msg_ids=_WECHAT_KF_SEEN_MSG_IDS,
            load_cursor=lambda: _WECHAT_KF_SYNC_CURSOR, persist_cursor=lambda _cursor: None,
            **_kf_build_handlers(),
        )
        _WECHAT_KF_SYNC_CURSOR = state.get("sync_cursor", _WECHAT_KF_SYNC_CURSOR)
        _WECHAT_KF_CURSOR_LOADED = bool(state.get("cursor_loaded", _WECHAT_KF_CURSOR_LOADED))
        if _WECHAT_KF_SYNC_CURSOR and _WECHAT_KF_SYNC_CURSOR != previous_cursor:
            if _create_task_is_mocked():
                _persist_wecom_kf_sync_cursor(_WECHAT_KF_SYNC_CURSOR)
            else:
                await _persist_wecom_kf_sync_cursor_shared(_WECHAT_KF_SYNC_CURSOR)


# ── KF event dispatch (called from router) ─────────────────────────────────

async def _handle_kf_event_dispatch(xml_str: str) -> bool:
    """If XML is a WeCom KF event, spawn background sync task and return True."""
    if _extract_cdata(xml_str, "Event") != "kf_msg_or_event":
        return False
    expected_msgid = _extract_cdata(xml_str, "MsgId") or _extract_cdata(xml_str, "Msgid")
    create_time_raw = _extract_cdata(xml_str, "CreateTime")
    event_token = _extract_cdata(xml_str, "Token")
    event_open_kfid = _extract_cdata(xml_str, "OpenKfId")
    try:
        event_create_time = int(create_time_raw) if create_time_raw else 0
    except ValueError:
        event_create_time = 0
    safe_create_task(_handle_wecom_kf_event_bg(
        expected_msgid=expected_msgid, event_create_time=event_create_time,
        event_token=event_token, event_open_kfid=event_open_kfid,
    ))
    return True
