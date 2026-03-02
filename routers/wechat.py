import asyncio
import os
import re
from datetime import datetime
from fastapi import APIRouter, Request, Response
from wechatpy import parse_message
from wechatpy.crypto import WeChatCrypto
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import TextReply
from services.structuring import structure_medical_record
from services.transcription import transcribe_audio
from services.vision import extract_text_from_image
from services.voice import download_and_convert, download_voice
from services.interview import InterviewState, STEPS
from services.intent import Intent
from services.agent import dispatch as agent_dispatch
from services.wechat_menu import create_menu
from services.wechat_notify import (
    _get_config, _get_access_token, _split_message,
    _send_customer_service_msg, _token_cache,
)
from services.session import get_session, get_session_lock, push_turn, set_current_patient, set_pending_create, clear_pending_create
from services.memory import maybe_compress, load_context_message
from services.tasks import create_follow_up_task, create_emergency_task, create_appointment_task
from db.engine import AsyncSessionLocal
from db.crud import create_patient, find_patient_by_name, save_record, get_records_for_patient, get_all_records_for_doctor, get_all_patients, list_tasks, update_task_status
from utils.log import log

_COMPLETE_RE = re.compile(r'^完成\s*(\d+)$')

router = APIRouter(prefix="/wechat", tags=["wechat"])


def _format_record(record) -> str:
    lines = ["📋 结构化病历\n"]
    lines.append(f"【主诉】\n{record.chief_complaint}\n")
    if record.history_of_present_illness:
        lines.append(f"【现病史】\n{record.history_of_present_illness}\n")
    if record.past_medical_history:
        lines.append(f"【既往史】\n{record.past_medical_history}\n")
    if record.physical_examination:
        lines.append(f"【体格检查】\n{record.physical_examination}\n")
    if record.auxiliary_examinations:
        lines.append(f"【辅助检查】\n{record.auxiliary_examinations}\n")
    if record.diagnosis:
        lines.append(f"【诊断】\n{record.diagnosis}\n")
    if record.treatment_plan:
        lines.append(f"【治疗方案】\n{record.treatment_plan}\n")
    if record.follow_up_plan:
        lines.append(f"【随访计划】\n{record.follow_up_plan}")
    return "\n".join(lines)



async def _build_reply(content: str) -> str:
    try:
        record = await structure_medical_record(content)
        return _format_record(record)
    except ValueError:
        return "⚠️ 未能识别为有效病历，请发送完整的病历描述（包含主诉、诊断等信息）。"
    except Exception as e:
        log(f"[WeChat] structuring FAILED: {e}")
        return "处理失败，请稍后重试。"


async def _handle_create_patient(doctor_id: str, intent_result) -> str:
    name = intent_result.patient_name
    if not name:
        return "⚠️ 未能识别患者姓名，请重新说明，例如：帮我建个新患者，张三，30岁男性。"
    async with AsyncSessionLocal() as session:
        patient = await create_patient(
            session, doctor_id, name, intent_result.gender, intent_result.age
        )
        set_current_patient(doctor_id, patient.id, patient.name)
    age_str = f"，{intent_result.age}岁" if intent_result.age else ""
    gender_str = f"，{intent_result.gender}性" if intent_result.gender else ""
    return f"✅ 已为患者【{name}】建档{gender_str}{age_str}，后续病历将自动关联该患者。"


async def _handle_add_record(text: str, doctor_id: str, intent_result, history: list = None) -> str:
    from models.medical_record import MedicalRecord
    # Resolve patient: by name in message > auto-create if new > current session
    patient_id = None
    patient_name = None
    patient_created = False
    async with AsyncSessionLocal() as session:
        if intent_result.patient_name:
            patient = await find_patient_by_name(session, doctor_id, intent_result.patient_name)
            if patient:
                patient_id = patient.id
                patient_name = patient.name
                set_current_patient(doctor_id, patient.id, patient.name)
            else:
                # Name mentioned but not on file — auto-create so the record is linked
                patient = await create_patient(
                    session, doctor_id, intent_result.patient_name,
                    intent_result.gender, intent_result.age,
                )
                patient_id = patient.id
                patient_name = patient.name
                patient_created = True
                set_current_patient(doctor_id, patient.id, patient.name)
                log(f"[WeChat] auto-created patient [{patient_name}] id={patient_id}")

        if patient_id is None:
            sess = get_session(doctor_id)
            patient_id = sess.current_patient_id
            patient_name = sess.current_patient_name

        # Build MedicalRecord: prefer single-LLM structured_fields, fallback to dedicated LLM
        if intent_result.structured_fields:
            fields = dict(intent_result.structured_fields)
            if not fields.get("chief_complaint"):
                fields["chief_complaint"] = text.split("，")[0][:20] or "门诊就诊"
            record = MedicalRecord(**{k: fields.get(k) for k in MedicalRecord.model_fields})
        else:
            try:
                doctor_ctx = [m["content"] for m in (history or [])[-10:] if m["role"] == "user"]
                doctor_ctx.append(text)
                record = await structure_medical_record("\n".join(doctor_ctx))
            except ValueError:
                return "没能识别病历内容，请重新描述一下。"
            except Exception as e:
                log(f"[WeChat] structuring FAILED: {e}")
                return "不好意思，刚才出了点问题，能再说一遍吗？"

        db_record = await save_record(session, doctor_id, record, patient_id)

    # Fire-and-forget task creation (outside the DB session)
    if record.follow_up_plan:
        asyncio.create_task(create_follow_up_task(
            doctor_id, db_record.id, patient_name or "未关联患者",
            record.follow_up_plan, patient_id,
        ))
    if intent_result.is_emergency:
        asyncio.create_task(create_emergency_task(
            doctor_id, db_record.id, patient_name or "未关联患者",
            record.diagnosis, patient_id,
        ))

    # Natural reply from LLM, with brief fallback
    reply = intent_result.chat_reply
    if not reply:
        reply = f"{patient_name}的病历已记录。" if patient_name else "病历已保存。"

    if intent_result.is_emergency:
        reply = "🚨 " + reply
    return reply


async def _handle_query_records(doctor_id: str, intent_result) -> str:
    patient_id = None
    patient_name = None

    async with AsyncSessionLocal() as session:
        if intent_result.patient_name:
            patient = await find_patient_by_name(session, doctor_id, intent_result.patient_name)
            if patient:
                patient_id = patient.id
                patient_name = patient.name

        if patient_id is None:
            sess = get_session(doctor_id)
            patient_id = sess.current_patient_id
            patient_name = sess.current_patient_name

        if patient_id is not None:
            records = await get_records_for_patient(session, doctor_id, patient_id)
            if not records:
                return f"📂 患者【{patient_name}】暂无历史记录。"
            lines = [f"📂 患者【{patient_name}】最近 {len(records)} 条记录：\n"]
            for i, r in enumerate(records, 1):
                date_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else "未知日期"
                lines.append(
                    f"{i}. [{date_str}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}"
                )
            return "\n".join(lines)

        # No specific patient — return all records for this doctor
        records = await get_all_records_for_doctor(session, doctor_id)

    if not records:
        return "📂 暂无任何病历记录。"

    lines = [f"📂 所有患者最近 {len(records)} 条记录：\n"]
    for i, r in enumerate(records, 1):
        pname = r.patient.name if r.patient else "未关联患者"
        date_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else "未知日期"
        lines.append(
            f"{i}. 【{pname}】[{date_str}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}"
        )
    return "\n".join(lines)


_MENU_EVENT_REPLIES = {
    "DOCTOR_NEW_PATIENT": "🆕 请发送患者信息，例如：帮我建个新患者，张三，30岁男性。",
    "DOCTOR_ADD_RECORD": "📝 请发送病历描述，AI 将自动生成结构化病历并保存。",
    "DOCTOR_QUERY": "🔍 请发送患者姓名，例如：查询张三的病历。",
}


async def _handle_all_patients(doctor_id: str) -> str:
    async with AsyncSessionLocal() as session:
        patients = await get_all_patients(session, doctor_id)
    if not patients:
        return "📂 暂无患者记录。发送「新患者姓名，年龄性别」可创建第一位患者。"
    lines = [f"👥 共 {len(patients)} 位患者：\n"]
    for i, p in enumerate(patients, 1):
        age_display = f"{datetime.now().year - p.year_of_birth}岁" if p.year_of_birth else None
        info = "、".join(filter(None, [p.gender, age_display]))
        lines.append(f"{i}. {p.name}" + (f"（{info}）" if info else ""))
    lines.append("\n发送「查询[姓名]」查看病历")
    return "\n".join(lines)


async def _start_interview(doctor_id: str) -> str:
    sess = get_session(doctor_id)
    sess.interview = InterviewState()
    first_q = STEPS[0][1]
    return f"🩺 开始问诊（发送「取消」随时结束）\n\n[1/{len(STEPS)}] {first_q}"


async def _handle_interview_step(text: str, doctor_id: str) -> str:
    if text.strip() in ("取消", "退出", "结束", "cancel"):
        get_session(doctor_id).interview = None
        return "好的，问诊结束了。"

    sess = get_session(doctor_id)
    iv = sess.interview
    iv.record_answer(text)

    if iv.active:
        return f"{iv.progress} {iv.current_question}"

    # All steps done — compile and save
    compiled = iv.compile_text()
    patient_name = iv.patient_name
    sess.interview = None
    log(f"[Interview] complete, compiled: {compiled}")

    try:
        record = await structure_medical_record(compiled)
    except Exception as e:
        log(f"[Interview] structuring FAILED: {e}")
        return "❌ 病历生成失败，请重新问诊。"

    async with AsyncSessionLocal() as session:
        patient = None
        if patient_name:
            patient = await find_patient_by_name(session, doctor_id, patient_name)
            if not patient:
                patient = await create_patient(session, doctor_id, patient_name, None, None)
            set_current_patient(doctor_id, patient.id, patient.name)
        await save_record(session, doctor_id, record, patient.id if patient else None)

    reply = "问诊完成，病历已保存。"
    if patient_name:
        reply = f"{patient_name}，" + reply
    return reply


async def _handle_menu_event(event_key: str, doctor_id: str) -> str:
    if event_key == "DOCTOR_ALL_PATIENTS":
        return await _handle_all_patients(doctor_id)
    if event_key == "DOCTOR_INTERVIEW":
        return await _start_interview(doctor_id)
    return _MENU_EVENT_REPLIES.get(event_key, "请通过菜单或文字与我们互动。")


_NAME_ONLY = re.compile(r'^[\u4e00-\u9fff]{2,4}$')


async def _handle_name_lookup(name: str, doctor_id: str) -> str:
    """Look up patient by name. If found, show records. If not, enter pending-create flow."""
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
    if patient:
        set_current_patient(doctor_id, patient.id, patient.name)
        log(f"[WeChat] name lookup hit: {name} → patient_id={patient.id}")
        from services.intent import IntentResult
        fake = IntentResult(intent=Intent.query_records, patient_name=name)
        return await _handle_query_records(doctor_id, fake)
    else:
        set_pending_create(doctor_id, name)
        log(f"[WeChat] name lookup miss: {name} → pending create")
        return f"没找到{name}这位患者，请问性别和年龄？（或发送「取消」放弃）"


async def _handle_pending_create(text: str, doctor_id: str) -> str:
    """Handle the reply to the 'please provide gender/age' prompt."""
    sess = get_session(doctor_id)
    name = sess.pending_create_name

    if text.strip() in ("取消", "cancel", "Cancel", "退出", "不要"):
        clear_pending_create(doctor_id)
        return "好的，已取消。"

    gender = None
    if re.search(r'男', text):
        gender = "男"
    elif re.search(r'女', text):
        gender = "女"

    age = None
    m = re.search(r'(\d+)\s*岁', text)
    if m:
        age = int(m.group(1))

    async with AsyncSessionLocal() as session:
        patient = await create_patient(session, doctor_id, name, gender, age)
        set_current_patient(doctor_id, patient.id, patient.name)

    clear_pending_create(doctor_id)
    parts = "、".join(filter(None, [gender, f"{age}岁" if age else None]))
    info = f"（{parts}）" if parts else ""
    return f"好的，{name}已建档{info}。"


async def _handle_list_tasks(doctor_id: str) -> str:
    async with AsyncSessionLocal() as session:
        tasks = await list_tasks(session, doctor_id, status="pending")
    if not tasks:
        return "📋 暂无待办任务。"
    lines = [f"📋 待办任务（共 {len(tasks)} 条）：\n"]
    for i, t in enumerate(tasks, 1):
        due_str = f" | ⏰ {t.due_at.strftime('%Y-%m-%d')}" if t.due_at else ""
        lines.append(f"{i}. [{t.task_type}] {t.title}{due_str}")
    lines.append("\n回复「完成 编号」标记任务完成")
    return "\n".join(lines)


async def _handle_complete_task(doctor_id: str, intent_result) -> str:
    task_id = intent_result.extra_data.get("task_id")
    if not isinstance(task_id, int):
        return "⚠️ 未能识别任务编号，请发送「完成 5」（5为任务编号）。"
    async with AsyncSessionLocal() as session:
        task = await update_task_status(session, task_id, doctor_id, "completed")
    if task is None:
        return f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。"
    return intent_result.chat_reply or "好的，任务完成了。"


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
    elif intent_result.intent == Intent.unknown and _NAME_ONLY.match(text.strip()):
        return await _handle_name_lookup(text.strip(), doctor_id)
    else:
        return intent_result.chat_reply or "您好！请直接描述病历内容、或说「新患者姓名」建档、或说「查询姓名」查记录。"


async def _handle_image_bg(media_id: str, doctor_id: str):
    """Download WeChat image, extract text via vision LLM, then route through normal pipeline."""
    # --- IO outside lock: no session state accessed ---
    cfg = _get_config()
    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        raw_bytes = await download_voice(media_id, access_token)  # same WeChat media endpoint
        text = await extract_text_from_image(raw_bytes, "image/jpeg")
        log(f"[Vision] extracted for {doctor_id}: {text[:80]!r}")
    except Exception as e:
        log(f"[Vision] extraction FAILED: {e}")
        await _send_customer_service_msg(doctor_id, f"❌ 图片识别失败：{e}")
        return

    # --- state check + stateful routing under lock ---
    route = "intent"
    result = None
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
            log(f"[Vision] routing FAILED: {e}")
            result = "处理失败，请稍后重试。"
            route = "done"

    if route == "done":
        preview = text[:60] + ("…" if len(text) > 60 else "")
        await _send_customer_service_msg(doctor_id, f"🖼️ 「{preview}」\n\n{result}")
    else:
        # delegate — _handle_intent_bg acquires its own lock
        await _handle_intent_bg(text, doctor_id)


@router.get("")
def verify(timestamp: str, nonce: str, signature: str, echostr: str):
    cfg = _get_config()
    log(f"[WeChat verify] token={cfg['token']!r} signature={signature}")
    try:
        check_signature(cfg["token"], signature, timestamp, nonce)
        log(f"[WeChat verify] OK")
        return Response(content=echostr, media_type="text/plain")
    except InvalidSignatureException as e:
        log(f"[WeChat verify] FAILED: {e}")
        return Response(content="Invalid signature", status_code=403)


async def _handle_intent_bg(text: str, doctor_id: str):
    """Process intent in background and deliver result via customer service API."""
    async with get_session_lock(doctor_id):
        sess = get_session(doctor_id)

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
    await _send_customer_service_msg(doctor_id, result)


async def _handle_voice_bg(media_id: str, doctor_id: str):
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
        await _send_customer_service_msg(doctor_id, f"❌ 语音识别失败：{e}")
        return

    # --- state check + stateful routing under lock ---
    route = "intent"
    result = None
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
        await _send_customer_service_msg(doctor_id, f'🎙️ 「{text}」\n\n{result}')
    else:
        # delegate — _handle_intent_bg acquires its own lock
        await _handle_intent_bg(text, doctor_id)


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
        if encrypt_type == "aes" and cfg["aes_key"] and cfg["app_id"]:
            crypto = WeChatCrypto(cfg["token"], cfg["aes_key"], cfg["app_id"])
            xml_str = crypto.decrypt_message(xml_str, msg_signature, timestamp, nonce)
            log(f"[WeChat msg] decrypted={xml_str[:200]}")
    except Exception as e:
        log(f"[WeChat msg] decrypt FAILED: {e}")
        return Response(content="", media_type="application/xml")

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
        asyncio.create_task(_handle_voice_bg(msg.media_id, msg.source))
        sess = get_session(msg.source)
        if sess.interview is not None:
            ack = f"🎙️ 收到语音，正在识别…\n{sess.interview.progress} {sess.interview.current_question}"
        else:
            ack = "🎙️ 收到语音，正在识别，稍候回复您…"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Image message: ACK immediately, extract text via vision LLM in background
    if msg.type == "image":
        asyncio.create_task(_handle_image_bg(msg.media_id, msg.source))
        ack = "🖼️ 收到图片，正在识别文字…"
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    if msg.type != "text" or not msg.content.strip():
        reply = TextReply(content="请发送文字、语音或图片消息。", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Stateful flows take priority over intent detection
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
    asyncio.create_task(_handle_intent_bg(msg.content, msg.source))
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
