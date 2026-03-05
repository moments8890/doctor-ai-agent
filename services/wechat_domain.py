from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.crud import (
    create_patient,
    find_patient_by_name,
    get_all_patients,
    get_all_records_for_doctor,
    get_records_for_patient,
    list_tasks,
    save_record,
    update_task_status,
)
from db.engine import AsyncSessionLocal
from services.agent import dispatch as agent_dispatch
from services.intent import Intent, IntentResult
from services.interview import InterviewState, STEPS
from services.session import (
    clear_pending_create,
    get_session,
    set_current_patient,
    set_pending_create,
)
from services.structuring import structure_medical_record
from services.tasks import create_appointment_task, create_emergency_task, create_follow_up_task
from utils.log import log

_NAME_TOKEN_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_NON_NAME_TOKENS = {"你好", "您好", "谢谢", "好的", "收到", "在吗", "哈喽", "嗯", "嗯嗯"}
_NON_NAME_SUBSTRINGS = {
    "发烧", "咳嗽", "头痛", "胸闷", "疼", "痛", "不适", "心悸", "气短",
    "一天", "两天", "三天", "一周", "两周", "三周", "一月", "两月",
    "记录", "病历", "查询", "随访", "复查", "预约",
}
_SYMPTOM_KEYWORDS = (
    "头疼", "头痛", "偏头痛", "发烧", "咳嗽", "胸闷", "胸痛",
    "腹痛", "恶心", "呕吐", "腹泻", "乏力", "眩晕", "心悸",
    "不舒服", "不适", "难受", "疼",
)
_EXPLICIT_NAME_PATTERNS = [
    re.compile(r"^\s*我是(?P<name>[\u4e00-\u9fff]{2,4})\s*$"),
    re.compile(r"^\s*我叫(?P<name>[\u4e00-\u9fff]{2,4})\s*$"),
    re.compile(r"^\s*患者(?:是|叫)?(?P<name>[\u4e00-\u9fff]{2,4})\s*$"),
]
_MENU_EVENT_REPLIES = {
    "DOCTOR_NEW_PATIENT": "🆕 请发送患者信息，例如：帮我建个新患者，张三，30岁男性。",
    "DOCTOR_ADD_RECORD": "📝 请发送病历描述，AI 将自动生成结构化病历并保存。",
    "DOCTOR_QUERY": "🔍 请发送患者姓名，例如：查询张三的病历。",
}


def extract_open_kfid(msg: Any) -> str:
    target = getattr(msg, "target", "")
    if isinstance(target, str):
        return target.strip()
    return ""


def extract_cdata(xml_str: str, tag: str) -> str:
    m = re.search(rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", xml_str)
    if m:
        return m.group(1)
    m = re.search(rf"<{tag}>([^<]+)</{tag}>", xml_str)
    return m.group(1) if m else ""


def name_token_or_none(text: str) -> str:
    candidate = text.strip()
    if _NAME_TOKEN_RE.match(candidate) and candidate not in _NON_NAME_TOKENS:
        if any(x in candidate for x in _NON_NAME_SUBSTRINGS):
            return ""
        return candidate
    return ""


def explicit_name_or_none(text: str) -> str:
    for pat in _EXPLICIT_NAME_PATTERNS:
        m = pat.match(text.strip())
        if not m:
            continue
        name = m.group("name")
        return name_token_or_none(name)
    return ""


def looks_like_symptom_note(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if len(s) > 30:
        return False
    return any(k in s for k in _SYMPTOM_KEYWORDS)


def format_record(record: Any) -> str:
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


async def build_reply(content: str) -> str:
    try:
        record = await structure_medical_record(content)
        return format_record(record)
    except ValueError:
        return "⚠️ 未能识别为有效病历，请发送完整的病历描述（包含主诉、诊断等信息）。"
    except Exception as e:
        log(f"[WeChat] structuring FAILED: {e}")
        return "处理失败，请稍后重试。"


async def handle_create_patient(doctor_id: str, intent_result: IntentResult) -> str:
    name = intent_result.patient_name
    if not name:
        return "⚠️ 未能识别患者姓名，请重新说明，例如：帮我建个新患者，张三，30岁男性。"
    created = False
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
        if patient is None:
            patient = await create_patient(session, doctor_id, name, intent_result.gender, intent_result.age)
            created = True
        set_current_patient(doctor_id, patient.id, patient.name)
    if not created and intent_result.gender is None and intent_result.age is None:
        return f"✅ 已切换到患者【{name}】，后续病历将自动关联该患者。"
    age_str = f"，{intent_result.age}岁" if intent_result.age else ""
    gender_str = f"，{intent_result.gender}性" if intent_result.gender else ""
    return f"✅ 已为患者【{name}】建档{gender_str}{age_str}，后续病历将自动关联该患者。"


async def handle_add_record(
    text: str,
    doctor_id: str,
    intent_result: IntentResult,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    from models.medical_record import MedicalRecord

    patient_id = None
    patient_name = None
    async with AsyncSessionLocal() as session:
        if intent_result.patient_name:
            patient = await find_patient_by_name(session, doctor_id, intent_result.patient_name)
            if patient:
                patient_id = patient.id
                patient_name = patient.name
                set_current_patient(doctor_id, patient.id, patient.name)
            else:
                patient = await create_patient(
                    session, doctor_id, intent_result.patient_name, intent_result.gender, intent_result.age
                )
                patient_id = patient.id
                patient_name = patient.name
                set_current_patient(doctor_id, patient.id, patient.name)
                log(f"[WeChat] auto-created patient [{patient_name}] id={patient_id}")

        if patient_id is None:
            sess = get_session(doctor_id)
            patient_id = sess.current_patient_id
            patient_name = sess.current_patient_name

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

    if record.follow_up_plan:
        asyncio.create_task(
            create_follow_up_task(doctor_id, db_record.id, patient_name or "未关联患者", record.follow_up_plan, patient_id)
        )
    if intent_result.is_emergency:
        asyncio.create_task(
            create_emergency_task(doctor_id, db_record.id, patient_name or "未关联患者", record.diagnosis, patient_id)
        )

    reply = intent_result.chat_reply or (f"{patient_name}的病历已记录。" if patient_name else "病历已保存。")
    if intent_result.is_emergency:
        reply = "🚨 " + reply
    return reply


async def handle_query_records(doctor_id: str, intent_result: IntentResult) -> str:
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
                lines.append(f"{i}. [{date_str}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}")
            return "\n".join(lines)

        records = await get_all_records_for_doctor(session, doctor_id)

    if not records:
        return "📂 暂无任何病历记录。"
    lines = [f"📂 所有患者最近 {len(records)} 条记录：\n"]
    for i, r in enumerate(records, 1):
        pname = r.patient.name if r.patient else "未关联患者"
        date_str = r.created_at.strftime("%Y-%m-%d") if r.created_at else "未知日期"
        lines.append(f"{i}. 【{pname}】[{date_str}] 主诉：{r.chief_complaint or '—'} | 诊断：{r.diagnosis or '—'}")
    return "\n".join(lines)


async def handle_all_patients(doctor_id: str) -> str:
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


async def start_interview(doctor_id: str) -> str:
    sess = get_session(doctor_id)
    sess.interview = InterviewState()
    return f"🩺 开始问诊（发送「取消」随时结束）\n\n[1/{len(STEPS)}] {STEPS[0][1]}"


async def handle_interview_step(text: str, doctor_id: str) -> str:
    if text.strip() in ("取消", "退出", "结束", "cancel"):
        get_session(doctor_id).interview = None
        return "好的，问诊结束了。"

    sess = get_session(doctor_id)
    iv = sess.interview
    iv.record_answer(text)
    if iv.active:
        return f"{iv.progress} {iv.current_question}"

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
        reply = f"{patient_name}，{reply}"
    return reply


async def handle_menu_event(event_key: str, doctor_id: str) -> str:
    if event_key == "DOCTOR_ALL_PATIENTS":
        return await handle_all_patients(doctor_id)
    if event_key == "DOCTOR_INTERVIEW":
        return await start_interview(doctor_id)
    return _MENU_EVENT_REPLIES.get(event_key, "请通过菜单或文字与我们互动。")


async def handle_name_lookup(name: str, doctor_id: str) -> str:
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
    if patient:
        set_current_patient(doctor_id, patient.id, patient.name)
        log(f"[WeChat] name lookup hit: {name} → patient_id={patient.id}")
        fake = IntentResult(intent=Intent.query_records, patient_name=name)
        return await handle_query_records(doctor_id, fake)

    set_pending_create(doctor_id, name)
    log(f"[WeChat] name lookup miss: {name} → pending create")
    return f"没找到{name}这位患者，请问性别和年龄？（或发送「取消」放弃）"


async def handle_pending_create(text: str, doctor_id: str) -> str:
    sess = get_session(doctor_id)
    name = sess.pending_create_name
    if text.strip() in ("取消", "cancel", "Cancel", "退出", "不要"):
        clear_pending_create(doctor_id)
        return "好的，已取消。"

    gender = None
    if re.search(r"男", text):
        gender = "男"
    elif re.search(r"女", text):
        gender = "女"
    age = None
    m = re.search(r"(\d+)\s*岁", text)
    if m:
        age = int(m.group(1))
    if gender is None and age is None:
        return f"还在为{name}建档，请补充性别和年龄（例如：男，17岁），或发送「取消」放弃。"

    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
        if patient is None:
            patient = await create_patient(session, doctor_id, name, gender, age)
        set_current_patient(doctor_id, patient.id, patient.name)

    clear_pending_create(doctor_id)
    parts = "、".join(filter(None, [gender, f"{age}岁" if age else None]))
    info = f"（{parts}）" if parts else ""
    return f"好的，{name}已建档{info}。"


async def handle_list_tasks(doctor_id: str) -> str:
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


async def handle_complete_task(doctor_id: str, intent_result: IntentResult) -> str:
    task_id = intent_result.extra_data.get("task_id")
    if not isinstance(task_id, int):
        return "⚠️ 未能识别任务编号，请发送「完成 5」（5为任务编号）。"
    async with AsyncSessionLocal() as session:
        task = await update_task_status(session, task_id, doctor_id, "completed")
    if task is None:
        return f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。"
    return intent_result.chat_reply or "好的，任务完成了。"


async def handle_schedule_appointment(doctor_id: str, intent_result: IntentResult) -> str:
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
    task = await create_appointment_task(doctor_id, patient_name, appointment_dt, notes)
    return (
        f"📅 已为患者【{patient_name}】安排预约\n"
        f"预约时间：{appointment_dt.strftime('%Y-%m-%d %H:%M')}\n"
        f"任务编号：{task.id}（将在1小时前提醒）"
    )


def wecom_kf_msg_to_text(msg: Dict[str, Any]) -> str:
    msgtype = str(msg.get("msgtype", "")).lower()
    if msgtype == "text":
        return str((msg.get("text") or {}).get("content") or "").strip()
    if msgtype == "voice":
        rec = str((msg.get("voice") or {}).get("recognition") or "").strip()
        return rec or "[语音消息]"
    if msgtype == "image":
        return "[图片消息]"
    if msgtype == "file":
        filename = str((msg.get("file") or {}).get("filename") or "").strip()
        return f"[文件消息]{(' ' + filename) if filename else ''}"
    if msgtype == "location":
        location = msg.get("location") or {}
        title = str(location.get("title") or location.get("name") or "").strip()
        addr = str(location.get("address") or "").strip()
        return f"[位置消息] {title or addr}".strip()
    if msgtype == "link":
        link = msg.get("link") or {}
        title = str(link.get("title") or "").strip()
        url = str(link.get("url") or "").strip()
        return f"[链接消息] {title or url}".strip()
    if msgtype in ("weapp", "miniprogram"):
        app = msg.get("weapp") or msg.get("miniprogram") or {}
        title = str(app.get("title") or "").strip()
        page = str(app.get("pagepath") or "").strip()
        return f"[小程序消息] {title or page}".strip()
    if msgtype == "video":
        return "[视频消息]"
    return ""


def wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    msgtype = str(msg.get("msgtype", "")).lower()
    if msgtype in ("text", "location", "link", "weapp", "miniprogram"):
        return bool(wecom_kf_msg_to_text(msg))
    if msgtype in ("voice", "image", "file", "video"):
        return True
    return bool(msgtype)


def wecom_msg_time(msg: Dict[str, Any]) -> int:
    for key in ("send_time", "create_time", "msg_time"):
        raw = msg.get(key)
        try:
            t = int(raw or 0)
            if t > 0:
                return t
        except (TypeError, ValueError):
            continue
    return 0
