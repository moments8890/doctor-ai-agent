"""
WeChat 意图处理层：创建患者、保存病历、查询、删除、引导问诊和历史导入的业务逻辑。
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.crud import (
    create_patient,
    create_pending_record,
    create_pending_import,
    delete_patient_for_doctor,
    find_patient_by_name,
    find_patients_by_exact_name,
    get_all_patients,
    get_all_records_for_doctor,
    get_records_for_patient,
    list_tasks,
    save_record,
    update_task_status,
)
from db.engine import AsyncSessionLocal
from services.ai.agent import dispatch as agent_dispatch
from services.observability.audit import audit
from services.knowledge.doctor_knowledge import maybe_auto_learn_knowledge
from services.ai.intent import Intent, IntentResult
from services.patient.interview import InterviewState, STEPS
from utils.response_formatting import format_draft_preview, format_record
from services.session import (
    clear_pending_create,
    get_session,
    set_current_patient,
    set_pending_create,
    set_pending_record_id,
    set_pending_import_id,
    clear_pending_import_id,
)
from services.ai.structuring import structure_medical_record
from services.notify.tasks import create_appointment_task, create_emergency_task, create_follow_up_task
from utils.text_parsing import (
    explicit_name_or_none,
    looks_like_symptom_note,
    name_token_or_none,
)
from utils.log import log


def _t(s: str | None, n: int = 30) -> str:
    """Truncate string for mobile display."""
    if not s:
        return ""
    return s[:n] + "…" if len(s) > n else s


_DRAFT_TTL_MINUTES = int(__import__("os").environ.get("PENDING_RECORD_TTL_MINUTES", "10"))

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
        return "⚠️ 未识别到患者姓名\n例：张三，30岁男性"
    created = False
    patient_id = None
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
        if patient is None:
            patient = await create_patient(session, doctor_id, name, intent_result.gender, intent_result.age)
            created = True
        patient_id = patient.id
        set_current_patient(doctor_id, patient.id, patient.name)
    if created:
        asyncio.create_task(audit(doctor_id, "WRITE", resource_type="patient", resource_id=str(patient_id)))
    if not created and intent_result.gender is None and intent_result.age is None:
        return f"✅ 已切换到患者【{name}】。\n后续病历自动关联。"
    age_str = f"，{intent_result.age}岁" if intent_result.age else ""
    gender_str = f"，{intent_result.gender}性" if intent_result.gender else ""
    return f"✅ 已为患者【{name}】建档{gender_str}{age_str}。\n后续病历自动关联。"


async def handle_add_record(
    text: str,
    doctor_id: str,
    intent_result: IntentResult,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Structure a medical record and save it as a pending draft for doctor confirmation."""
    from models.medical_record import MedicalRecord

    patient_id = None
    patient_name = None
    new_patient_created = False
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
                new_patient_created = True
                set_current_patient(doctor_id, patient.id, patient.name)
                log(f"[WeChat] auto-created patient [{patient_name}] id={patient_id}")

        if patient_id is None:
            sess = get_session(doctor_id)
            patient_id = sess.current_patient_id
            patient_name = sess.current_patient_name

    if new_patient_created:
        asyncio.create_task(audit(doctor_id, "WRITE", resource_type="patient", resource_id=str(patient_id)))

    # Structure the record
    if intent_result.structured_fields:
        fields = dict(intent_result.structured_fields)
        content_text = (fields.get("content") or text).strip() or "门诊就诊"
        record = MedicalRecord(content=content_text, record_type="dictation")
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

    # Emergency records skip the confirmation gate — saved immediately
    if intent_result.is_emergency:
        async with AsyncSessionLocal() as session:
            db_record = await save_record(session, doctor_id, record, patient_id)
        asyncio.create_task(audit(doctor_id, "WRITE", resource_type="record", resource_id=str(patient_id)))
        asyncio.create_task(create_emergency_task(
            doctor_id, db_record.id, patient_name or "未关联患者", None, patient_id
        ))
        asyncio.create_task(_bg_auto_learn(doctor_id, text, record))
        reply = intent_result.chat_reply or (f"{patient_name}的病历已记录。" if patient_name else "病历已保存。")
        return "🚨 " + reply

    # Save as pending draft — doctor must confirm before it hits medical_records
    draft_id = uuid.uuid4().hex
    async with AsyncSessionLocal() as session:
        await create_pending_record(
            session,
            record_id=draft_id,
            doctor_id=doctor_id,
            draft_json=json.dumps(record.model_dump(), ensure_ascii=False),
            raw_input=text[:2000],
            patient_id=patient_id,
            patient_name=patient_name,
            ttl_minutes=_DRAFT_TTL_MINUTES,
        )
    set_pending_record_id(doctor_id, draft_id)

    return format_draft_preview(record, patient_name)


async def _bg_auto_learn(doctor_id: str, text: str, record: Any) -> None:
    """Run knowledge auto-learning in the background (non-blocking)."""
    try:
        async with AsyncSessionLocal() as session:
            await maybe_auto_learn_knowledge(
                session, doctor_id, text,
                structured_fields=record.model_dump(exclude_none=True),
            )
    except Exception as e:
        log(f"[WeChat] bg auto-learn FAILED doctor={doctor_id}: {e}")


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
            lines = [f"📂 【{patient_name}】最近 {len(records)} 条记录\n"]
            for i, r in enumerate(records, 1):
                date_str = r.created_at.strftime("%m-%d") if r.created_at else "?"
                snippet = _t(r.content or "—", 30)
                lines.append(f"{i}. {date_str} {snippet}")
            return "\n".join(lines)

        records = await get_all_records_for_doctor(session, doctor_id)

    if not records:
        return "📂 暂无任何病历记录。"
    lines = [f"📂 所有患者最近 {len(records)} 条记录\n"]
    for i, r in enumerate(records, 1):
        pname = r.patient.name if r.patient else "未关联患者"
        date_str = r.created_at.strftime("%m-%d") if r.created_at else "?"
        snippet = _t(r.content or "—", 30)
        lines.append(f"{i}. 【{pname}】{date_str} {snippet}")
    return "\n".join(lines)


async def handle_all_patients(doctor_id: str) -> str:
    async with AsyncSessionLocal() as session:
        patients = await get_all_patients(session, doctor_id)
    if not patients:
        return "📂 暂无患者记录。发送「新患者姓名，年龄性别」可创建第一位患者。"
    lines = [f"👥 共 {len(patients)} 位患者\n"]
    for i, p in enumerate(patients, 1):
        age_display = f"{datetime.now().year - p.year_of_birth}岁" if p.year_of_birth else ""
        parts = [x for x in [p.gender, age_display] if x]
        info = "·".join(parts)
        suffix = f"（{info}）" if info else ""
        lines.append(f"{i}. {p.name}{suffix}")
    lines.append("\n发「查询[姓名]」看病历")
    return "\n".join(lines)


async def handle_delete_patient(doctor_id: str, intent_result: IntentResult) -> str:
    name = (intent_result.patient_name or "").strip()
    occurrence_raw = intent_result.extra_data.get("occurrence_index")
    occurrence_index = occurrence_raw if isinstance(occurrence_raw, int) else None
    if not name:
        return "⚠️ 请告诉我要删除的患者姓名，例如：删除患者张三。"

    async with AsyncSessionLocal() as session:
        matches = await find_patients_by_exact_name(session, doctor_id, name)
        if not matches:
            return f"⚠️ 未找到患者【{name}】。"
        if occurrence_index is None and len(matches) > 1:
            return f"⚠️ 找到同名患者【{name}】共 {len(matches)} 位，请发送「删除第2个患者{name}」。"
        if occurrence_index is not None:
            if occurrence_index <= 0 or occurrence_index > len(matches):
                return f"⚠️ 序号超出范围。同名患者【{name}】共 {len(matches)} 位。"
            target = matches[occurrence_index - 1]
        else:
            target = matches[0]

        deleted = await delete_patient_for_doctor(session, doctor_id, target.id)
    if deleted is None:
        return f"⚠️ 删除失败，未找到患者【{name}】。"
    asyncio.create_task(audit(doctor_id, "DELETE", resource_type="patient", resource_id=str(deleted.id)))
    return intent_result.chat_reply or f"✅ 已删除患者【{deleted.name}】(ID {deleted.id}) 及其相关记录。"


async def start_interview(doctor_id: str) -> str:
    sess = get_session(doctor_id)
    sess.interview = InterviewState()
    return f"🩺 开始问诊\n发「取消」随时结束\n\n[1/{len(STEPS)}] {STEPS[0][1]}"


async def handle_interview_step(text: str, doctor_id: str) -> str:
    if text.strip() in ("取消", "退出", "结束", "cancel"):
        get_session(doctor_id).interview = None
        return "好的，问诊结束了。"

    sess = get_session(doctor_id)
    iv = sess.interview
    iv.record_answer(text)
    if iv.active:
        return f"{iv.progress}\n{iv.current_question}"

    compiled = iv.compile_text()
    patient_name = iv.patient_name
    sess.interview = None
    log(f"[Interview] complete, compiled: {compiled}")
    try:
        record = await structure_medical_record(compiled)
    except Exception as e:
        log(f"[Interview] structuring FAILED: {e}")
        return "❌ 病历生成失败，请重新问诊。"

    patient_id = None
    async with AsyncSessionLocal() as session:
        patient = None
        if patient_name:
            patient = await find_patient_by_name(session, doctor_id, patient_name)
            if not patient:
                patient = await create_patient(session, doctor_id, patient_name, None, None)
                asyncio.create_task(
                    audit(doctor_id, "WRITE", resource_type="patient", resource_id=str(patient.id))
                )
            set_current_patient(doctor_id, patient.id, patient.name)
        patient_id = patient.id if patient else None
        draft_id = uuid.uuid4().hex
        await create_pending_record(
            session,
            record_id=draft_id,
            doctor_id=doctor_id,
            draft_json=json.dumps(record.model_dump(), ensure_ascii=False),
            patient_id=patient_id,
            patient_name=patient_name,
            ttl_minutes=_DRAFT_TTL_MINUTES,
        )
    set_pending_record_id(doctor_id, draft_id)
    return format_draft_preview(record, patient_name)


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
        return f"还在为{name}建档\n请补充性别和年龄\n（如：男，17岁）\n或发「取消」放弃。"

    new_patient_id = None
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
        if patient is None:
            patient = await create_patient(session, doctor_id, name, gender, age)
            new_patient_id = patient.id
        set_current_patient(doctor_id, patient.id, patient.name)

    if new_patient_id is not None:
        asyncio.create_task(audit(doctor_id, "WRITE", resource_type="patient", resource_id=str(new_patient_id)))
    clear_pending_create(doctor_id)
    parts = "、".join(filter(None, [gender, f"{age}岁" if age else None]))
    info = f"（{parts}）" if parts else ""
    return f"好的，{name}已建档{info}。"


async def handle_list_tasks(doctor_id: str) -> str:
    async with AsyncSessionLocal() as session:
        tasks = await list_tasks(session, doctor_id, status="pending")
    if not tasks:
        return "📋 暂无待办任务。"
    lines = [f"📋 待办任务 {len(tasks)}条\n"]
    for t in tasks:
        due = t.due_at.strftime('%m-%d') if t.due_at else ""
        due_str = f"  📅{due}" if due else ""
        lines.append(f"· {_t(t.title, 18)}{due_str}")
        lines.append(f"  #{t.id} · {t.task_type}")
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
        f"时间：{appointment_dt.strftime('%m-%d %H:%M')}\n"
        f"任务编号：{task.id}（1小时前提醒）"
    )


# ── History import helpers ────────────────────────────────────────────────────

import re as _re

_VISIT_BOUNDARY_RE = _re.compile(
    r"(?:^|\n)(?="
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}"   # 2023-11-01 / 2023年11月1日
    r"|第\d+次|初诊|复诊|【\d{4}"          # 第1次/初诊/复诊/【2023
    r")",
    _re.MULTILINE,
)

_DATE_IN_TEXT_RE = _re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}")


_CHAT_EXPORT_HEADER_RE = _re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(:\d{2})?\s+\S",
    _re.MULTILINE,
)


def _looks_like_chat_export(text: str) -> bool:
    """Heuristic: does the text look like a WeChat chat export?"""
    return bool(_CHAT_EXPORT_HEADER_RE.search(text[:2000]))


def _preprocess_import_text(
    text: str,
    source: str,
    sender_filter: str | None = None,
) -> str:
    """Strip media prefixes and clean WeChat chat export formatting."""
    # Strip [PDF:filename] / [Word:filename] prefix
    text = _re.sub(r"^\[(PDF|Word):[^\]]*\]\s*", "", text, flags=_re.IGNORECASE)
    if source == "chat_export" or _looks_like_chat_export(text):
        from services.wechat.wechat_media_pipeline import preprocess_wechat_chat_export
        text = preprocess_wechat_chat_export(text, sender_filter=sender_filter)
    elif _looks_like_structured_report(text):
        text = _preprocess_exam_report(text)
    return text.strip()


# Sections in 体检报告 that contain the clinically actionable summary.
# Must appear at the START of a line (with optional section number prefix).
# Covers: 江南大学附属医院, 爱康国宾, and common national templates.
_EXAM_SUMMARY_RE = _re.compile(
    r"(?:^|\n)(?:\d+[.．、]\s*)?(?:"
    r"检查综述|体检结论|健康评估|主要.*?问题|检查结论|体检小结"
    r"|体检重要异常结果|阳性结果和异常情况|异常结果及建议"
    r"|重要检查结论|体检报告总结"
    r")",
    _re.MULTILINE,
)
# 体检报告 header junk: lines before the clinical summary
_EXAM_HEADER_JUNK_RE = _re.compile(
    r"^[\s姓名身份证单位部门工号体检号电话日期年月\d\*\-（）()\s江南大学附属医院健康体检报告您的健康我们共同目标页共您的健康:：]+$",
)


def _preprocess_exam_report(text: str) -> str:
    """Extract clinically relevant sections from a 体检报告.

    Keeps: 检查综述, 主要/次要健康问题, 体检结论及建议.
    Discards: header junk, raw lab tables (too large for LLM).
    """
    # Find where the clinical summary starts (line-anchored — won't match inline text).
    # TOC entries in 爱康国宾 use spaces (`1      体检...`) not period (`1. 体检...`),
    # so they're skipped by the (?:\d+[.．、]\s*)? prefix requirement in the regex.
    m = _EXAM_SUMMARY_RE.search(text)
    if not m:
        return text  # can't identify structure — pass as-is
    # m.start() may point to the leading \n — find the actual keyword start
    body_start = m.start() + (1 if text[m.start()] in "\n\r" else 0)

    # Get patient identity from the full header (everything before the body section)
    header = text[:body_start]
    # Extract name, gender, age, date from header (multiple format support)
    name_m = _re.search(r"姓\s*名\s+(\S+)", header) or _re.search(r"REPORT\s+(\S{2,4})\s+(?:女士|先生|男士)", header)
    gender_m = _re.search(r"性别\s+([男女])", header) or _re.search(r"(\S{2,4})\s+(女士|先生)", header)
    age_m = _re.search(r"年龄\s+(\d+\s*岁?)", header)
    date_m = _re.search(r"体检日期\s+(\S+)", header) or _re.search(r"(\d{4}年\d{1,2}月\d{1,2}日)的体检报告", header)

    identity_parts = []
    if name_m:
        identity_parts.append(f"姓名：{name_m.group(1)}")
    if gender_m:
        # gender_m.group(1) may be name, group(2) may be 女士/先生 — normalize
        raw_gender = gender_m.group(2) if gender_m.lastindex and gender_m.lastindex >= 2 else gender_m.group(1)
        gender_val = "女" if "女" in raw_gender else ("男" if "男" in raw_gender else raw_gender)
        identity_parts.append(f"性别：{gender_val}")
    if age_m:
        identity_parts.append(f"年龄：{age_m.group(1)}")
    if date_m:
        identity_parts.append(f"体检日期：{date_m.group(1)}")

    identity_line = "  ".join(identity_parts) if identity_parts else ""

    # Keep only from the summary onwards, up to reasonable length
    clinical = text[body_start:].strip()

    # Discard raw data tables after the conclusion / expert advice section
    # Matches common stopping points: 江南大学 format + 爱康国宾 detailed results section
    conclusion_m = _re.search(
        r"(?:体检结论|健康建议|医师签名"
        r"|(?:^|\n)\s*3[\s、.．]+健康体检结果"   # 爱康国宾 section 3 (raw detailed tables)
        r"|(?:^|\n)\s*[三3][\s、.．]+检查详细"   # alternative heading
        r")",
        clinical,
        _re.MULTILINE,
    )
    if conclusion_m:
        # Keep up to end of conclusion section (next 2000 chars)
        clinical = clinical[:conclusion_m.start() + 2000]

    result = (identity_line + "\n\n" + clinical).strip() if identity_line else clinical
    return result


# Structured single-document report markers: header fields that indicate the
# entire text is ONE encounter (体检报告, 化验单, 出院记录, 影像报告 etc.)
_STRUCTURED_REPORT_RE = _re.compile(
    r"(?:"
    # Standard form layout: 姓名 ... 性别/年龄 nearby
    r"(?:姓\s*名|患者姓名|检查日期|报告日期|体检编号|住院号|门诊号|标本编号|送检日期)"
    r".{0,20}"
    r"(?:性\s*别|年\s*龄|科\s*室|床\s*号|检查者)"
    r"|"
    # 爱康国宾 / 美年健康 inline format: "健康体检报告" + 体检号
    r"(?:健康体检报告|MEDICAL EXAMINATION REPORT).{0,60}(?:体检号|用户ID|检查日期)"
    r")",
    _re.DOTALL,
)
# Section headers found in structured reports (【血常规】, 一、检查结果, 1  体检重要异常 etc.)
_REPORT_SECTION_RE = _re.compile(
    r"(?:^|\n)【[^】]{2,12}】"
    r"|(?:^|\n)[一二三四五六七八九十]+[、.．]\s*\S"
    r"|(?:^|\n)\d+\s{2,}[\u4e00-\u9fff]"  # Arabic numeral + spaces + Chinese (爱康国宾 TOC)
)


def _looks_like_structured_report(text: str) -> bool:
    """Return True if text is a single structured report (体检报告, 化验单, etc.)
    that should be kept as one chunk rather than split by paragraphs."""
    sample = text[:1500]
    return bool(_STRUCTURED_REPORT_RE.search(sample)) and bool(_REPORT_SECTION_RE.search(sample))


def _chunk_history_text(text: str) -> list[str]:
    """Split bulk history text into individual visit chunks.

    Strategy:
    0. Detect single structured reports (体检报告, 化验单) → return as-is.
    1. Try splitting on date/visit boundaries (most reliable).
    2. Fall back to paragraph splitting (double newline).
    3. If single block, return as-is.
    """
    # ── Strategy 0: structured single-document report ────────────────────────
    if _looks_like_structured_report(text):
        return [text]

    # _VISIT_BOUNDARY_RE uses (?:^|\n)(?=...) so m.start() may land on a \n;
    # adjust each boundary to point to the actual first character of the section.
    raw_boundaries = [m.start() for m in _VISIT_BOUNDARY_RE.finditer(text)]
    boundaries: list[int] = []
    for pos in raw_boundaries:
        actual = pos + 1 if pos < len(text) and text[pos] == "\n" else pos
        if not boundaries or actual != boundaries[-1]:
            boundaries.append(actual)

    # ── Strategy 1: paragraph splitting (blank lines) ────────────────────────
    # Split on blank lines first; this cleanly separates visits when the doctor
    # has already separated them with empty lines.
    paragraphs = [p.strip() for p in _re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) >= 2:
        # Only merge truly tiny stub fragments (< 15 chars) into the following
        # paragraph.  Keep normal-length paragraphs as separate visit chunks.
        merged: list[str] = []
        buf = ""
        for p in paragraphs:
            if buf and len(buf) < 15:
                buf = (buf + "\n" + p).strip()
            else:
                if buf:
                    merged.append(buf)
                buf = p
        if buf:
            merged.append(buf)
        if len(merged) >= 2:
            return merged

    # ── Strategy 2: date/keyword boundary regex ───────────────────────────────
    if len(boundaries) >= 2:
        raw_chunks: list[str] = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            chunk = text[start:end].strip()
            if chunk:
                raw_chunks.append(chunk)
        # Merge adjacent short fragments into the next one.
        sections: list[str] = []
        buf = ""
        for chunk in raw_chunks:
            buf = (buf + "\n" + chunk).strip() if buf else chunk
            if len(buf) >= 40:
                sections.append(buf)
                buf = ""
        if buf:
            if sections:
                sections[-1] = (sections[-1] + "\n" + buf).strip()
            else:
                sections.append(buf)
        if len(sections) >= 2:
            return sections

    return [text]


def _extract_chunk_date(chunk: str) -> str | None:
    """Extract the first date string from a chunk for display."""
    m = _DATE_IN_TEXT_RE.search(chunk)
    return m.group(0) if m else None


async def _mark_duplicates(
    chunks: list[dict],
    doctor_id: str,
    patient_id: int,
) -> list[dict]:
    """Mark chunks that appear to duplicate existing records."""
    async with AsyncSessionLocal() as session:
        existing = await get_records_for_patient(session, doctor_id, patient_id)
    if not existing:
        return chunks
    for chunk in chunks:
        s = chunk.get("structured", {})
        cc = (s.get("chief_complaint") or "").strip().lower()
        if not cc:
            continue
        for rec in existing:
            existing_cc = (rec.chief_complaint or "").strip().lower()
            if cc and existing_cc and (cc in existing_cc or existing_cc in cc):
                chunk["status"] = "duplicate"
                break
    return chunks


def _format_import_preview(
    chunks: list[dict],
    patient_name: str | None,
    source: str,
) -> str:
    """Build the confirmation message shown to the doctor."""
    source_label = {
        "pdf": "PDF文件",
        "word": "Word文件",
        "voice": "语音",
        "chat_export": "微信聊天记录",
    }.get(source, "文字")
    name_part = f"患者【{patient_name}】" if patient_name else "未关联患者"
    total = len(chunks)
    dup_count = sum(1 for c in chunks if c["status"] == "duplicate")
    new_count = total - dup_count

    lines = [f"📂 {name_part}历史记录\n共 {total} 条（来自{source_label}）\n"]
    ICONS = ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10."]
    for i, chunk in enumerate(chunks):
        s = chunk.get("structured", {})
        icon = ICONS[i] if i < len(ICONS) else f"{i+1}."
        date_str = _extract_chunk_date(chunk.get("raw_text", "")) or "?"
        cc = _t(s.get("chief_complaint") or "—", 14)
        diag = _t(s.get("diagnosis") or "", 12)
        diag_part = f"·{diag}" if diag else ""
        dup_tag = "⚠️疑似重复" if chunk["status"] == "duplicate" else ""
        lines.append(f"{icon} {date_str} {cc}{diag_part} {dup_tag}".strip())

    lines.append("")
    if dup_count > 0:
        lines.append(f"{new_count} 条新记录，{dup_count} 条疑似重复。")
        lines.append("「确认导入」保存全部\n「跳过重复」仅存新记录\n「取消」放弃")
    else:
        lines.append(f"「确认导入」保存全部 {total} 条\n「取消」放弃")
    return "\n".join(lines)


async def handle_import_history(text: str, doctor_id: str, intent_result: IntentResult) -> str:
    """Handle bulk patient history import from PDF, Word, voice, or text."""
    source = intent_result.extra_data.get("source", "text")
    patient_name = intent_result.patient_name

    # Resolve patient from session if not in intent
    sess = get_session(doctor_id)
    patient_id: int | None = None
    if not patient_name and sess.current_patient_id:
        patient_id = sess.current_patient_id
        patient_name = sess.current_patient_name

    if patient_name and patient_id is None:
        async with AsyncSessionLocal() as session:
            patient = await find_patient_by_name(session, doctor_id, patient_name)
            if patient:
                patient_id = patient.id

    # For chat exports with multiple senders, ask which sender to import
    if source == "chat_export" or (source == "text" and _looks_like_chat_export(text)):
        from services.wechat.wechat_chat_export import list_senders
        senders = list_senders(text)
        sender_filter = intent_result.extra_data.get("sender_filter")
        if len(senders) > 1 and not sender_filter:
            sender_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(senders))
            return (
                f"检测到群聊记录，共 {len(senders)} 位发言人：\n{sender_list}\n\n"
                f"请回复发言人姓名或序号，指定导入哪位医生的记录。"
            )
        # Single sender or already selected
        clean_text = _preprocess_import_text(text, source, sender_filter=sender_filter or (senders[0] if senders else None))
    else:
        clean_text = _preprocess_import_text(text, source)

    chunks_raw = _chunk_history_text(clean_text)

    if not chunks_raw:
        return "未能从内容中提取有效病历记录，请检查格式后重试。"

    # Structure each chunk (cap at 10 to avoid excessive LLM calls)
    structured_chunks: list[dict] = []
    for i, chunk_text in enumerate(chunks_raw[:10]):
        try:
            record = await structure_medical_record(chunk_text)
            structured_chunks.append({
                "idx": i + 1,
                "raw_text": chunk_text[:600],
                "structured": record.model_dump(),
                "status": "pending",
            })
        except Exception as e:
            log(f"[Import] chunk {i+1} structuring FAILED doctor={doctor_id}: {e}")

    if not structured_chunks:
        return "未能解析病历内容，请确认文件是否包含可读文字后重试。"

    # Deduplicate
    if patient_id:
        structured_chunks = await _mark_duplicates(structured_chunks, doctor_id, patient_id)

    # Persist as PendingImport
    import_id = uuid.uuid4().hex
    async with AsyncSessionLocal() as session:
        await create_pending_import(
            session,
            import_id,
            doctor_id,
            patient_id=patient_id,
            patient_name=patient_name,
            source=source,
            chunks_json=json.dumps(structured_chunks, ensure_ascii=False),
            ttl_minutes=30,
        )
    set_pending_import_id(doctor_id, import_id)

    # Build preview; prepend patient question if unknown
    preview = _format_import_preview(structured_chunks, patient_name, source)
    if patient_id is None:
        preview = (
            "未识别到患者姓名，请先告知患者姓名（如「这是张三的记录」），"
            "或直接回复「确认导入」关联到当前患者。\n\n" + preview
        )
    return preview


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
    if msgtype == "merged_msg":
        merged = msg.get("merged_msg") or {}
        title = str(merged.get("title") or "聊天记录").strip()
        return f"[合并消息] {title}"
    return ""


def wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    msgtype = str(msg.get("msgtype", "")).lower()
    if msgtype in ("text", "location", "link", "weapp", "miniprogram"):
        return bool(wecom_kf_msg_to_text(msg))
    if msgtype in ("voice", "image", "file", "video", "merged_msg"):
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
