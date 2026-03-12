"""
WeChat 意图处理层：引导问诊、待确认病历保存、CVD量表回复和历史导入的业务逻辑。

Intent handling for create_patient, add_record, query_records, delete_patient,
list_tasks, complete_task, schedule_follow_up, cancel_task, postpone_task,
schedule_appointment, update_record, and name_lookup has been moved to the
shared handler layer at ``services/domain/intent_handlers/``.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from db.crud import (
    create_patient,
    create_pending_record,
    confirm_pending_record,
    find_patient_by_name,
    get_all_patients,
    save_record,
)
from db.engine import AsyncSessionLocal
from services.observability.audit import audit
from services.ai.intent import IntentResult
from services.patient.interview import InterviewState, STEPS
from utils.response_formatting import format_draft_preview, format_record
from services.session import (
    clear_pending_create,
    get_session,
    set_current_patient,
    set_pending_record_id,
)
from services.ai.structuring import structure_medical_record
from services.notify.tasks import create_follow_up_task
from utils.text_parsing import (
    explicit_name_or_none,
    looks_like_symptom_note,
    name_token_or_none,
)
from utils.log import log

# Re-export from sub-modules for backward compatibility
from services.wechat.wechat_export import (
    handle_export_records,
    handle_export_outpatient_report,
)
from services.wechat.wechat_import import (
    handle_import_history,
    _chunk_history_text,
    _preprocess_import_text,
    _format_import_preview,
    _mark_duplicates,
)


_DRAFT_TTL_MINUTES = int(__import__("os").environ.get("PENDING_RECORD_TTL_MINUTES", "30"))

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


async def _parse_pending_draft(pending, doctor_id):
    """解析草稿 JSON，返回 (record, cvd_raw) 或 None。"""
    from db.models.medical_record import MedicalRecord
    try:
        draft = json.loads(pending.draft_json)
        cvd_raw = draft.pop("cvd_context", None)
        record = MedicalRecord(**{k: draft.get(k) for k in MedicalRecord.model_fields})
        return record, cvd_raw
    except Exception as e:
        log(f"[PendingRecord] parse draft FAILED doctor={doctor_id} id={pending.id}: {e}")
        return None


async def _persist_pending_record(pending, record, cvd_raw, doctor_id):
    """将记录、分数、CVD上下文入库并确认草稿。返回 db_record 或 None。"""
    from db.models.neuro_case import NeuroCVDSurgicalContext
    try:
        async with AsyncSessionLocal() as session:
            db_record = await save_record(session, doctor_id, record, pending.patient_id)
            if record.specialty_scores:
                from db.crud.scores import save_specialty_scores
                await save_specialty_scores(session, db_record.id, doctor_id, record.specialty_scores)
            if cvd_raw:
                try:
                    from db.crud.specialty import save_cvd_context
                    cvd_ctx = NeuroCVDSurgicalContext.model_validate(cvd_raw)
                    if cvd_ctx.has_data():
                        await save_cvd_context(
                            session, doctor_id, pending.patient_id, db_record.id, cvd_ctx, source="chat"
                        )
                        log(f"[CVD] context saved inline for record={db_record.id}")
                except Exception as exc:
                    log(f"[CVD] inline save failed (non-fatal): {exc}")
            await confirm_pending_record(session, pending.id, doctor_id=doctor_id)
        return db_record
    except Exception as e:
        log(f"[PendingRecord] save FAILED doctor={doctor_id} id={pending.id}: {e}")
        return None


def _fire_post_save_tasks(doctor_id, record, record_id, patient_name, pending, cvd_raw):
    """将保存后的后台任务（审计、随访、自学习等）全部触发。"""
    asyncio.create_task(audit(doctor_id, "WRITE", resource_type="record", resource_id=str(record_id)))
    _follow_up_hint = next(
        (t for t in record.tags if "随访" in t or "复诊" in t), None
    ) or (("随访" in (record.content or "") or "复诊" in (record.content or "")) and record.content) or None
    if _follow_up_hint:
        asyncio.create_task(create_follow_up_task(
            doctor_id, record_id, patient_name, str(_follow_up_hint), pending.patient_id
        ))
    content = record.content or ""
    if content:
        asyncio.create_task(_bg_auto_tasks(
            doctor_id, record_id, patient_name, pending.patient_id, content
        ))
    raw_input = getattr(pending, "raw_input", None) or record.content or ""
    asyncio.create_task(_bg_auto_learn(doctor_id, raw_input, record))
    if not cvd_raw and _detect_cvd_keywords(raw_input):
        asyncio.create_task(_bg_extract_cvd_context(
            doctor_id, record_id, pending.patient_id, record.content or ""
        ))


async def save_pending_record(doctor_id: str, pending: Any) -> Optional[tuple]:
    """解析 PendingRecord 并保存到 medical_records。

    成功返回 (patient_name, record_id)，失败返回 None。
    副作用：触发审计、随访任务和自学习后台任务。
    不更改会话状态——调用方负责清除 pending_record_id。
    """
    parsed = await _parse_pending_draft(pending, doctor_id)
    if parsed is None:
        return None
    record, cvd_raw = parsed
    db_record = await _persist_pending_record(pending, record, cvd_raw, doctor_id)
    if db_record is None:
        return None
    patient_name = pending.patient_name or "未关联患者"
    record_id = db_record.id
    _fire_post_save_tasks(doctor_id, record, record_id, patient_name, pending, cvd_raw)
    return patient_name, record_id

async def handle_cvd_scale_reply(text: str, doctor_id: str) -> str:
    """Handle doctor reply to a pending CVD scale question."""
    from services.patient.cvd_scale_interview import CVDScaleSession
    from db.crud.specialty import upsert_cvd_field

    sess = get_session(doctor_id)
    cvd_sess: CVDScaleSession = sess.pending_cvd_scale
    sess.pending_cvd_scale = None  # always clear

    answer = cvd_sess.parse_answer(text)
    if answer is None:
        return "已跳过量表录入。"
    try:
        async with AsyncSessionLocal() as session:
            await upsert_cvd_field(
                session,
                record_id=cvd_sess.record_id,
                patient_id=cvd_sess.patient_id,
                doctor_id=doctor_id,
                field_name=cvd_sess.field_name,
                value=answer,
            )
        return f"✅ 已记录 {cvd_sess.field_label()}：{answer}分"
    except Exception as exc:
        log(f"[CVD scale] save failed (non-fatal): {exc}")
        return "已收到量表评分（保存失败，请稍后补录）。"


# CVD detection and background helpers (imported from wechat_bg for modularity)
from services.wechat.wechat_bg import (
    detect_cvd_keywords as _detect_cvd_keywords,
    bg_extract_cvd_context as _bg_extract_cvd_context,
    bg_auto_tasks as _bg_auto_tasks,
    bg_auto_learn as _bg_auto_learn,
)


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


async def start_interview(doctor_id: str) -> str:
    sess = get_session(doctor_id)
    sess.interview = InterviewState()
    return f"🩺 开始问诊\n发「取消」随时结束\n\n[1/{len(STEPS)}] {STEPS[0][1]}"


async def handle_interview_step(text: str, doctor_id: str) -> str:
    _EXIT_WORDS = {"取消", "退出", "结束", "cancel", "停止", "不要了", "中断", "重来", "stop", "终止", "算了", "放弃"}
    if text.strip() in _EXIT_WORDS:
        get_session(doctor_id).interview = None
        return "好的，问诊结束了。"

    sess = get_session(doctor_id)
    iv = sess.interview
    if iv is None:
        return "当前没有进行中的问诊，请先说「开始问诊」。"
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
        # If the message looks like clinical content, auto-create the patient and proceed
        from services.ai.fast_router import fast_route as _fast_route
        from services.ai.intent import Intent as _Intent
        _probe = _fast_route(text)
        if _probe is not None and _probe.intent == _Intent.add_record:
            async with AsyncSessionLocal() as session:
                patient = await find_patient_by_name(session, doctor_id, name)
                if patient is None:
                    patient = await create_patient(session, doctor_id, name, None, None)
                    asyncio.create_task(audit(doctor_id, "WRITE", resource_type="patient", resource_id=str(patient.id)))
                set_current_patient(doctor_id, patient.id, patient.name)
            clear_pending_create(doctor_id)
            fake_intent = IntentResult(intent=_Intent.add_record, patient_name=name)
            # Delegate to the shared add_record handler.
            from services.domain.intent_handlers import handle_add_record as _shared_add_record
            hr = await _shared_add_record(text, doctor_id, [], fake_intent)
            return hr.reply
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


# WeCom KF message parsing helpers (re-exported from wechat_bg)
from services.wechat.wechat_bg import wecom_kf_msg_to_text, wecom_msg_is_processable, wecom_msg_time
