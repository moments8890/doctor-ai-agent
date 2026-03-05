import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from fastapi import APIRouter, Request, Response
import httpx
from wechatpy import parse_message
from wechatpy.crypto import WeChatCrypto
from wechatpy.enterprise.crypto import WeChatCrypto as EnterpriseWeChatCrypto
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import TextReply
from services.structuring import structure_medical_record
from services.transcription import transcribe_audio
from services.vision import extract_text_from_image
from services.pdf_extract import extract_text_from_pdf
from services import wechat_domain as wd
from services import wechat_media_pipeline as wmp
from services import wecom_kf_sync as kfsync
from services.wechat_voice import download_and_convert, download_voice
from services.intent import Intent, IntentResult
from services.agent import dispatch as agent_dispatch
from services.wechat_menu import create_menu
from services.wechat_notify import (
    _get_config, _get_access_token, _send_customer_service_msg, _split_message as _notify_split_message,
)
from services.wechat_customer import prefetch_customer_profile
from services.session import (
    get_session,
    get_session_lock,
    push_turn,
    set_current_patient,
    hydrate_session_state,
)
from services.memory import maybe_compress, load_context_message
from services.tasks import create_follow_up_task, create_emergency_task, create_appointment_task
from db.engine import AsyncSessionLocal
from db.crud import (
    create_patient,
    find_patient_by_name,
    save_record,
    get_records_for_patient,
    get_all_records_for_doctor,
    get_all_patients,
    list_tasks,
    update_task_status,
)
from utils.log import log

_COMPLETE_RE = re.compile(r'^完成\s*(\d+)$')

router = APIRouter(prefix="/wechat", tags=["wechat"])
_WECHAT_KF_SYNC_CURSOR: str = ""
_WECHAT_KF_SEEN_MSG_IDS: set = set()
_WECHAT_KF_CURSOR_LOADED: bool = False
_WECHAT_KF_CURSOR_FILE = Path(__file__).resolve().parents[1] / "logs" / "wechat_kf_sync_state.json"


def _sync_wechat_domain_bindings() -> None:
    wd.AsyncSessionLocal = AsyncSessionLocal
    wd.structure_medical_record = structure_medical_record
    wd.create_patient = create_patient
    wd.find_patient_by_name = find_patient_by_name
    wd.save_record = save_record
    wd.get_records_for_patient = get_records_for_patient
    wd.get_all_records_for_doctor = get_all_records_for_doctor
    wd.get_all_patients = get_all_patients
    wd.list_tasks = list_tasks
    wd.update_task_status = update_task_status
    wd.create_follow_up_task = create_follow_up_task
    wd.create_emergency_task = create_emergency_task
    wd.create_appointment_task = create_appointment_task


def _extract_open_kfid(msg) -> str:
    return wd.extract_open_kfid(msg)


def _load_wecom_kf_sync_cursor() -> str:
    try:
        if not _WECHAT_KF_CURSOR_FILE.exists():
            return ""
        data = json.loads(_WECHAT_KF_CURSOR_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ""
        return str(data.get("cursor") or "").strip()
    except Exception as e:
        log(f"[WeCom KF] load cursor FAILED: {e}")
        return ""


def _persist_wecom_kf_sync_cursor(cursor: str) -> None:
    if not cursor:
        return
    try:
        _WECHAT_KF_CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        _WECHAT_KF_CURSOR_FILE.write_text(
            json.dumps({"cursor": cursor}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log(f"[WeCom KF] persist cursor FAILED: {e}")


def _name_token_or_none(text: str) -> str:
    return wd.name_token_or_none(text)


def _explicit_name_or_none(text: str) -> str:
    return wd.explicit_name_or_none(text)


def _looks_like_symptom_note(text: str) -> bool:
    return wd.looks_like_symptom_note(text)


def _format_record(record) -> str:
    return wd.format_record(record)


def _split_message(text: str, limit: int = 600) -> List[str]:
    # Backward-compatible router-level alias used by existing tests.
    return _notify_split_message(text, limit=limit)



async def _build_reply(content: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.build_reply(content)


async def _handle_create_patient(doctor_id: str, intent_result) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_create_patient(doctor_id, intent_result)


async def _handle_add_record(text: str, doctor_id: str, intent_result, history: list = None) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_add_record(text, doctor_id, intent_result, history=history)


async def _handle_query_records(doctor_id: str, intent_result) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_query_records(doctor_id, intent_result)


async def _handle_all_patients(doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_all_patients(doctor_id)


async def _start_interview(doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.start_interview(doctor_id)


async def _handle_interview_step(text: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_interview_step(text, doctor_id)


async def _handle_menu_event(event_key: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    wd.handle_all_patients = _handle_all_patients
    wd.start_interview = _start_interview
    return await wd.handle_menu_event(event_key, doctor_id)


async def _handle_name_lookup(name: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    wd.handle_query_records = _handle_query_records
    return await wd.handle_name_lookup(name, doctor_id)


async def _handle_pending_create(text: str, doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_pending_create(text, doctor_id)


async def _handle_list_tasks(doctor_id: str) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_list_tasks(doctor_id)


async def _handle_complete_task(doctor_id: str, intent_result) -> str:
    _sync_wechat_domain_bindings()
    return await wd.handle_complete_task(doctor_id, intent_result)


async def _handle_schedule_appointment(doctor_id: str, intent_result) -> str:
    patient_name = intent_result.patient_name
    if not patient_name:
        return "⚠️ 未能识别患者姓名，请重新说明预约信息。"
    raw_time = intent_result.extra_data.get("appointment_time")
    if not raw_time:
        return "⚠️ 未能识别预约时间，请使用格式如「明天下午2点」或「2026-03-15 14:00」。"
    try:
        appointment_dt = datetime.fromisoformat(str(raw_time))
    except (ValueError, TypeError):
        return "⚠️ 时间格式无法识别，请使用格式如「2026-03-15T14:00:00」。"
    notes = intent_result.extra_data.get("notes")
    from services.tasks import create_appointment_task as _create_appt

    task = await _create_appt(doctor_id, patient_name, appointment_dt, notes)
    return (
        f"📅 已为患者【{patient_name}】安排预约\n"
        f"预约时间：{appointment_dt.strftime('%Y-%m-%d %H:%M')}\n"
        f"任务编号：{task.id}（将在1小时前提醒）"
    )


async def _handle_intent(text: str, doctor_id: str, history: list = None) -> str:
    # Fast-path: "完成 N" bypasses LLM
    m = _COMPLETE_RE.match(text.strip())
    if m:
        task_id = int(m.group(1))
        async with AsyncSessionLocal() as session:
            task = await update_task_status(session, task_id, doctor_id, "completed")
        if task is None:
            return f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。"
        return f"✅ 任务【{task.title}】已标记完成。"

    try:
        intent_result = await agent_dispatch(text, history=history or [])
    except Exception as e:
        log(f"[WeChat] agent dispatch FAILED: {e}, falling back to structuring")
        try:
            record = await structure_medical_record(text)
            return _format_record(record)
        except ValueError:
            return "没能识别病历内容，请重新描述一下。"
        except Exception:
            return "不好意思，出了点问题，能再说一遍吗？"

    log(f"[WeChat] intent={intent_result.intent} patient={intent_result.patient_name}")

    if intent_result.intent == Intent.create_patient:
        return await _handle_create_patient(doctor_id, intent_result)
    elif intent_result.intent == Intent.add_record:
        sess = get_session(doctor_id)
        if not intent_result.patient_name and not sess.current_patient_id:
            # If session context was lost but this conversation has only one patient,
            # safely re-bind to that patient to avoid unnecessary follow-up question.
            async with AsyncSessionLocal() as session:
                patients = await get_all_patients(session, doctor_id)
            if len(patients) == 1:
                only = patients[0]
                set_current_patient(doctor_id, only.id, only.name)
                log(f"[WeChat] rebound single patient context: doctor={doctor_id} patient={only.name}")
                return await _handle_add_record(text, doctor_id, intent_result, history=history)
            candidate_name = _name_token_or_none(text)
            if candidate_name:
                return await _handle_name_lookup(candidate_name, doctor_id)
            return "请问这位患者叫什么名字？"
        return await _handle_add_record(text, doctor_id, intent_result, history=history)
    elif intent_result.intent == Intent.query_records:
        return await _handle_query_records(doctor_id, intent_result)
    elif intent_result.intent == Intent.list_patients:
        return await _handle_all_patients(doctor_id)
    elif intent_result.intent == Intent.list_tasks:
        return await _handle_list_tasks(doctor_id)
    elif intent_result.intent == Intent.complete_task:
        return await _handle_complete_task(doctor_id, intent_result)
    elif intent_result.intent == Intent.schedule_appointment:
        return await _handle_schedule_appointment(doctor_id, intent_result)
    elif intent_result.intent == Intent.unknown:
        explicit_name = _explicit_name_or_none(text)
        if explicit_name:
            looked_up = await _handle_name_lookup(explicit_name, doctor_id)
            if looked_up:
                return looked_up
        sess = get_session(doctor_id)
        if sess.current_patient_id and _looks_like_symptom_note(text):
            synthetic = IntentResult(
                intent=Intent.add_record,
                patient_name=sess.current_patient_name,
                structured_fields={"chief_complaint": text.strip()},
                chat_reply=(
                    f"已记录【{sess.current_patient_name}】当前症状：{text.strip()}。"
                    "如补充持续时间/伴随症状/诱因，我可继续完善病历。"
                ),
            )
            return await _handle_add_record(text, doctor_id, synthetic, history=history)
        fallback = "您好！请直接描述病历内容、或说「新患者姓名」建档、或说「查询姓名」查记录。"
        return intent_result.chat_reply or fallback
    else:
        return intent_result.chat_reply or "您好！请直接描述病历内容、或说「新患者姓名」建档、或说「查询姓名」查记录。"


async def _handle_image_bg(media_id: str, doctor_id: str, open_kfid: str = ""):
    await wmp.handle_image_bg(
        media_id,
        doctor_id,
        get_config=_get_config,
        get_access_token=_get_access_token,
        download_media=download_voice,
        extract_image_text=extract_text_from_image,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_intent_bg=lambda text, uid: _handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def _handle_pdf_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    await wmp.handle_pdf_file_bg(
        media_id,
        filename,
        doctor_id,
        get_config=_get_config,
        get_access_token=_get_access_token,
        download_media=download_voice,
        extract_pdf_text=extract_text_from_pdf,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_intent_bg=lambda text, uid: _handle_intent_bg(text, uid, open_kfid=open_kfid),
        log=log,
    )


async def _handle_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    await wmp.handle_file_bg(
        media_id,
        filename,
        doctor_id,
        get_config=_get_config,
        get_access_token=_get_access_token,
        download_media=download_voice,
        send_customer_service_msg=lambda uid, content: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_pdf_file_bg_fn=lambda mid, fname, uid: _handle_pdf_file_bg(
            mid, fname, uid, open_kfid=open_kfid
        ),
        log=log,
    )


def _extract_cdata(xml_str: str, tag: str) -> str:
    return wd.extract_cdata(xml_str, tag)


def _wecom_kf_msg_to_text(msg: Dict[str, Any]) -> str:
    return wd.wecom_kf_msg_to_text(msg)


def _wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    return wd.wecom_msg_is_processable(msg)


def _wecom_msg_time(msg: Dict[str, Any]) -> int:
    return wd.wecom_msg_time(msg)


async def _handle_wecom_kf_event_bg(
    expected_msgid: str = "",
    event_create_time: int = 0,
    event_token: str = "",
    event_open_kfid: str = "",
) -> None:
    """Fetch latest WeCom KF customer messages and route through intent pipeline."""
    global _WECHAT_KF_SYNC_CURSOR, _WECHAT_KF_CURSOR_LOADED
    async def _enqueue_intent(text: str, doctor_id: str, open_kfid: str) -> None:
        asyncio.create_task(_handle_intent_bg(text, doctor_id, open_kfid=open_kfid))

    async def _enqueue_voice(media_id: str, doctor_id: str, open_kfid: str) -> None:
        asyncio.create_task(_handle_voice_bg(media_id, doctor_id, open_kfid=open_kfid))

    async def _enqueue_image(media_id: str, doctor_id: str, open_kfid: str) -> None:
        asyncio.create_task(_handle_image_bg(media_id, doctor_id, open_kfid=open_kfid))

    async def _enqueue_file(media_id: str, filename: str, doctor_id: str, open_kfid: str) -> None:
        asyncio.create_task(_handle_file_bg(media_id, filename, doctor_id, open_kfid=open_kfid))

    state = await kfsync.handle_event(
        expected_msgid=expected_msgid,
        event_create_time=event_create_time,
        event_token=event_token,
        event_open_kfid=event_open_kfid,
        sync_cursor=_WECHAT_KF_SYNC_CURSOR,
        cursor_loaded=_WECHAT_KF_CURSOR_LOADED,
        seen_msg_ids=_WECHAT_KF_SEEN_MSG_IDS,
        load_cursor=_load_wecom_kf_sync_cursor,
        persist_cursor=_persist_wecom_kf_sync_cursor,
        log=log,
        get_config=_get_config,
        get_access_token=_get_access_token,
        msg_to_text=_wecom_kf_msg_to_text,
        msg_is_processable=_wecom_msg_is_processable,
        msg_time=_wecom_msg_time,
        send_customer_service_msg=lambda uid, content, open_kfid: _send_customer_service_msg(
            uid, content, open_kfid=open_kfid
        ),
        handle_voice_bg=_enqueue_voice,
        handle_image_bg=_enqueue_image,
        handle_file_bg=_enqueue_file,
        handle_intent_bg=_enqueue_intent,
        async_client_cls=httpx.AsyncClient,
    )
    _WECHAT_KF_SYNC_CURSOR = state.get("sync_cursor", _WECHAT_KF_SYNC_CURSOR)
    _WECHAT_KF_CURSOR_LOADED = bool(state.get("cursor_loaded", _WECHAT_KF_CURSOR_LOADED))


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
        f"[WeChat verify] token={cfg['token']!r} signature={effective_sig} "
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


async def _handle_intent_bg(text: str, doctor_id: str, open_kfid: str = ""):
    """Process intent in background and deliver result via customer service API."""
    if open_kfid:
        # Non-blocking enrichment from WeCom customer profile.
        asyncio.create_task(prefetch_customer_profile(doctor_id))

    await hydrate_session_state(doctor_id)
    async with get_session_lock(doctor_id):
        sess = get_session(doctor_id)
        if sess.pending_create_name:
            result = await _handle_pending_create(text, doctor_id)
            push_turn(doctor_id, text, result)
        elif sess.interview is not None:
            result = await _handle_interview_step(text, doctor_id)
            push_turn(doctor_id, text, result)
        else:
            # Compress rolling window if full or idle before adding new turn
            await maybe_compress(doctor_id, sess)

            # Build history: inject persisted context only when starting a fresh session
            history = list(sess.conversation_history)
            if not history:
                ctx_msg = await load_context_message(doctor_id)
                if ctx_msg:
                    history = [ctx_msg]

            try:
                result = await _handle_intent(text, doctor_id, history=history)
            except Exception as e:
                log(f"[WeChat bg] FAILED: {e}")
                result = "不好意思，出了点问题，能再说一遍吗？"

            push_turn(doctor_id, text, result)
    try:
        await _send_customer_service_msg(doctor_id, result, open_kfid=open_kfid)
    except Exception as e:
        log(f"[WeChat bg] send FAILED: {e}")


async def _handle_voice_bg(media_id: str, doctor_id: str, open_kfid: str = ""):
    """Download, convert, transcribe WeChat voice, then route through normal pipeline."""
    # --- IO outside lock: no session state accessed ---
    cfg = _get_config()
    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        wav = await download_and_convert(media_id, access_token)
        text = await transcribe_audio(wav, "voice.wav")
        log(f"[Voice] transcribed for {doctor_id}: {text!r}")
    except Exception as e:
        log(f"[Voice] transcription FAILED: {e}")
        await _send_customer_service_msg(doctor_id, f"❌ 语音识别失败：{e}", open_kfid=open_kfid)
        return

    # --- state check + stateful routing under lock ---
    route = "intent"
    result = None
    await hydrate_session_state(doctor_id)
    async with get_session_lock(doctor_id):
        sess = get_session(doctor_id)
        try:
            if sess.pending_create_name:
                result = await _handle_pending_create(text, doctor_id)
                route = "done"
            elif sess.interview is not None:
                result = await _handle_interview_step(text, doctor_id)
                route = "done"
        except Exception as e:
            log(f"[Voice] routing FAILED: {e}")
            result = "处理失败，请稍后重试。"
            route = "done"

    if route == "done":
        await _send_customer_service_msg(doctor_id, f'🎙️ 「{text}」\n\n{result}', open_kfid=open_kfid)
    else:
        # delegate — _handle_intent_bg acquires its own lock
        await _handle_intent_bg(text, doctor_id, open_kfid=open_kfid)


@router.post("")
async def handle_message(request: Request):
    cfg = _get_config()
    params = dict(request.query_params)
    timestamp = params.get("timestamp", "")
    nonce = params.get("nonce", "")
    msg_signature = params.get("msg_signature", "")
    encrypt_type = params.get("encrypt_type", "")

    log(f"[WeChat msg] POST received — encrypt_type={encrypt_type!r}")

    body = await request.body()
    xml_str = body.decode("utf-8")
    log(f"[WeChat msg] body={xml_str[:200]}")

    try:
        has_encrypt_node = "<Encrypt><![CDATA[" in xml_str or "<Encrypt>" in xml_str
        should_decrypt = (
            (encrypt_type == "aes")
            or (bool(msg_signature) and has_encrypt_node)
        )
        if should_decrypt and cfg["aes_key"] and cfg["app_id"]:
            crypto_cls = EnterpriseWeChatCrypto if cfg["app_id"].startswith("ww") else WeChatCrypto
            crypto = crypto_cls(cfg["token"], cfg["aes_key"], cfg["app_id"])
            xml_str = crypto.decrypt_message(xml_str, msg_signature, timestamp, nonce)
            log(f"[WeChat msg] decrypted={xml_str[:200]}")
    except Exception as e:
        log(f"[WeChat msg] decrypt FAILED: {e}")
        return Response(content="", media_type="application/xml")

    # WeCom KF callback may send only event=kf_msg_or_event.
    # The actual customer content is pulled via kf/sync_msg.
    if _extract_cdata(xml_str, "Event") == "kf_msg_or_event":
        expected_msgid = _extract_cdata(xml_str, "MsgId") or _extract_cdata(xml_str, "Msgid")
        create_time_raw = _extract_cdata(xml_str, "CreateTime")
        event_token = _extract_cdata(xml_str, "Token")
        event_open_kfid = _extract_cdata(xml_str, "OpenKfId")
        try:
            event_create_time = int(create_time_raw) if create_time_raw else 0
        except ValueError:
            event_create_time = 0
        asyncio.create_task(
            _handle_wecom_kf_event_bg(
                expected_msgid=expected_msgid,
                event_create_time=event_create_time,
                event_token=event_token,
                event_open_kfid=event_open_kfid,
            )
        )
        return Response(content="success", media_type="text/plain")

    try:
        msg = parse_message(xml_str)
        log(f"[WeChat msg] type={msg.type!r} from={msg.source}")
    except Exception as e:
        log(f"[WeChat msg] parse FAILED: {e}")
        return Response(content="", media_type="application/xml")

    if msg.type == "event" and msg.event.upper() == "CLICK":
        reply_text = await _handle_menu_event(msg.key, msg.source)
        log(f"[WeChat msg] menu click key={msg.key!r} reply={reply_text[:60]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Voice message: ACK immediately, process in background
    if msg.type == "voice":
        asyncio.create_task(_handle_voice_bg(msg.media_id, msg.source, _extract_open_kfid(msg)))
        await hydrate_session_state(msg.source)
        sess = get_session(msg.source)
        if sess.interview is not None:
            ack = f"🎙️ 收到语音，正在识别…\n{sess.interview.progress} {sess.interview.current_question}"
        else:
            ack = "🎙️ 收到语音，正在识别，稍候回复您…"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Image message: ACK immediately, extract text via vision LLM in background
    if msg.type == "image":
        asyncio.create_task(_handle_image_bg(msg.media_id, msg.source, _extract_open_kfid(msg)))
        ack = "🖼️ 收到图片，正在识别文字…"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type in ("video", "shortvideo"):
        ack = "🎬 收到视频。当前暂不支持自动解析视频，请发送关键内容文字说明。"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type == "location":
        label = str(getattr(msg, "label", "") or "")
        x = str(getattr(msg, "location_x", "") or "")
        y = str(getattr(msg, "location_y", "") or "")
        text = f"[位置消息] {label}".strip()
        if x and y:
            text += f" ({x},{y})"
        asyncio.create_task(_handle_intent_bg(text, msg.source, _extract_open_kfid(msg)))
        reply = TextReply(content="📍 已收到位置，正在处理…", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type == "link":
        title = str(getattr(msg, "title", "") or "")
        url = str(getattr(msg, "url", "") or "")
        text = f"[链接消息] {title or url}".strip()
        asyncio.create_task(_handle_intent_bg(text, msg.source, _extract_open_kfid(msg)))
        reply = TextReply(content="🔗 已收到链接，正在处理…", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type != "text" or not msg.content.strip():
        reply = TextReply(content="请发送文字、语音或图片消息。", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Stateful flows take priority over intent detection
    await hydrate_session_state(msg.source)
    sess = get_session(msg.source)

    if sess.pending_create_name:
        reply_text = await _handle_pending_create(msg.content, msg.source)
        log(f"[WeChat msg] pending_create reply: {reply_text[:80]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if sess.interview is not None:
        reply_text = await _handle_interview_step(msg.content, msg.source)
        log(f"[WeChat msg] interview step reply: {reply_text[:80]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Always background: LLM agent call cannot fit in WeChat's 5s window.
    # Deliver result via customer service API.
    asyncio.create_task(_handle_intent_bg(msg.content, msg.source, _extract_open_kfid(msg)))
    log(f"[WeChat msg] → background task created for {msg.source}")
    reply = TextReply(content="⏳ 正在处理，稍候回复您…", message=msg)
    return Response(content=reply.render(), media_type="application/xml")


@router.post("/menu")
async def setup_menu():
    """Admin endpoint: create / update the WeChat custom menu."""
    cfg = _get_config()
    access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
    result = await create_menu(access_token)
    if result.get("errcode", -1) == 0:
        return {"status": "ok", "detail": "菜单创建成功"}
    return {"status": "error", "detail": result}
