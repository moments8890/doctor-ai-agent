import asyncio
import os
import re
import time
from fastapi import APIRouter, Request, Response
from wechatpy import parse_message
from wechatpy.crypto import WeChatCrypto
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.replies import TextReply
import httpx
from services.structuring import structure_medical_record
from services.intent import detect_intent, Intent
from services.wechat_menu import create_menu
from services.session import get_session, set_current_patient, set_pending_create, clear_pending_create
from db.engine import AsyncSessionLocal
from db.crud import create_patient, find_patient_by_name, save_record, get_records_for_patient, get_all_records_for_doctor, get_all_patients
from utils.log import log

router = APIRouter(prefix="/wechat", tags=["wechat"])

# Access token cache
_token_cache = {"token": "", "expires_at": 0.0}


def _get_config():
    return {
        "token": os.environ.get("WECHAT_TOKEN", ""),
        "app_id": os.environ.get("WECHAT_APP_ID", ""),
        "app_secret": os.environ.get("WECHAT_APP_SECRET", ""),
        "aes_key": os.environ.get("WECHAT_ENCODING_AES_KEY", ""),
    }


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


async def _get_access_token(app_id: str, app_secret: str) -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        log(f"[WeChat token] using cached token (expires in {int(_token_cache['expires_at'] - now)}s)")
        return _token_cache["token"]

    url = "https://api.weixin.qq.com/cgi-bin/token"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params={
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        })
        data = resp.json()
        log(f"[WeChat token] fetched new token: {data}")
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + data["expires_in"] - 60
        return _token_cache["token"]


def _split_message(text: str, limit: int = 600) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("【", 1, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:]
    return chunks


async def _send_customer_service_msg(to_user: str, content: str):
    cfg = _get_config()
    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}"
        chunks = _split_message(content)
        log(f"[WeChat cs] sending {len(chunks)} message(s) to {to_user}")
        async with httpx.AsyncClient() as client:
            for i, chunk in enumerate(chunks):
                payload = {"touser": to_user, "msgtype": "text", "text": {"content": chunk}}
                resp = await client.post(url, json=payload)
                log(f"[WeChat cs] chunk {i+1}/{len(chunks)}: {resp.json()}")
    except Exception as e:
        log(f"[WeChat cs] FAILED: {e}")


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


async def _handle_add_record(text: str, doctor_id: str, intent_result) -> str:
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

        try:
            record = await structure_medical_record(text)
        except ValueError:
            return "⚠️ 未能识别为有效病历，请发送完整的病历描述（包含主诉、诊断等信息）。"
        except Exception as e:
            log(f"[WeChat] structuring FAILED: {e}")
            return "处理失败，请稍后重试。"

        await save_record(session, doctor_id, record, patient_id)

    reply = _format_record(record)
    if intent_result.extra_data:
        log(f"[WeChat] cv_metrics={intent_result.extra_data}")
    if patient_name:
        if patient_created:
            reply = f"✅ 已为【{patient_name}】新建档并保存病历\n\n" + reply
        else:
            reply = f"📌 已关联患者【{patient_name}】\n\n" + reply
    if intent_result.is_emergency:
        reply = "🚨 【紧急记录已保存】\n\n" + reply
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
    # 患者 menu
    "PATIENT_RECORDS": "📋 请发送您的姓名，我将为您查询病历记录。",
    "PATIENT_CONSULT": "👨‍⚕️ 请直接发送您的问题，医生助手将为您解答。",
    "PATIENT_HELP": (
        "📖 使用说明：\n"
        "• 患者：点击「患者」菜单查看病历或咨询医生\n"
        "• 医生：点击「医生」菜单新建患者、录入或查询病历\n"
        "• 也可直接发送文字，AI 将自动识别意图并处理"
    ),
    # 医生 menu
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
        info = "、".join(filter(None, [p.gender, f"{p.age}岁" if p.age else None]))
        lines.append(f"{i}. {p.name}" + (f"（{info}）" if info else ""))
    lines.append("\n发送「查询[姓名]」查看病历")
    return "\n".join(lines)


async def _handle_menu_event(event_key: str, doctor_id: str) -> str:
    if event_key == "DOCTOR_ALL_PATIENTS":
        return await _handle_all_patients(doctor_id)
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
        return (
            f"未找到患者【{name}】。\n\n"
            "请回复性别和年龄以建立新档案，例如：男，30岁\n"
            "或发送「取消」放弃"
        )


async def _handle_pending_create(text: str, doctor_id: str) -> str:
    """Handle the reply to the 'please provide gender/age' prompt."""
    sess = get_session(doctor_id)
    name = sess.pending_create_name

    if text.strip() in ("取消", "cancel", "Cancel", "退出", "不要"):
        clear_pending_create(doctor_id)
        return f"已取消，未创建患者【{name}】。"

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
    return f"✅ 已为患者【{name}】建档" + (f"（{parts}）" if parts else "") + "。\n后续病历将自动关联该患者。"


async def _handle_intent(text: str, doctor_id: str) -> str:
    try:
        intent_result = await detect_intent(text)
    except Exception as e:
        log(f"[WeChat] intent detection FAILED: {e}, falling back to structuring")
        return await _build_reply(text)

    log(f"[WeChat] intent={intent_result.intent} patient={intent_result.patient_name}")

    if intent_result.intent == Intent.create_patient:
        return await _handle_create_patient(doctor_id, intent_result)
    elif intent_result.intent == Intent.add_record:
        return await _handle_add_record(text, doctor_id, intent_result)
    elif intent_result.intent == Intent.query_records:
        return await _handle_query_records(doctor_id, intent_result)
    elif intent_result.intent == Intent.list_patients:
        return await _handle_all_patients(doctor_id)
    elif intent_result.intent == Intent.unknown and _NAME_ONLY.match(text.strip()):
        return await _handle_name_lookup(text.strip(), doctor_id)
    else:
        return (
            "您好！我是医生助手，请发送以下内容：\n\n"
            "📋 病历记录 — 直接描述症状、诊断和治疗\n"
            "👤 新建患者 — 例如：新患者李明，45岁男性\n"
            "🔍 查询病历 — 例如：查一下李明的记录\n"
            "👥 所有病人 — 查看患者列表"
        )


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
    try:
        result = await _handle_intent(text, doctor_id)
    except Exception as e:
        log(f"[WeChat bg] FAILED: {e}")
        result = "处理失败，请稍后重试。"
    await _send_customer_service_msg(doctor_id, result)


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

    if msg.type != "text" or not msg.content.strip():
        reply = TextReply(content="请发送文字病历记录，我将自动生成结构化病历。", message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Pending create flow: doctor was asked for gender/age of a new patient.
    sess = get_session(msg.source)
    if sess.pending_create_name:
        reply_text = await _handle_pending_create(msg.content, msg.source)
        log(f"[WeChat msg] pending_create reply: {reply_text[:80]}")
        reply = TextReply(content=reply_text, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # Peek at intent using fast rule-based detection (< 5 ms, no network).
    # add_record triggers an Ollama LLM call that can exceed WeChat's 5 s limit,
    # so we ACK immediately and deliver the result via the customer service API.
    from services.intent_rules import detect_intent_rules
    peek = detect_intent_rules(msg.content)
    log(f"[WeChat msg] peek intent={peek.intent}")

    if peek.intent == Intent.add_record:
        asyncio.create_task(_handle_intent_bg(msg.content, msg.source))
        ack = "⏳ 正在生成结构化病历，稍候将发送给您…"
        log(f"[WeChat msg] add_record → background task created for {msg.source}")
        reply = TextReply(content=ack, message=msg)
        return Response(content=reply.render(), media_type="application/xml")

    # All other intents (create_patient, query_records, unknown) are fast.
    try:
        reply_text = await asyncio.wait_for(_handle_intent(msg.content, msg.source), timeout=4.5)
    except asyncio.TimeoutError:
        reply_text = "⏳ 处理超时，请重新发送消息。"
        log(f"[WeChat msg] timeout for {msg.source}")

    log(f"[WeChat msg] reply to {msg.source}:\n{reply_text}")
    reply = TextReply(content=reply_text, message=msg)
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
