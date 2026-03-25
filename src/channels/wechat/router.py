"""
WeChat/WeCom 消息路由：接收微信事件、异步调度意图处理并管理待确认病历确认门。
"""
from __future__ import annotations

import asyncio
import os
import re
try:
    from asyncio import timeout as _async_timeout
except ImportError:
    from async_timeout import timeout as _async_timeout
import sys
from fastapi import APIRouter, Header, Request, Response
from wechatpy import parse_message
from wechatpy.crypto import WeChatCrypto
from wechatpy.enterprise.crypto import WeChatCrypto as EnterpriseWeChatCrypto
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import TextReply
from channels.wechat import wechat_domain as wd
from channels.wechat.wechat_menu import create_menu
from channels.wechat.wechat_notify import (
    _get_config, _get_access_token, _send_customer_service_msg,
)
from channels.wechat.wechat_customer import prefetch_customer_profile
from channels.wechat.patient_pipeline import (
    _NON_TEXT_REPLY as _PATIENT_NON_TEXT_REPLY,
)
from db.engine import AsyncSessionLocal
from db.crud import update_task_status
from domain.knowledge.doctor_knowledge import (
    parse_add_to_knowledge_command,
    save_knowledge_item,
)
from utils.log import log, bind_log_context, safe_create_task

_COMPLETE_RE = re.compile(r'^\s*完成\s*(\d+)\s*$')

from channels.wechat.infra import (
    is_registered_doctor as _is_registered_doctor,
)

router = APIRouter(prefix="/wechat", tags=["wechat"])

# ── KF handlers: delegate to wechat_kf_handlers ──────────────────────────────
import channels.wechat.wechat_kf_handlers as _kf_mod  # noqa: E402
_handle_wecom_kf_event_bg = _kf_mod._handle_wecom_kf_event_bg
_handle_kf_event_dispatch = _kf_mod._handle_kf_event_dispatch
# KF state lives in _kf_mod; __getattr__/__setattr__ proxy for test compat.
_KF_STATE_NAMES = frozenset({"_WECHAT_KF_SYNC_CURSOR", "_WECHAT_KF_SEEN_MSG_IDS",
                              "_WECHAT_KF_CURSOR_LOADED", "_KF_CURSOR_LOCK"})
def __getattr__(name: str):  # noqa: E302
    if name in _KF_STATE_NAMES:
        return getattr(_kf_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
class _ProxyModule(type(sys.modules[__name__])):  # noqa: E302
    def __setattr__(self, name, value):
        if name in _KF_STATE_NAMES:
            setattr(_kf_mod, name, value); return  # noqa: E702
        super().__setattr__(name, value)
sys.modules[__name__].__class__ = _ProxyModule

from channels.wechat.flows import (
    handle_notify_control_command as _handle_notify_control_command,
    handle_menu_event as _handle_menu_event,
    handle_image_bg as _handle_image_bg,
    WeChatReply as _WeChatReply,
    _plain as _plain_reply,
)

def _extract_open_kfid(msg) -> str:
    return wd.extract_open_kfid(msg)



async def _handle_intent(
    text: str, doctor_id: str, history: list = None, *,
    turn_context=None, knowledge_context: str = "",
) -> "_WeChatReply":
    """Route doctor text through the Plan-and-Act agent."""
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

    from agent import handle_turn
    result = await handle_turn(text, "doctor", doctor_id)
    return _plain_reply(result.reply)


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
    """Route doctor text through Plan-and-Act agent."""
    try:
        reply_parts = await _handle_intent(text, doctor_id)
    except TimeoutError:
        log(f"[WeChat bg] timeout doctor={doctor_id} len={len(text)}")
        reply_parts = _plain_reply("处理超时，请重新发送。")
    except ConnectionError as e:
        log(f"[WeChat bg] connection error doctor={doctor_id}: {e}")
        reply_parts = _plain_reply("服务暂时不可用，请稍后重试。")
    except Exception as e:
        log(f"[WeChat bg] FAILED ({type(e).__name__}) doctor={doctor_id}: {e}")
        reply_parts = _plain_reply("不好意思，出了点问题，能再说一遍吗？")
    return reply_parts


async def _handle_intent_bg(text: str, doctor_id: str, open_kfid: str = "", msg_id: str = ""):
    """Process intent in background and deliver result via customer service API.

    When ``_route_session_state_bg`` returns a ``WeChatReply`` with a non-None
    ``notification`` (e.g. a patient-switch bubble), that notification is sent
    as a separate CS-API message *before* the main reply text.
    """
    bind_log_context(doctor_id=doctor_id)
    if open_kfid:
        safe_create_task(prefetch_customer_profile(doctor_id))

    _OVERALL_TIMEOUT = float(os.environ.get("INTENT_BG_TIMEOUT", "4.5"))
    reply_parts: "_WeChatReply" = _plain_reply("处理超时，请重新发送。")
    _processed = False
    try:
        try:
            async with _async_timeout(_OVERALL_TIMEOUT):
                reply_parts = await _route_session_state_bg(text, doctor_id)
                _processed = True
        except asyncio.TimeoutError:
            log(f"[WeChat bg] TIMEOUT after {_OVERALL_TIMEOUT}s doctor={doctor_id}")
        except Exception as e:
            log(f"[WeChat bg] FAILED ({type(e).__name__}): {e}", level="error", exc_info=True)
            reply_parts = _plain_reply("不好意思，出了点问题，能再说一遍吗？")
    finally:
        _send_ok = False
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
            _send_ok = True
        except Exception as e:
            log(f"[WeChat bg] send FAILED: {e}")
        # Pending message tracking removed (killed PendingMessage table).


async def _handle_patient_bg(text: str, open_id: str, open_kfid: str = "") -> None:
    """Handle a text message from a non-doctor (patient) sender via ReAct agent."""
    try:
        from channels.wechat.patient_pipeline import has_emergency_keyword, _EMERGENCY_REPLY
        if has_emergency_keyword(text):
            await _send_customer_service_msg(open_id, _EMERGENCY_REPLY, open_kfid=open_kfid)
            return
        from agent.handle_turn import handle_turn
        result = await handle_turn(text, "patient", open_id)
        await _send_customer_service_msg(open_id, result.reply, open_kfid=open_kfid)
    except Exception as e:
        log(f"[WeChat patient] FAILED open_id={open_id}: {e}")


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


async def _handle_non_doctor_msg(msg) -> Response:
    """Dispatch a message from an unregistered (patient) sender."""
    open_kfid = _extract_open_kfid(msg)
    if msg.type == "text" and msg.content.strip():
        log(f"[WeChat] patient message open_id={msg.source[:8]} kfid={open_kfid[:8] if open_kfid else ''}")
        safe_create_task(_handle_patient_bg(msg.content.strip(), msg.source, open_kfid))
    else:
        safe_create_task(_send_customer_service_msg(msg.source, _PATIENT_NON_TEXT_REPLY, open_kfid=open_kfid))
    return Response(content=TextReply(content="", message=msg).render(), media_type="application/xml")


async def _handle_non_text_msg(msg) -> Response | None:
    """Handle image/video/location/link messages; return None if not applicable."""
    if msg.type == "voice":
        return Response(content=TextReply(content="暂不支持语音消息，请发送文字或图片。", message=msg).render(), media_type="application/xml")
    if msg.type == "image":
        safe_create_task(_handle_image_bg(msg.media_id, msg.source, _extract_open_kfid(msg)))
        return Response(content=TextReply(content="🖼️ 收到图片，正在识别文字…", message=msg).render(), media_type="application/xml")
    if msg.type in ("video", "shortvideo"):
        return Response(content=TextReply(content="🎬 收到视频\n暂不支持视频解析\n请发文字说明。", message=msg).render(), media_type="application/xml")
    if msg.type == "location":
        return Response(content=TextReply(content="📍 暂不支持位置消息，请发文字描述。", message=msg).render(), media_type="application/xml")
    if msg.type == "link":
        return Response(content=TextReply(content="🔗 暂不支持链接消息，请发文字描述。", message=msg).render(), media_type="application/xml")
    return None


async def _handle_stateful_sync(msg) -> Response | None:
    """Handle stateful messages synchronously.

    In the Plan-and-Act architecture, confirm/abandon routing is handled by
    the routing LLM — no regex fast path needed. This function now always
    returns None so all messages fall through to background processing.
    """
    return None


async def _persist_and_enqueue_intent(msg) -> Response:
    """Persist message to DB and enqueue background intent processing."""
    import uuid as _uuid
    msg_id = _uuid.uuid4().hex
    # PendingMessage table removed — enqueue directly without persisting.
    safe_create_task(_handle_intent_bg(msg.content, msg.source, _extract_open_kfid(msg), msg_id=msg_id))
    log(f"[WeChat msg] → background task created for {msg.source} msg_id={msg_id}")
    return Response(content=TextReply(content="⏳ 正在处理，稍候回复您…", message=msg).render(), media_type="application/xml")


@router.post("")
async def handle_message(request: Request):
    cfg = _get_config()
    params = dict(request.query_params)
    signature = params.get("signature", "")
    timestamp, nonce = params.get("timestamp", ""), params.get("nonce", "")
    msg_signature, encrypt_type = params.get("msg_signature", ""), params.get("encrypt_type", "")
    log(f"[WeChat msg] POST received — encrypt_type={encrypt_type!r}")

    # ── Signature verification ────────────────────────────────────────────
    # Encrypted messages (AES mode) are verified inside decrypt_message().
    # Plain-text messages must be verified here using the `signature` param
    # that WeChat sends on every POST — without this check, anyone can POST
    # fabricated XML and impersonate a doctor.
    is_encrypted = (encrypt_type == "aes") or bool(msg_signature)
    if not is_encrypted:
        effective_sig = signature
        if not effective_sig:
            log("[WeChat msg] REJECTED: missing signature on plain-text POST")
            return Response(content="", status_code=403, media_type="text/plain")
        try:
            check_signature(cfg["token"], effective_sig, timestamp, nonce)
        except InvalidSignatureException:
            log("[WeChat msg] REJECTED: invalid signature on plain-text POST")
            return Response(content="", status_code=403, media_type="text/plain")

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
        log(f"[WeChat msg] menu click key={msg.key!r} reply_len={len(reply_text)}")
        return Response(content=TextReply(content=reply_text, message=msg).render(), media_type="application/xml")
    if not await _is_registered_doctor(msg.source):
        return await _handle_non_doctor_msg(msg)
    non_text_resp = await _handle_non_text_msg(msg)
    if non_text_resp is not None:
        return non_text_resp
    if msg.type != "text" or not msg.content.strip():
        return Response(content=TextReply(content="请发送文字、语音或图片消息。", message=msg).render(), media_type="application/xml")
    # Truncate excessively long messages to prevent LLM cost amplification
    if len(msg.content) > 8000:
        log(f"[WeChat msg] truncating oversized message ({len(msg.content)} chars) from={msg.source}")
        msg.content = msg.content[:8000]
    stateful_resp = await _handle_stateful_sync(msg)
    if stateful_resp is not None:
        return stateful_resp
    return await _persist_and_enqueue_intent(msg)


async def recover_stale_pending_messages(older_than_seconds: int = 60) -> int:
    """No-op — PendingMessage table removed. Kept for API compatibility."""
    return 0


@router.post("/menu")
async def setup_menu(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    """Admin endpoint: create / update the WeChat custom menu."""
    from infra.auth.request_auth import require_admin_token
    require_admin_token(x_admin_token)
    cfg = _get_config()
    access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
    result = await create_menu(access_token)
    if result.get("errcode", -1) == 0:
        return {"status": "ok", "detail": "菜单创建成功"}
    return {"status": "error", "detail": result}


# ── Public aliases for cross-module use ──────────────────────────────────────
# wechat_flows.py uses these instead of reaching into private _handle_intent*.
# Keep names stable; internal implementation may change.

handle_intent = _handle_intent
handle_intent_bg = _handle_intent_bg
