import asyncio
import json
import os
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
from services.wechat_voice import download_and_convert, download_voice
from services.interview import InterviewState, STEPS
from services.intent import Intent, IntentResult
from services.agent import dispatch as agent_dispatch
from services.wechat_menu import create_menu
from services.wechat_notify import (
    _get_config, _get_access_token, _split_message,
    _send_customer_service_msg, _token_cache,
)
from services.session import (
    get_session,
    get_session_lock,
    push_turn,
    set_current_patient,
    set_pending_create,
    clear_pending_create,
    hydrate_session_state,
)
from services.memory import maybe_compress, load_context_message
from services.tasks import create_follow_up_task, create_emergency_task, create_appointment_task
from db.engine import AsyncSessionLocal
from db.crud import create_patient, find_patient_by_name, save_record, get_records_for_patient, get_all_records_for_doctor, get_all_patients, list_tasks, update_task_status
from utils.log import log

_COMPLETE_RE = re.compile(r'^完成\s*(\d+)$')
_NAME_TOKEN_RE = re.compile(r'^[\u4e00-\u9fff]{2,4}$')
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

router = APIRouter(prefix="/wechat", tags=["wechat"])
_WECHAT_KF_SYNC_CURSOR: str = ""
_WECHAT_KF_SEEN_MSG_IDS: set = set()
_WECHAT_KF_CURSOR_LOADED: bool = False
_WECHAT_KF_CURSOR_FILE = Path(__file__).resolve().parents[1] / "logs" / "wechat_kf_sync_state.json"


def _extract_open_kfid(msg) -> str:
    target = getattr(msg, "target", "")
    if isinstance(target, str):
        return target.strip()
    return ""


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
    candidate = text.strip()
    if _NAME_TOKEN_RE.match(candidate) and candidate not in _NON_NAME_TOKENS:
        if any(x in candidate for x in _NON_NAME_SUBSTRINGS):
            return ""
        return candidate
    return ""


def _explicit_name_or_none(text: str) -> str:
    for pat in _EXPLICIT_NAME_PATTERNS:
        m = pat.match(text.strip())
        if not m:
            continue
        name = m.group("name")
        return _name_token_or_none(name)
    return ""


def _looks_like_symptom_note(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if len(s) > 30:
        return False
    return any(k in s for k in _SYMPTOM_KEYWORDS)


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
        patient = await find_patient_by_name(session, doctor_id, name)
        if patient is None:
            patient = await create_patient(
                session, doctor_id, name, intent_result.gender, intent_result.age
            )
        set_current_patient(doctor_id, patient.id, patient.name)
    if patient and patient.name == name and intent_result.gender is None and intent_result.age is None:
        # Keep response concise and deterministic for repeat "new patient <name>" calls.
        return f"✅ 已切换到患者【{name}】，后续病历将自动关联该患者。"
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

    # Guardrail: avoid accidentally creating a patient from unrelated medical text.
    if gender is None and age is None:
        return (
            f"还在为{name}建档，请补充性别和年龄（例如：男，17岁），"
            "或发送「取消」放弃。"
        )

    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
        if patient is None:
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
        await _send_customer_service_msg(doctor_id, f"❌ 图片识别失败：{e}", open_kfid=open_kfid)
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
            log(f"[Vision] routing FAILED: {e}")
            result = "处理失败，请稍后重试。"
            route = "done"

    if route == "done":
        preview = text[:60] + ("…" if len(text) > 60 else "")
        await _send_customer_service_msg(doctor_id, f"🖼️ 「{preview}」\n\n{result}", open_kfid=open_kfid)
    else:
        # delegate — _handle_intent_bg acquires its own lock
        await _handle_intent_bg(text, doctor_id, open_kfid=open_kfid)


async def _handle_pdf_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    """Download PDF file, extract text, then route through normal pipeline."""
    cfg = _get_config()
    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        raw_bytes = await download_voice(media_id, access_token)
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, extract_text_from_pdf, raw_bytes)
    except Exception as e:
        log(f"[PDF] extraction FAILED: {e}")
        await _send_customer_service_msg(
            doctor_id,
            f"❌ PDF解析失败：{e}",
            open_kfid=open_kfid,
        )
        return

    if not text.strip():
        await _send_customer_service_msg(
            doctor_id,
            f"已收到《{filename or 'PDF文件'}》，但未提取到可读文本。请发送关键页面截图或粘贴主要内容。",
            open_kfid=open_kfid,
        )
        return

    preview = text[:80].replace("\n", " ")
    log(f"[PDF] extracted for {doctor_id}: {preview!r}")
    normalized = f"[PDF:{filename or 'uploaded.pdf'}]\n{text}"
    await _handle_intent_bg(normalized, doctor_id, open_kfid=open_kfid)


async def _handle_file_bg(media_id: str, filename: str, doctor_id: str, open_kfid: str = ""):
    """Download file and route by detected type (PDF supported)."""
    cfg = _get_config()
    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        raw_bytes = await download_voice(media_id, access_token)
    except Exception as e:
        log(f"[File] download FAILED: {e}")
        await _send_customer_service_msg(doctor_id, f"❌ 文件下载失败：{e}", open_kfid=open_kfid)
        return

    name = (filename or "").strip()
    lower_name = name.lower()
    is_pdf = lower_name.endswith(".pdf") or raw_bytes.startswith(b"%PDF")
    if is_pdf:
        await _handle_pdf_file_bg(media_id, name or "uploaded.pdf", doctor_id, open_kfid=open_kfid)
        return

    await _send_customer_service_msg(
        doctor_id,
        f"已收到文件《{name or '文件'}》。当前自动处理支持文字/语音/图片/PDF；其他文件请发送关键内容文本。",
        open_kfid=open_kfid,
    )


def _extract_cdata(xml_str: str, tag: str) -> str:
    m = re.search(rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", xml_str)
    if m:
        return m.group(1)
    m = re.search(rf"<{tag}>([^<]+)</{tag}>", xml_str)
    return m.group(1) if m else ""


def _wecom_kf_msg_to_text(msg: Dict[str, Any]) -> str:
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


def _wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    msgtype = str(msg.get("msgtype", "")).lower()
    if msgtype in ("text", "location", "link", "weapp", "miniprogram"):
        return bool(_wecom_kf_msg_to_text(msg))
    if msgtype == "voice":
        return True
    if msgtype == "image":
        return True
    if msgtype == "file":
        return True
    if msgtype == "video":
        return True
    return bool(msgtype)


def _wecom_msg_time(msg: Dict[str, Any]) -> int:
    for key in ("send_time", "create_time", "msg_time"):
        raw = msg.get(key)
        try:
            t = int(raw or 0)
            if t > 0:
                return t
        except (TypeError, ValueError):
            continue
    return 0


async def _handle_wecom_kf_event_bg(expected_msgid: str = "", event_create_time: int = 0) -> None:
    """Fetch latest WeCom KF customer messages and route through intent pipeline."""
    global _WECHAT_KF_SYNC_CURSOR, _WECHAT_KF_CURSOR_LOADED
    cfg = _get_config()
    if not cfg["app_id"] or not cfg["app_secret"]:
        log("[WeCom KF] skipped sync: app_id/app_secret missing")
        return

    if not _WECHAT_KF_CURSOR_LOADED:
        _WECHAT_KF_SYNC_CURSOR = _load_wecom_kf_sync_cursor() or _WECHAT_KF_SYNC_CURSOR
        _WECHAT_KF_CURSOR_LOADED = True

    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        cursor = _WECHAT_KF_SYNC_CURSOR
        next_cursor = _WECHAT_KF_SYNC_CURSOR
        max_pages = 5
        msg_list: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(max_pages):
                payload: Dict[str, Any] = {"limit": 100}
                if cursor:
                    payload["cursor"] = cursor
                resp = await client.post(
                    "https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg",
                    params={"access_token": access_token},
                    json=payload,
                )
                if hasattr(resp, "raise_for_status"):
                    resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict) or data.get("errcode", 0) != 0:
                    log(f"[WeCom KF] sync_msg failed: {data}")
                    return

                batch = data.get("msg_list") or []
                if isinstance(batch, list):
                    msg_list.extend(batch)

                batch_next_cursor = str(data.get("next_cursor") or "")
                if batch_next_cursor:
                    next_cursor = batch_next_cursor
                has_more = str(data.get("has_more") or "0") in ("1", "true", "True")
                if not has_more or not batch_next_cursor or batch_next_cursor == cursor:
                    break
                cursor = batch_next_cursor

        if next_cursor and next_cursor != _WECHAT_KF_SYNC_CURSOR:
            _WECHAT_KF_SYNC_CURSOR = next_cursor
            _persist_wecom_kf_sync_cursor(next_cursor)

        candidates: List[Dict[str, Any]] = []
        for raw in msg_list:
            if raw.get("origin") not in (3, "3"):
                continue
            msg_id = str(raw.get("msgid") or "")
            if msg_id and msg_id in _WECHAT_KF_SEEN_MSG_IDS:
                continue
            if not _wecom_msg_is_processable(raw):
                continue
            external_userid = str(raw.get("external_userid") or "")
            if not external_userid:
                continue
            candidates.append(raw)

        if not candidates:
            return

        selected = None
        if expected_msgid:
            for item in candidates:
                if str(item.get("msgid") or "") == expected_msgid:
                    selected = item
                    break
        timed_candidates = [m for m in candidates if _wecom_msg_time(m) > 0]

        if selected is None and event_create_time > 0 and timed_candidates:
            # Prefer message nearest to webhook event time to avoid replaying stale backlog.
            def _time_distance(item: Dict[str, Any]) -> int:
                return abs(_wecom_msg_time(item) - event_create_time)

            near = sorted(timed_candidates, key=_time_distance)
            if near and _time_distance(near[0]) <= 900:
                selected = near[0]
            else:
                # If callback has event time but fetched list is far away in time, skip it.
                # This avoids replaying stale backlog after restart.
                log(
                    "[WeCom KF] skip stale batch",
                    event_create_time=event_create_time,
                    closest_msg_time=_wecom_msg_time(near[0]) if near else 0,
                )
                return

        if selected is None:
            # Fallback: process newest unseen by timestamp; if unavailable, use last item.
            if timed_candidates:
                selected = max(timed_candidates, key=_wecom_msg_time)
            else:
                selected = candidates[-1]

        msg_id = str(selected.get("msgid") or "")
        external_userid = str(selected.get("external_userid") or "")
        open_kfid = str(selected.get("open_kfid") or "")
        msgtype = str(selected.get("msgtype") or "").lower()
        text = _wecom_kf_msg_to_text(selected)
        if not external_userid:
            return
        if msg_id:
            _WECHAT_KF_SEEN_MSG_IDS.add(msg_id)
            # Keep bounded memory.
            if len(_WECHAT_KF_SEEN_MSG_IDS) > 2000:
                _WECHAT_KF_SEEN_MSG_IDS.clear()
        if msgtype == "voice":
            voice = selected.get("voice") or {}
            recognition = str(voice.get("recognition") or "").strip()
            media_id = str(voice.get("media_id") or "").strip()
            if recognition:
                asyncio.create_task(_handle_intent_bg(recognition, external_userid, open_kfid=open_kfid))
                log(
                    f"[WeCom KF] queued voice(recognition) user={external_userid} kf={open_kfid} "
                    f"msgid={msg_id or 'n/a'} text={recognition[:80]!r}"
                )
                return
            if media_id:
                await _send_customer_service_msg(
                    external_userid,
                    "已收到语音，正在识别，请稍候。",
                    open_kfid=open_kfid,
                )
                asyncio.create_task(_handle_voice_bg(media_id, external_userid, open_kfid=open_kfid))
                log(
                    f"[WeCom KF] queued voice(media) user={external_userid} kf={open_kfid} "
                    f"msgid={msg_id or 'n/a'} media_id={media_id}"
                )
                return
            await _send_customer_service_msg(
                external_userid,
                "已收到语音，但未拿到语音文件ID，暂时无法识别。请重试发送。",
                open_kfid=open_kfid,
            )
            return
        if msgtype == "image":
            image = selected.get("image") or {}
            media_id = str(image.get("media_id") or "").strip()
            if media_id:
                await _send_customer_service_msg(
                    external_userid,
                    "已收到图片，正在识别文字，请稍候。",
                    open_kfid=open_kfid,
                )
                asyncio.create_task(_handle_image_bg(media_id, external_userid, open_kfid=open_kfid))
                log(
                    f"[WeCom KF] queued image(media) user={external_userid} kf={open_kfid} "
                    f"msgid={msg_id or 'n/a'} media_id={media_id}"
                )
                return
            await _send_customer_service_msg(
                external_userid,
                "已收到图片，但未拿到图片文件ID，暂时无法解析。请重试发送。",
                open_kfid=open_kfid,
            )
            return
        if msgtype == "file":
            filename = str((selected.get("file") or {}).get("filename") or "文件").strip()
            media_id = str((selected.get("file") or {}).get("media_id") or "").strip()
            if media_id:
                notice = f"已收到文件《{filename}》，正在识别并处理，请稍候。"
                await _send_customer_service_msg(external_userid, notice, open_kfid=open_kfid)
                asyncio.create_task(
                    _handle_file_bg(media_id, filename, external_userid, open_kfid=open_kfid)
                )
            else:
                await _send_customer_service_msg(
                    external_userid,
                    f"已收到文件《{filename}》，但未拿到文件ID，暂时无法解析。请重试或改发图片/文本。",
                    open_kfid=open_kfid,
                )
            log(
                f"[WeCom KF] file received user={external_userid} kf={open_kfid} "
                f"msgid={msg_id or 'n/a'} filename={filename!r} media_id={media_id or 'n/a'}"
            )
            return
        if msgtype == "video":
            await _send_customer_service_msg(
                external_userid,
                "已收到视频。当前暂不支持自动转写视频，请发送关键内容文字说明，我可继续处理。",
                open_kfid=open_kfid,
            )
            log(
                f"[WeCom KF] video received user={external_userid} kf={open_kfid} "
                f"msgid={msg_id or 'n/a'}"
            )
            return
        if not text:
            await _send_customer_service_msg(
                external_userid,
                f"已收到消息类型：{msgtype or 'unknown'}，当前暂不支持自动处理，请改发文字描述。",
                open_kfid=open_kfid,
            )
            return
        asyncio.create_task(_handle_intent_bg(text, external_userid, open_kfid=open_kfid))
        log(
            f"[WeCom KF] queued inbound text user={external_userid} kf={open_kfid} "
            f"msgid={msg_id or 'n/a'} expected_msgid={expected_msgid or 'n/a'} "
            f"event_create_time={event_create_time or 0} msg_time={_wecom_msg_time(selected)} text={text!r}"
        )
    except Exception as e:
        log(f"[WeCom KF] sync processing FAILED: {e}")


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
        try:
            event_create_time = int(create_time_raw) if create_time_raw else 0
        except ValueError:
            event_create_time = 0
        asyncio.create_task(
            _handle_wecom_kf_event_bg(
                expected_msgid=expected_msgid,
                event_create_time=event_create_time,
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
