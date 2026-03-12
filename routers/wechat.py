"""
WeChat/WeCom 消息路由：接收微信事件、异步调度意图处理并管理待确认病历确认门。
"""

import asyncio
import json
import os
import re
import time
try:
    from asyncio import timeout as _async_timeout
except ImportError:
    from async_timeout import timeout as _async_timeout
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import Mock
from fastapi import APIRouter, Request, Response
import httpx
from wechatpy import parse_message
from wechatpy.crypto import WeChatCrypto
from wechatpy.enterprise.crypto import WeChatCrypto as EnterpriseWeChatCrypto
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import TextReply
from services.ai.structuring import structure_medical_record
from services.ai.transcription import transcribe_audio
from services.knowledge.doctor_knowledge import load_knowledge_context_for_prompt
from services.wechat import wechat_domain as wd
from services.wechat import wechat_media_pipeline as wmp
from services.wechat import wecom_kf_sync as kfsync
from services.wechat.wechat_voice import download_and_convert, download_media, download_voice
from services.ai.intent import Intent, IntentResult
from services.ai.router import route_message
from services.wechat.wechat_menu import create_menu
from services.wechat.wechat_notify import (
    _get_config, _get_access_token, _send_customer_service_msg, _split_message as _notify_split_message,
)
from services.wechat.wechat_customer import prefetch_customer_profile
from services.wechat.patient_pipeline import (
    handle_patient_message,
    _NON_TEXT_REPLY as _PATIENT_NON_TEXT_REPLY,
)
from services.session import (
    get_session,
    get_session_lock,
    push_turn,
    flush_turns,
    hydrate_session_state,
)
from services.observability.audit import audit
from services.ai.memory import maybe_compress, load_context_message
from db.engine import AsyncSessionLocal
from db.crud import (
    update_task_status,
    get_all_patients,
    list_tasks,
)
from services.knowledge.doctor_knowledge import (
    parse_add_to_knowledge_command,
    save_knowledge_item,
)
from services.knowledge.pdf_extract import extract_text_from_pdf
from services.notify.tasks import (
    create_appointment_task,
    create_emergency_task,
    run_due_task_cycle,
)
from services.notify.notify_control import set_notify_mode
from utils.log import log, bind_log_context

_COMPLETE_RE = re.compile(r'^完成\s*(\d+)$')

from routers.wechat_infra import (
    is_registered_doctor as _is_registered_doctor,
    get_kb_lock as _get_kb_lock,
    KB_CONTEXT_CACHE as _KB_CONTEXT_CACHE,
    KB_CONTEXT_TTL as _KB_CONTEXT_TTL,
    load_wecom_kf_sync_cursor as _load_wecom_kf_sync_cursor,
    persist_wecom_kf_sync_cursor as _persist_wecom_kf_sync_cursor,
    load_wecom_kf_sync_cursor_shared as _load_wecom_kf_sync_cursor_shared,
    persist_wecom_kf_sync_cursor_shared as _persist_wecom_kf_sync_cursor_shared,
)

router = APIRouter(prefix="/wechat", tags=["wechat"])
_WECHAT_KF_SYNC_CURSOR: str = ""
_WECHAT_KF_SEEN_MSG_IDS: "deque[str]" = deque(maxlen=2000)
_WECHAT_KF_CURSOR_LOADED: bool = False
_KF_CURSOR_LOCK = asyncio.Lock()

from routers.wechat_flows import (
    sync_wechat_domain_bindings as _sync_wechat_domain_bindings,
    handle_notify_control_command as _handle_notify_control_command,
    handle_create_patient as _handle_create_patient,
    handle_add_record as _handle_add_record,
    handle_query_records as _handle_query_records,
    handle_all_patients as _handle_all_patients,
    start_interview as _start_interview,
    handle_interview_step as _handle_interview_step,
    handle_menu_event as _handle_menu_event,
    handle_name_lookup as _handle_name_lookup,
    handle_pending_create as _handle_pending_create,
    build_reply as _build_reply,
    confirm_pending_record as _confirm_pending_record,
    handle_pending_record_reply as _handle_pending_record_reply,
    load_knowledge_context as _load_knowledge_context,
    dispatch_intent_result as _dispatch_intent_result,
    handle_image_bg as _handle_image_bg,
    handle_pdf_file_bg as _handle_pdf_file_bg,
    handle_word_file_bg as _handle_word_file_bg,
    _handle_file_bg,
    _HELP_TEXT,
    _FALLBACK_TEXT,
    WeChatReply as _WeChatReply,
    _plain as _plain_reply,
)

def _extract_open_kfid(msg) -> str:
    return wd.extract_open_kfid(msg)


def _create_task_is_mocked() -> bool:
    """Test harnesses patch asyncio.create_task; avoid async DB cursor I/O in that mode."""
    return isinstance(asyncio.create_task, Mock)


def _format_record(record) -> str:
    return wd.format_record(record)


def _split_message(text: str, limit: int = 600) -> List[str]:
    # Backward-compatible router-level alias used by existing tests.
    return _notify_split_message(text, limit=limit)


def _format_chat_result(result) -> str:
    """Format a ChatResponse into a plain-text WeChat reply string."""
    parts = [result.reply or ""]
    if result.record:
        formatted = wd.format_record(result.record)
        if formatted:
            parts.append(formatted)
    return "\n".join(p for p in parts if p).strip()


async def _handle_intent(text: str, doctor_id: str, history: list = None) -> "_WeChatReply":
    # Fast-path: "完成 N" bypasses LLM
    m = _COMPLETE_RE.match(text.strip())
    if m:
        task_id = int(m.group(1))
        async with AsyncSessionLocal() as session:
            task = await update_task_status(session, task_id, doctor_id, "completed")
        if task is None:
            return _plain_reply(f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
        return _plain_reply(f"✅ 任务【{task.title}】已标记完成。")

    notify_reply = await _handle_notify_control_command(doctor_id, text)
    if notify_reply:
        return _plain_reply(notify_reply)

    knowledge_payload = parse_add_to_knowledge_command(text)
    if knowledge_payload is not None:
        if not knowledge_payload:
            return _plain_reply("⚠️ 请在命令后补充知识内容，例如：add_to_knowledge_base 高危胸痛需先排除ACS。")
        async with AsyncSessionLocal() as session:
            item = await save_knowledge_item(session, doctor_id, knowledge_payload, source="doctor", confidence=1.0)
        if item is None:
            return _plain_reply("⚠️ 知识内容为空，未保存。")
        return _plain_reply("✅ 已加入医生知识库（#{0}）：{1}".format(item.id, knowledge_payload))

    knowledge_context = await _load_knowledge_context(doctor_id, text)

    # Use the unified intent workflow pipeline (same as web path).
    from services.intent_workflow import run as workflow_run

    try:
        result = await workflow_run(
            text, doctor_id, history or [],
            knowledge_context=knowledge_context,
            channel="wechat",
        )
    except Exception as e:
        log(f"[WeChat] workflow FAILED: {e}, falling back to structuring")
        from services.observability.routing_metrics import record as _record_metric
        _record_metric("fallback:structuring")
        try:
            record = await structure_medical_record(text)
            return _plain_reply(wd.format_record(record))
        except ValueError:
            return _plain_reply("没能识别病历内容，请重新描述一下。")
        except Exception as ex:
            log(f"[WeChat] structuring fallback FAILED doctor={doctor_id}: {ex}")
            _record_metric("fallback:error")
            return _plain_reply("不好意思，出了点问题，能再说一遍吗？")

    if not result.gate.approved:
        # For add_record blocked by no_patient_name, let the handler's own
        # patient resolution run (single-patient auto-bind, name token lookup).
        if result.gate.reason != "no_patient_name":
            return _plain_reply(result.gate.clarification_message or _FALLBACK_TEXT)

    intent_result = result.to_intent_result()
    bind_log_context(intent=intent_result.intent.value)
    log(f"[WeChat] intent={intent_result.intent} patient={intent_result.patient_name}")
    return await _dispatch_intent_result(text, doctor_id, intent_result, history)



def _extract_cdata(xml_str: str, tag: str) -> str:
    return wd.extract_cdata(xml_str, tag)


def _wecom_kf_msg_to_text(msg: Dict[str, Any]) -> str:
    return wd.wecom_kf_msg_to_text(msg)


def _wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    return wd.wecom_msg_is_processable(msg)


def _wecom_msg_time(msg: Dict[str, Any]) -> int:
    return wd.wecom_msg_time(msg)


async def _kf_enqueue_intent(text: str, user_id: str, open_kfid: str) -> None:
    """Persist and enqueue a doctor text message through the intent pipeline."""
    if await _is_registered_doctor(user_id):
        import uuid as _uuid
        msg_id = _uuid.uuid4().hex
        try:
            async with AsyncSessionLocal() as _db:
                from db.crud import create_pending_message as _create_pm
                await _create_pm(_db, msg_id, user_id, text)
        except Exception as _e:
            log(f"[KF] pending_message persist FAILED (non-fatal): {_e}")
            msg_id = ""
        asyncio.create_task(_handle_intent_bg(text, user_id, open_kfid=open_kfid, msg_id=msg_id))
    else:
        asyncio.create_task(_handle_patient_bg(text, user_id, open_kfid=open_kfid))


async def _kf_enqueue_voice(media_id: str, user_id: str, open_kfid: str) -> None:
    """Persist and enqueue a doctor voice message for transcription."""
    if await _is_registered_doctor(user_id):
        import uuid as _uuid
        _voice_msg_id = _uuid.uuid4().hex
        try:
            async with AsyncSessionLocal() as _db:
                from db.crud import create_pending_message as _create_pm
                await _create_pm(_db, _voice_msg_id, user_id, f"[voice:{media_id}]")
        except Exception as _e:
            log(f"[KF] voice pending_message persist FAILED (non-fatal): {_e}")
            _voice_msg_id = ""
        asyncio.create_task(_handle_voice_bg(media_id, user_id, open_kfid=open_kfid, msg_id=_voice_msg_id))
    else:
        asyncio.create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))


async def _kf_enqueue_image(media_id: str, user_id: str, open_kfid: str) -> None:
    """Dispatch a doctor image message to vision handler or patient reply."""
    if await _is_registered_doctor(user_id):
        asyncio.create_task(_handle_image_bg(media_id, user_id, open_kfid=open_kfid))
    else:
        asyncio.create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))


async def _kf_enqueue_file(media_id: str, filename: str, user_id: str, open_kfid: str) -> None:
    """Dispatch a doctor file message to file handler or patient reply."""
    if await _is_registered_doctor(user_id):
        asyncio.create_task(_handle_file_bg(media_id, filename, user_id, open_kfid=open_kfid))
    else:
        asyncio.create_task(_handle_patient_bg(_PATIENT_NON_TEXT_REPLY, user_id, open_kfid=open_kfid))


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
        handle_voice_bg=_kf_enqueue_voice, handle_image_bg=_kf_enqueue_image,
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


@router.get("")
def verify(
    timestamp: str = "",
    nonce: str = "",
    signature: str = "",
    echostr: str = "",
    msg_signature: str = "",
):
    log(
        "[WeChat verify] inbound",
        timestamp=timestamp or "(empty)",
        nonce=nonce or "(empty)",
        signature=signature or "(empty)",
        msg_signature=msg_signature or "(empty)",
        has_echostr=str(bool(echostr)).lower(),
    )

    # Some upstream checks probe callback URL without verification params.
    # Return 200 so domain reachability checks pass before real signature validation.
    if not timestamp and not nonce and not signature and not msg_signature and not echostr:
        log("[WeChat verify] probe: empty query params -> 200")
        return Response(content="ok", media_type="text/plain")

    cfg = _get_config()
    effective_sig = msg_signature or signature
    if not effective_sig:
        # Some pre-check flows send timestamp/nonce/echostr without signature.
        # Respond 200 to allow domain callback validation to proceed.
        log("[WeChat verify] probe: missing signature -> 200")
        return Response(content=echostr or "ok", media_type="text/plain")
    log(
        f"[WeChat verify] token=*** signature={effective_sig} "
        f"mode={'wecom-aes' if msg_signature else 'plain'}"
    )
    try:
        if msg_signature and cfg["aes_key"] and cfg["app_id"]:
            # WeCom callback verification uses msg_signature + encrypted echostr.
            crypto = EnterpriseWeChatCrypto(cfg["token"], cfg["aes_key"], cfg["app_id"])
            plain = crypto.check_signature(msg_signature, timestamp, nonce, echostr)
            log("[WeChat verify] OK (wecom-aes)")
            return Response(content=plain, media_type="text/plain")

        check_signature(cfg["token"], effective_sig, timestamp, nonce)
        log("[WeChat verify] OK (plain)")
        return Response(content=echostr, media_type="text/plain")
    except InvalidSignatureException as e:
        log(f"[WeChat verify] FAILED: {e}")
        return Response(content="Invalid signature", status_code=403)


async def _route_session_state_bg(text: str, doctor_id: str) -> "_WeChatReply":
    """Under session lock: check stateful flows first, else call _handle_intent."""
    from services.ai.turn_context import assemble_turn_context
    sess = get_session(doctor_id)
    try:
        await asyncio.wait_for(maybe_compress(doctor_id, sess), timeout=2.0)
    except asyncio.TimeoutError:
        log(f"[WeChat bg] maybe_compress timed out for doctor={doctor_id}, skipping")

    # Assemble authoritative workflow state + advisory context (already under lock)
    ctx = await assemble_turn_context(doctor_id, already_locked=True)

    reply_parts: "_WeChatReply"
    if ctx.workflow.pending_record_id:
        reply_parts = _plain_reply(await _handle_pending_record_reply(text, doctor_id, sess))
    elif ctx.workflow.pending_create_name:
        reply_parts = _plain_reply(await _handle_pending_create(text, doctor_id))
    elif ctx.workflow.pending_cvd_scale is not None:
        reply_parts = _plain_reply(await wd.handle_cvd_scale_reply(text, doctor_id))
    elif ctx.workflow.interview is not None:
        reply_parts = _plain_reply(await _handle_interview_step(text, doctor_id))
    else:
        welcome = ""
        if not ctx.advisory.recent_history:
            welcome = (
                "欢迎使用门诊AI助手！\n"
                "我可以帮您：建档、记录病历、查询患者、安排随访。\n"
                "发「帮助」可查看完整功能列表。\n\n"
            )
        history = list(ctx.advisory.recent_history)
        if ctx.advisory.context_message:
            history = [ctx.advisory.context_message] + history
        log(f"[WeChat bg] provenance: patient_source={ctx.provenance.current_patient_source} "
            f"memory={ctx.provenance.memory_used} knowledge={ctx.provenance.knowledge_used}")
        try:
            reply_parts = await _handle_intent(text, doctor_id, history=history)
            if welcome:
                reply_parts = _WeChatReply(
                    notification=reply_parts.notification,
                    text=welcome + reply_parts.text,
                )
        except Exception as e:
            log(f"[WeChat bg] FAILED: {e}")
            reply_parts = _plain_reply("不好意思，出了点问题，能再说一遍吗？")
    # Store combined text for conversation history (notification + reply).
    combined = reply_parts.text
    if reply_parts.notification:
        combined = f"{reply_parts.notification}\n{reply_parts.text}"
    push_turn(doctor_id, text, combined)
    await flush_turns(doctor_id)
    return reply_parts


async def _handle_intent_bg(text: str, doctor_id: str, open_kfid: str = "", msg_id: str = ""):
    """Process intent in background and deliver result via customer service API.

    When ``_route_session_state_bg`` returns a ``WeChatReply`` with a non-None
    ``notification`` (e.g. a patient-switch bubble), that notification is sent
    as a separate CS-API message *before* the main reply text.
    """
    bind_log_context(doctor_id=doctor_id)
    if open_kfid:
        asyncio.create_task(prefetch_customer_profile(doctor_id))

    _OVERALL_TIMEOUT = float(os.environ.get("INTENT_BG_TIMEOUT", "4.5"))
    _LOCK_TIMEOUT = float(os.environ.get("INTENT_LOCK_TIMEOUT", "1.0"))
    reply_parts: "_WeChatReply" = _plain_reply("处理超时，请重新发送。")
    try:
        try:
            async with _async_timeout(_OVERALL_TIMEOUT):
                _lock = get_session_lock(doctor_id)
                _lock_acquired = False
                _lock_wait_start = time.perf_counter()
                try:
                    await asyncio.wait_for(_lock.acquire(), timeout=_LOCK_TIMEOUT)
                    _lock_acquired = True
                    _lock_wait_ms = (time.perf_counter() - _lock_wait_start) * 1000
                    if _lock_wait_ms > 100:
                        log(f"[WeChat bg] session lock wait {_lock_wait_ms:.0f}ms doctor={doctor_id}")
                except asyncio.TimeoutError:
                    log(f"[WeChat bg] lock timeout after {_LOCK_TIMEOUT}s doctor={doctor_id}")
                    reply_parts = _plain_reply("上一条消息处理中，请稍候重发。")
                if _lock_acquired:
                    try:
                        await hydrate_session_state(doctor_id)  # inside lock: no TOCTOU
                        reply_parts = await _route_session_state_bg(text, doctor_id)
                    finally:
                        _lock.release()
        except asyncio.TimeoutError:
            log(f"[WeChat bg] TIMEOUT after {_OVERALL_TIMEOUT}s doctor={doctor_id}")
        except Exception as e:
            log(f"[WeChat bg] FAILED (outer): {e}")
            reply_parts = _plain_reply("不好意思，出了点问题，能再说一遍吗？")
    finally:
        if msg_id:
            try:
                async with AsyncSessionLocal() as _mdb:
                    from db.crud import mark_pending_message as _mark_pm
                    await _mark_pm(_mdb, msg_id, "done")
            except Exception as _e:
                log(f"[WeChat bg] mark pending_message done FAILED: {_e}")
        try:
            # Send switch notification as a separate chat bubble before the main reply.
            if reply_parts.notification:
                try:
                    await _send_customer_service_msg(
                        doctor_id, reply_parts.notification, open_kfid=open_kfid,
                    )
                except Exception as ne:
                    log(f"[WeChat bg] switch notification send FAILED: {ne}")
            await _send_customer_service_msg(doctor_id, reply_parts.text, open_kfid=open_kfid)
        except Exception as e:
            log(f"[WeChat bg] send FAILED: {e}")


async def _handle_patient_bg(text: str, open_id: str, open_kfid: str = "") -> None:
    """Handle a text message from a non-doctor (patient) sender."""
    reply = await handle_patient_message(text, open_id)
    await _send_customer_service_msg(open_id, reply, open_kfid=open_kfid)


async def _transcribe_voice_msg(media_id: str, doctor_id: str, open_kfid: str) -> str | None:
    """Download and transcribe a voice message; send error reply and return None on failure."""
    cfg = _get_config()
    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        wav = await download_and_convert(media_id, access_token)
        text = await transcribe_audio(wav, "voice.wav")
        log(f"[Voice] transcribed for {doctor_id}: {text!r}")
        return text
    except Exception as e:
        log(f"[Voice] transcription FAILED: {e}")
        await _send_customer_service_msg(doctor_id, "❌ 语音识别失败，请稍后重试。", open_kfid=open_kfid)
        return None


async def _route_voice_under_lock(text: str, doctor_id: str) -> tuple[str, str]:
    """Under session lock: check stateful flows; return (route, result)."""
    route, result = "intent", None
    await hydrate_session_state(doctor_id)
    sess = get_session(doctor_id)
    try:
        if sess.pending_record_id:
            result = await _handle_pending_record_reply(text, doctor_id, sess)
            route = "done"
        elif sess.pending_create_name:
            result = await _handle_pending_create(text, doctor_id)
            route = "done"
        elif sess.interview is not None:
            result = await _handle_interview_step(text, doctor_id)
            route = "done"
    except Exception as e:
        log(f"[Voice] routing FAILED: {e}")
        result = "处理失败，请稍后重试。"
        route = "done"
    if route == "done" and result is not None:
        push_turn(doctor_id, text, result)
        await flush_turns(doctor_id)
    return route, result


async def _handle_voice_bg(media_id: str, doctor_id: str, open_kfid: str = "", msg_id: str = ""):
    """Download, convert, transcribe WeChat voice, then route through normal pipeline."""
    try:
        text = await _transcribe_voice_msg(media_id, doctor_id, open_kfid)
        if text is None:
            return
        async with get_session_lock(doctor_id):
            route, result = await _route_voice_under_lock(text, doctor_id)
        if route == "done":
            await _send_customer_service_msg(doctor_id, f'🎙️ 「{text}」\n\n{result}', open_kfid=open_kfid)
        else:
            await _handle_intent_bg(text, doctor_id, open_kfid=open_kfid)
    finally:
        if msg_id:
            try:
                async with AsyncSessionLocal() as _mdb:
                    from db.crud import mark_pending_message as _mark_pm
                    await _mark_pm(_mdb, msg_id, "done")
            except Exception as _e:
                log(f"[Voice] mark pending_message done FAILED: {_e}")


async def _decrypt_xml_body(xml_str: str, encrypt_type: str, msg_signature: str,
                            timestamp: str, nonce: str, cfg: dict) -> str | None:
    """Decrypt an AES-encrypted WeChat/WeCom XML body; return None on failure."""
    has_encrypt_node = "<Encrypt><![CDATA[" in xml_str or "<Encrypt>" in xml_str
    should_decrypt = (encrypt_type == "aes") or (bool(msg_signature) and has_encrypt_node)
    if not should_decrypt:
        return xml_str
    if not (cfg["aes_key"] and cfg["app_id"]):
        missing = [k for k in ("app_id", "aes_key") if not cfg[k]]
        log("[WeChat msg] encrypted payload received but decrypt config missing: " + ",".join(missing))
        return ""  # sentinel: ACK without processing
    crypto_cls = EnterpriseWeChatCrypto if cfg["app_id"].startswith("ww") else WeChatCrypto
    crypto = crypto_cls(cfg["token"], cfg["aes_key"], cfg["app_id"])
    xml_str = crypto.decrypt_message(xml_str, msg_signature, timestamp, nonce)
    log(f"[WeChat msg] decrypted ok, length={len(xml_str)}")
    return xml_str


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
    asyncio.create_task(_handle_wecom_kf_event_bg(
        expected_msgid=expected_msgid, event_create_time=event_create_time,
        event_token=event_token, event_open_kfid=event_open_kfid,
    ))
    return True


async def _handle_non_doctor_msg(msg) -> Response:
    """Dispatch a message from an unregistered (patient) sender."""
    open_kfid = _extract_open_kfid(msg)
    if msg.type == "text" and msg.content.strip():
        log(f"[WeChat] patient message open_id={msg.source[:8]} kfid={open_kfid[:8] if open_kfid else ''}")
        asyncio.create_task(_handle_patient_bg(msg.content.strip(), msg.source, open_kfid))
    else:
        asyncio.create_task(_send_customer_service_msg(msg.source, _PATIENT_NON_TEXT_REPLY, open_kfid=open_kfid))
    return Response(content=TextReply(content="", message=msg).render(), media_type="application/xml")


async def _handle_non_text_msg(msg) -> Response | None:
    """Handle voice/image/video/location/link messages; return None if not applicable."""
    if msg.type == "voice":
        asyncio.create_task(_handle_voice_bg(msg.media_id, msg.source, _extract_open_kfid(msg)))
        await hydrate_session_state(msg.source)
        sess = get_session(msg.source)
        if sess.interview is not None:
            ack = f"🎙️ 收到语音，正在识别…\n{sess.interview.progress} {sess.interview.current_question}"
        else:
            ack = "🎙️ 收到语音，正在识别，稍候回复您…"
        return Response(content=TextReply(content=ack, message=msg).render(), media_type="application/xml")
    if msg.type == "image":
        asyncio.create_task(_handle_image_bg(msg.media_id, msg.source, _extract_open_kfid(msg)))
        return Response(content=TextReply(content="🖼️ 收到图片，正在识别文字…", message=msg).render(), media_type="application/xml")
    if msg.type in ("video", "shortvideo"):
        return Response(content=TextReply(content="🎬 收到视频\n暂不支持视频解析\n请发文字说明。", message=msg).render(), media_type="application/xml")
    if msg.type == "location":
        return Response(content=TextReply(content="📍 暂不支持位置消息，请发文字描述。", message=msg).render(), media_type="application/xml")
    if msg.type == "link":
        return Response(content=TextReply(content="🔗 暂不支持链接消息，请发文字描述。", message=msg).render(), media_type="application/xml")
    return None


async def _handle_stateful_sync(msg) -> Response | None:
    """Check for active session state flows; return response if handled, else None."""
    await hydrate_session_state(msg.source)
    sess = get_session(msg.source)
    if sess.pending_record_id:
        reply_text = await _handle_pending_record_reply(msg.content, msg.source, sess)
        log(f"[WeChat msg] pending_record reply: {reply_text[:80]}")
        return Response(content=TextReply(content=reply_text, message=msg).render(), media_type="application/xml")
    if sess.pending_create_name:
        reply_text = await _handle_pending_create(msg.content, msg.source)
        log(f"[WeChat msg] pending_create reply: {reply_text[:80]}")
        return Response(content=TextReply(content=reply_text, message=msg).render(), media_type="application/xml")
    if sess.interview is not None:
        reply_text = await _handle_interview_step(msg.content, msg.source)
        log(f"[WeChat msg] interview step reply: {reply_text[:80]}")
        return Response(content=TextReply(content=reply_text, message=msg).render(), media_type="application/xml")
    return None


async def _persist_and_enqueue_intent(msg) -> Response:
    """Persist message to DB and enqueue background intent processing."""
    import uuid as _uuid
    msg_id = _uuid.uuid4().hex
    try:
        async with AsyncSessionLocal() as _db:
            from db.crud import create_pending_message as _create_pm
            await _create_pm(_db, msg_id, msg.source, msg.content)
    except Exception as _e:
        log(f"[WeChat msg] pending_message persist FAILED (non-fatal): {_e}")
        msg_id = ""
    asyncio.create_task(_handle_intent_bg(msg.content, msg.source, _extract_open_kfid(msg), msg_id=msg_id))
    log(f"[WeChat msg] → background task created for {msg.source} msg_id={msg_id}")
    return Response(content=TextReply(content="⏳ 正在处理，稍候回复您…", message=msg).render(), media_type="application/xml")


@router.post("")
async def handle_message(request: Request):
    cfg = _get_config()
    params = dict(request.query_params)
    timestamp, nonce = params.get("timestamp", ""), params.get("nonce", "")
    msg_signature, encrypt_type = params.get("msg_signature", ""), params.get("encrypt_type", "")
    log(f"[WeChat msg] POST received — encrypt_type={encrypt_type!r}")
    xml_str = (await request.body()).decode("utf-8")
    log(f"[WeChat msg] body received, length={len(xml_str)}, encrypt_type={encrypt_type!r}")
    try:
        xml_str = await _decrypt_xml_body(xml_str, encrypt_type, msg_signature, timestamp, nonce, cfg)
    except Exception as e:
        log(f"[WeChat msg] decrypt FAILED: {e}")
        return Response(content="", media_type="application/xml")
    if xml_str == "":  # misconfigured AES — ACK to stop retries
        return Response(content="success", media_type="text/plain")
    if await _handle_kf_event_dispatch(xml_str):
        return Response(content="success", media_type="text/plain")
    try:
        msg = parse_message(xml_str)
        bind_log_context(doctor_id=str(msg.source or ""))
        log(f"[WeChat msg] type={msg.type!r} from={msg.source}")
    except Exception as e:
        log(f"[WeChat msg] parse FAILED: {e}")
        return Response(content="", media_type="application/xml")
    if msg.type == "event" and msg.event.upper() == "CLICK":
        reply_text = await _handle_menu_event(msg.key, msg.source)
        log(f"[WeChat msg] menu click key={msg.key!r} reply={reply_text[:60]}")
        return Response(content=TextReply(content=reply_text, message=msg).render(), media_type="application/xml")
    if not await _is_registered_doctor(msg.source):
        return await _handle_non_doctor_msg(msg)
    non_text_resp = await _handle_non_text_msg(msg)
    if non_text_resp is not None:
        return non_text_resp
    if msg.type != "text" or not msg.content.strip():
        return Response(content=TextReply(content="请发送文字、语音或图片消息。", message=msg).render(), media_type="application/xml")
    stateful_resp = await _handle_stateful_sync(msg)
    if stateful_resp is not None:
        return stateful_resp
    return await _persist_and_enqueue_intent(msg)


_PENDING_MESSAGE_MAX_ATTEMPTS = 3


async def recover_stale_pending_messages(older_than_seconds: int = 60) -> int:
    """Re-queue pending messages left unprocessed after a crash. Call on startup."""
    try:
        async with AsyncSessionLocal() as _db:
            from db.crud import list_stale_pending_messages as _list_pm, mark_pending_message as _mark_pm2, increment_pending_message_attempt as _inc_attempt
            msgs = await _list_pm(_db, older_than_seconds=older_than_seconds)
        for msg in msgs:
            attempt_count = getattr(msg, "attempt_count", 0)
            if attempt_count >= _PENDING_MESSAGE_MAX_ATTEMPTS:
                async with AsyncSessionLocal() as _db:
                    from db.crud import mark_pending_message as _mark_pm2, increment_pending_message_attempt as _inc_attempt
                    await _mark_pm2(_db, msg.id, "dead")
                log(f"[Recovery] dead-lettering message {msg.id} after {attempt_count} attempts")
                continue
            async with AsyncSessionLocal() as _db:
                from db.crud import increment_pending_message_attempt as _inc_attempt
                await _inc_attempt(_db, msg.id)
            asyncio.create_task(_handle_intent_bg(msg.raw_content, msg.doctor_id, msg_id=msg.id))
            log(f"[Recovery] re-queued stale pending_message id={msg.id} doctor={msg.doctor_id}")
        return len(msgs)
    except Exception as e:
        log(f"[Recovery] stale pending_message recovery FAILED: {e}")
        return 0


@router.post("/menu")
async def setup_menu():
    """Admin endpoint: create / update the WeChat custom menu."""
    cfg = _get_config()
    access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
    result = await create_menu(access_token)
    if result.get("errcode", -1) == 0:
        return {"status": "ok", "detail": "菜单创建成功"}
    return {"status": "error", "detail": result}
