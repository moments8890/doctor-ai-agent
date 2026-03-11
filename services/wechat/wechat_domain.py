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
    confirm_pending_record,
    delete_patient_for_doctor,
    find_patient_by_name,
    find_patients_by_exact_name,
    get_all_patients,
    get_all_records_for_doctor,
    get_records_for_patient,
    get_task_by_id,
    list_tasks,
    save_record,
    update_task_due_at,
    update_task_status,
)
from db.engine import AsyncSessionLocal
from db.crud.records import update_latest_record_for_patient
from services.ai.agent import dispatch as agent_dispatch
from services.observability.audit import audit
from services.knowledge.doctor_knowledge import maybe_auto_learn_knowledge
from services.ai.intent import Intent, IntentResult
from services.patient.interview import InterviewState, STEPS
from utils.response_formatting import format_draft_preview, format_record
from services.session import (
    clear_pending_create,
    get_session,
    hydrate_session_state,
    set_current_patient,
    set_pending_create,
    set_pending_record_id,
)
from services.ai.structuring import structure_medical_record
from services.domain.record_ops import assemble_record
from services.patient.score_extraction import detect_score_keywords, extract_specialty_scores
from services.notify.tasks import create_appointment_task, create_emergency_task, create_follow_up_task
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


def _t(s: str | None, n: int = 30) -> str:
    """Truncate string for mobile display."""
    if not s:
        return ""
    return s[:n] + "…" if len(s) > n else s


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
        _prev = set_current_patient(doctor_id, patient.id, patient.name)
    if created:
        asyncio.create_task(audit(doctor_id, "WRITE", resource_type="patient", resource_id=str(patient_id)))
    if not created and intent_result.gender is None and intent_result.age is None:
        return f"✅ 已切换到患者【{name}】。\n后续病历自动关联。"
    _switch = f"🔄 已从【{_prev}】切换\n" if _prev else ""
    age_str = f"，{intent_result.age}岁" if intent_result.age else ""
    gender_str = f"，{intent_result.gender}性" if intent_result.gender else ""
    return f"{_switch}✅ 已为患者【{name}】建档{gender_str}{age_str}。\n后续病历自动关联。"



async def _resolve_add_record_patient(doctor_id, intent_result):
    """Resolve patient for add_record. Returns (patient_id, patient_name, new_patient_created, switched_from)."""
    _sess_check = get_session(doctor_id)
    if (intent_result.patient_name and _sess_check.current_patient_name
            and intent_result.patient_name == _sess_check.current_patient_name
            and _sess_check.current_patient_id is not None):
        pid = _sess_check.current_patient_id
        pname = _sess_check.current_patient_name
        set_current_patient(doctor_id, pid, pname)
        return pid, pname, False, None
    if intent_result.patient_name:
        async with AsyncSessionLocal() as session:
            patient = await find_patient_by_name(session, doctor_id, intent_result.patient_name)
            if patient:
                _prev = set_current_patient(doctor_id, patient.id, patient.name)
                return patient.id, patient.name, False, _prev
            patient = await create_patient(
                session, doctor_id, intent_result.patient_name,
                intent_result.gender, intent_result.age,
            )
            _prev = set_current_patient(doctor_id, patient.id, patient.name)
            log(f"[WeChat] auto-created patient [{patient.name}] id={patient.id}")
            return patient.id, patient.name, True, _prev
    sess = get_session(doctor_id)
    return sess.current_patient_id, sess.current_patient_name, False, None


async def _build_record_from_text(text, history, doctor_id, patient_id):
    """Structure a medical record from doctor text + conversation history.

    Delegates to the shared assemble_record() which handles clinical context
    filtering, encounter-type detection, and prior-visit summary injection.
    """
    from services.ai.intent import IntentResult, Intent
    # Wrap as IntentResult with no structured_fields so assemble_record
    # takes the LLM structuring path with full clinical context filtering.
    stub = IntentResult(intent=Intent.add_record)
    return await assemble_record(stub, text, history, doctor_id, patient_id=patient_id)


async def _save_emergency_record(doctor_id, record, patient_id, patient_name, text, intent_result):
    """紧急病历直接保存，不经于确认门。"""
    log(
        f"[silent-save] emergency record saved WITHOUT confirmation "
        f"doctor={doctor_id} patient={patient_name!r} patient_id={patient_id}"
    )
    async with AsyncSessionLocal() as session:
        db_record = await save_record(session, doctor_id, record, patient_id)
    asyncio.create_task(audit(doctor_id, "WRITE", resource_type="record", resource_id=str(patient_id)))
    asyncio.create_task(create_emergency_task(
        doctor_id, db_record.id, patient_name or "未关联患者", None, patient_id
    ))
    asyncio.create_task(_bg_auto_learn(doctor_id, text, record))
    reply = intent_result.chat_reply or (
        f"{patient_name}的病历已记录。" if patient_name else "病历已保存。"
    )
    return "🚨 " + reply


async def _save_draft_and_preview(doctor_id, record, patient_id, patient_name, intent_result):
    """将病历保存为待确认草稿并返回预览消息。"""
    cvd_raw = intent_result.extra_data.get("cvd_context")
    draft_data = record.model_dump()
    if cvd_raw:
        draft_data["cvd_context"] = cvd_raw
    draft_id = uuid.uuid4().hex
    async with AsyncSessionLocal() as session:
        await create_pending_record(
            session, record_id=draft_id, doctor_id=doctor_id,
            draft_json=json.dumps(draft_data, ensure_ascii=False),
            patient_id=patient_id, patient_name=patient_name, ttl_minutes=_DRAFT_TTL_MINUTES,
        )
    set_pending_record_id(doctor_id, draft_id)
    preview = format_draft_preview(record, patient_name)
    if cvd_raw:
        footer = "\n\n「撤销」可取消"
        try:
            from services.patient.prior_visit import _format_cvd_summary as _fmt_cvd
            cvd_str = _fmt_cvd(json.dumps(cvd_raw, ensure_ascii=False), None) or ""
        except Exception:
            cvd_str = ""
        if cvd_str:
            cvd_line = "\n" + cvd_str
            preview = (preview[:-len(footer)] + cvd_line + footer) if preview.endswith(footer) else preview + cvd_line
    return preview


async def handle_add_record(
    text: str,
    doctor_id: str,
    intent_result: IntentResult,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """将病历结构化并保存为待确认草稿。"""
    from db.models.medical_record import MedicalRecord

    # Force-refresh session from DB on write-capable intents to prevent
    # stale patient attribution in multi-device workflows.
    await hydrate_session_state(doctor_id, write_intent=True)

    patient_id, patient_name, new_patient_created, _switched_from = await _resolve_add_record_patient(
        doctor_id, intent_result
    )
    if new_patient_created:
        asyncio.create_task(
            audit(doctor_id, "WRITE", resource_type="patient", resource_id=str(patient_id))
        )

    if intent_result.structured_fields:
        fields = dict(intent_result.structured_fields)
        content_text = (fields.get("content") or text).strip() or "门诊就诊"
        record = MedicalRecord(content=content_text, record_type="dictation")
    else:
        try:
            record = await _build_record_from_text(text, history, doctor_id, patient_id)
        except ValueError:
            return "没能识别病历内容，请重新描述一下。"
        except Exception as e:
            log(f"[WeChat] structuring FAILED: {e}")
            return "不好意思，刚才出了点问题，能再说一遍吗？"

    if detect_score_keywords(text):
        try:
            record.specialty_scores = await extract_specialty_scores(record.content or text)
            if record.specialty_scores:
                log(f"[WeChat] extracted {len(record.specialty_scores)} specialty score(s)")
        except Exception as exc:
            log(f"[WeChat] score extraction failed (non-fatal): {exc}")

    if intent_result.is_emergency:
        reply = await _save_emergency_record(
            doctor_id, record, patient_id, patient_name, text, intent_result
        )
    else:
        reply = await _save_draft_and_preview(doctor_id, record, patient_id, patient_name, intent_result)
    if _switched_from:
        reply = f"🔄 已从【{_switched_from}】切换到【{patient_name}】\n{reply}"
    return reply


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

async def handle_query_records(doctor_id: str, intent_result: IntentResult) -> str:
    patient_id = None
    patient_name = None
    _prev = None

    async with AsyncSessionLocal() as session:
        if intent_result.patient_name:
            patient = await find_patient_by_name(session, doctor_id, intent_result.patient_name)
            if patient:
                patient_id = patient.id
                patient_name = patient.name
                # Pin queried patient so follow-up turns bind by ID.
                _prev = set_current_patient(doctor_id, patient.id, patient.name)

        if patient_id is None:
            sess = get_session(doctor_id)
            patient_id = sess.current_patient_id
            patient_name = sess.current_patient_name

        if patient_id is not None:
            _switch = f"🔄 已从【{_prev}】切换到【{patient_name}】\n" if _prev else ""
            records = await get_records_for_patient(session, doctor_id, patient_id)
            if not records:
                return f"{_switch}📂 患者【{patient_name}】暂无历史记录。"
            lines = [f"{_switch}📂 【{patient_name}】最近 {len(records)} 条记录\n"]
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


async def handle_name_lookup(name: str, doctor_id: str) -> str:
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, name)
    if patient:
        _prev = set_current_patient(doctor_id, patient.id, patient.name)
        log(f"[WeChat] name lookup hit: {name} → patient_id={patient.id}")
        fake = IntentResult(intent=Intent.query_records, patient_name=name)
        result = await handle_query_records(doctor_id, fake)
        if _prev:
            result = f"🔄 已从【{_prev}】切换到【{patient.name}】\n{result}"
        return result

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
            return await handle_add_record(text, doctor_id, fake_intent)
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


async def handle_schedule_follow_up(doctor_id: str, intent_result: IntentResult) -> str:
    """Create a standalone follow-up task for a patient without needing a record save."""
    from datetime import timedelta, timezone
    from services.notify.tasks import create_follow_up_task, extract_follow_up_days

    patient_name = intent_result.patient_name
    if not patient_name:
        return "⚠️ 未能识别患者姓名，请说明如「给张三设3个月后随访」"

    follow_up_plan = intent_result.extra_data.get("follow_up_plan") or "下次随访"

    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, patient_name)

    patient_id = patient.id if patient else None

    # Resolve due days from the follow_up_plan text
    days = extract_follow_up_days(follow_up_plan)
    task = await create_follow_up_task(
        doctor_id=doctor_id,
        record_id=0,          # no linked record
        patient_name=patient_name,
        follow_up_plan=follow_up_plan,
        patient_id=patient_id,
    )
    from datetime import datetime, timezone as tz
    due_str = task.due_at.strftime("%Y-%m-%d") if task.due_at else f"{days}天后"
    return (
        f"✅ 已为【{patient_name}】创建随访提醒\n"
        f"计划：{follow_up_plan}\n"
        f"到期：{due_str}（任务编号 {task.id}）"
    )


async def handle_cancel_task(doctor_id: str, intent_result: IntentResult) -> str:
    """Cancel a pending task by ID."""
    task_id = intent_result.extra_data.get("task_id")
    if not task_id:
        return "⚠️ 未能识别任务编号，请发送「取消任务 5」（5为任务编号）。"
    async with AsyncSessionLocal() as session:
        task = await update_task_status(session, task_id, doctor_id, "cancelled")
    if task is None:
        return f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。"
    return f"🚫 任务 {task_id}（{task.title}）已取消。"


async def handle_postpone_task(doctor_id: str, intent_result: IntentResult) -> str:
    """Push a task's due date forward by N days."""
    from datetime import timedelta, timezone
    from db.crud import update_task_due_at, get_task_by_id

    task_id = intent_result.extra_data.get("task_id")
    delta_days = intent_result.extra_data.get("delta_days", 7)
    if not task_id:
        return "⚠️ 未能识别任务编号，请发送「推迟任务 5 一周」。"

    async with AsyncSessionLocal() as session:
        task = await get_task_by_id(session, task_id, doctor_id)
        if task is None:
            return f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。"
        now = datetime.now(timezone.utc)
        base = task.due_at if task.due_at and task.due_at > now else now
        new_due = base + timedelta(days=delta_days)
        await update_task_due_at(session, task_id, doctor_id, new_due)

    return (
        f"⏰ 任务 {task_id}（{task.title}）已推迟 {delta_days} 天\n"
        f"新到期时间：{new_due.strftime('%Y-%m-%d')}"
    )


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


_CLINICAL_KEYS_ZH = {
    "chief_complaint": "主诉",
    "history_of_present_illness": "现病史",
    "past_medical_history": "既往史",
    "physical_examination": "体格检查",
    "auxiliary_examinations": "辅助检查",
    "diagnosis": "诊断",
    "treatment_plan": "治疗方案",
    "follow_up_plan": "随访计划",
}


async def _restructure_and_save_record(
    doctor_id: str,
    patient_id: int,
    patient_name: str,
    existing_content: str,
    fields: dict,
) -> str:
    """Re-structure the record with the given field corrections and save it."""
    correction_lines = "\n".join(
        f"{_CLINICAL_KEYS_ZH.get(k, k)}：{v}" for k, v in fields.items() if v
    )
    correction_text = (
        f"原有病历：\n{existing_content}\n\n"
        f"更正以下字段（以更正内容为准）：\n{correction_lines}"
    )
    try:
        new_record = await structure_medical_record(correction_text)
    except Exception as e:
        log(f"[WeChat] update_record re-structure FAILED doctor={doctor_id}: {e}")
        return "⚠️ 病历更正失败，请稍后重试。"
    async with AsyncSessionLocal() as session:
        await update_latest_record_for_patient(
            session, doctor_id, patient_id,
            {"content": new_record.content, "tags": new_record.tags},
        )
    updated_labels = "、".join(_CLINICAL_KEYS_ZH.get(k, k) for k in fields)
    return f"✅ 已更正患者【{patient_name}】最近一条病历\n更新字段：{updated_labels}"


async def handle_update_record(doctor_id: str, intent_result: IntentResult) -> str:
    """Re-structure the most recent record with the corrected fields applied."""
    patient_name = (intent_result.patient_name or "").strip()
    sess = get_session(doctor_id)
    if not patient_name and sess.current_patient_name:
        patient_name = sess.current_patient_name
    if not patient_name:
        return "⚠️ 未能识别患者姓名，请说明要更正哪位患者的病历。"
    fields = intent_result.structured_fields or {}
    if not fields:
        return "⚠️ 未能识别需要更正的字段内容，请重新描述。"
    async with AsyncSessionLocal() as session:
        patient = await find_patient_by_name(session, doctor_id, patient_name)
        if patient is None:
            return f"⚠️ 未找到患者【{patient_name}】，请确认姓名后重试。"
        existing = await update_latest_record_for_patient(session, doctor_id, patient.id, {})
    if existing is None:
        return f"⚠️ 患者【{patient_name}】暂无病历记录，无法更正。"
    return await _restructure_and_save_record(
        doctor_id, patient.id, patient_name, existing.content or "", fields
    )


# WeCom KF message parsing helpers (re-exported from wechat_bg)
from services.wechat.wechat_bg import wecom_kf_msg_to_text, wecom_msg_is_processable, wecom_msg_time
