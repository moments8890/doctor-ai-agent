"""
病历聊天意图处理器：create_patient、add_record、query_records 等核心意图的实现。

从 routers/records.py 分离，保持文件体积合规（< 800 行）。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from db.crud import (
    create_patient as db_create_patient,
    find_patient_by_name,
    find_patients_by_exact_name,
    get_all_patients,
    get_all_records_for_doctor,
    get_records_for_patient,
    save_record,
)
from db.crud.pending import create_pending_record
from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.ai.intent import IntentResult
from services.ai.structuring import structure_medical_record
from services.domain.record_ops import assemble_record
from services.domain.chat_constants import (
    CREATE_PREAMBLE_RE as _CREATE_PREAMBLE_RE,
    CLINICAL_CONTENT_HINTS as _CLINICAL_CONTENT_HINTS,
    REMINDER_IN_MSG_RE as _REMINDER_IN_MSG_RE,
)
from services.domain.name_utils import is_valid_patient_name, patient_name_from_history
from services.notify.tasks import create_general_task
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from services.session import (
    hydrate_session_state,
    set_current_patient, set_pending_record_id,
    set_patient_not_found, clear_candidate_patient, clear_patient_not_found,
)
from utils.errors import InvalidMedicalRecordError
from utils.log import log


# ChatResponse is imported lazily to avoid circular imports
def _chat_response(reply: str, **kwargs):
    from routers.records import ChatResponse
    return ChatResponse(reply=reply, **kwargs)


# ---------------------------------------------------------------------------
# Content classification helpers
# ---------------------------------------------------------------------------

def _contains_clinical_content(text: str) -> bool:
    return any(hint in (text or "") for hint in _CLINICAL_CONTENT_HINTS)


# ICU/PACU/bed-context detection for stricter anonymous draft rules.
_LOCATION_CONTEXT_RE = re.compile(
    r"(?:ICU|PACU|CCU|NICU|急诊|抢救室|手术室|监护室|留观|绿色通道"
    r"|\d+床|\d+号床|[A-Z]?\d+病房|[A-Z]?\d+号)",
    re.IGNORECASE,
)


def _has_clinical_location_context(text: str) -> bool:
    """Return True if text contains explicit clinical location markers (ICU, bed, ward)."""
    return bool(_LOCATION_CONTEXT_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

async def background_auto_learn(doctor_id: str, text: str, fields: dict) -> None:
    """Run knowledge auto-learning in the background after returning the response."""
    from services.knowledge.doctor_knowledge import maybe_auto_learn_knowledge
    try:
        async with AsyncSessionLocal() as db:
            await maybe_auto_learn_knowledge(db, doctor_id, text, structured_fields=fields)
    except Exception as e:
        log(f"[Chat] background auto-learn failed doctor={doctor_id}: {e}")


# ---------------------------------------------------------------------------
# create_patient intent handlers
# ---------------------------------------------------------------------------

async def handle_create_patient(
    body_text: str, original_text: str, doctor_id: str, intent_result: IntentResult,
):
    """创建：创建或复用患者档案，可附带病历和提醒任务。"""
    name = intent_result.patient_name
    if not name:
        return _chat_response("好的，请告诉我患者的姓名。")

    _yob = (datetime.now().year - intent_result.age) if intent_result.age else None
    async with AsyncSessionLocal() as db:
        _candidates = await find_patients_by_exact_name(db, doctor_id, name)

    if _yob is not None:
        yob_match = next((p for p in _candidates if p.year_of_birth == _yob), None)
        patient = yob_match or (_candidates[0] if _candidates else None)
    else:
        patient = _candidates[0] if _candidates else None

    reply, patient = await _create_or_reuse_patient(doctor_id, name, patient, intent_result)
    # Pin resolved patient to session → subsequent add_record turns bind by ID (Category C fix).
    set_current_patient(doctor_id, patient.id, patient.name)
    if _contains_clinical_content(body_text):
        reply = await _append_compound_record(doctor_id, patient, body_text, name, reply)
    _reminder_m = _REMINDER_IN_MSG_RE.search(original_text)
    if _reminder_m:
        reply = await _append_reminder_task(doctor_id, patient, name, _reminder_m, reply)
    return _chat_response(reply)


async def _create_or_reuse_patient(
    doctor_id: str, name: str, patient: Optional[object], intent_result: IntentResult,
) -> tuple[str, object]:
    """创建或复用已有患者，返回 (reply, patient)。"""
    if patient is not None:
        _age_str = (
            f"{datetime.now().year - patient.year_of_birth}岁"
            if patient.year_of_birth else None
        )
        parts = "、".join(filter(None, [patient.gender, _age_str]))
        reply = (
            f"ℹ️ 患者【{name}】已存在（ID {patient.id}"
            f"{('，' + parts) if parts else ''}），已复用现有档案。"
        )
        log(f"[Chat] reusing existing patient [{name}] id={patient.id} doctor={doctor_id}")
        return reply, patient

    with trace_block("router", "records.chat.create_patient", {"doctor_id": doctor_id, "patient_name": name}):
        try:
            async with AsyncSessionLocal() as db:
                patient = await db_create_patient(
                    db, doctor_id, name, intent_result.gender, intent_result.age
                )
        except InvalidMedicalRecordError as e:
            log(f"[Chat] create patient validation FAILED doctor={doctor_id}: {e}")
            raise HTTPException(status_code=422, detail="⚠️ 患者信息不完整或格式不正确，请检查后重试。") from e
    parts = "、".join(filter(None, [
        intent_result.gender,
        f"{intent_result.age}岁" if intent_result.age else None,
    ]))
    reply = f"✅ 已为患者【{patient.name}】创建" + (f"（{parts}）" if parts else "") + "。"
    log(f"[Chat] created patient [{patient.name}] id={patient.id} doctor={doctor_id}")
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="patient",
        resource_id=str(patient.id), trace_id=get_current_trace_id(),
    ))
    return reply, patient


async def _append_compound_record(
    doctor_id: str, patient: object, body_text: str, name: str, reply: str,
) -> str:
    """附加病历录入到创建回复中。"""
    try:
        _clinical_text = _CREATE_PREAMBLE_RE.sub("", body_text).strip() or body_text
        with trace_block("router", "records.chat.compound_record"):
            record = await structure_medical_record(_clinical_text)
        async with AsyncSessionLocal() as db:
            saved = await save_record(db, doctor_id, record, patient.id)
        preview = record.content[:50] + ("…" if len(record.content) > 50 else "")
        reply += f"\n✅ 已录入病历：{preview}"
        asyncio.create_task(audit(
            doctor_id, "WRITE", resource_type="record",
            resource_id=str(saved.id), trace_id=get_current_trace_id(),
        ))
        log(f"[Chat] compound record saved [{name}] record_id={saved.id} doctor={doctor_id}")
    except Exception as e:
        log(f"[Chat] compound record save FAILED doctor={doctor_id}: {e}")
        reply += "\n⚠️ 病历录入失败，请稍后单独补充。"
    return reply


async def _append_reminder_task(
    doctor_id: str, patient: object, name: str, reminder_match: re.Match, reply: str,
) -> str:
    """附加提醒任务到创建回复中。"""
    task_title_raw = reminder_match.group(1).strip().rstrip("。！")
    task_title = f"【{name}】{task_title_raw}"
    try:
        task = await create_general_task(doctor_id, task_title, patient_id=patient.id)
        reply += f"\n📋 已创建提醒任务：{task_title}（编号 {task.id}）"
        log(f"[Chat] compound task created [{task_title}] id={task.id} doctor={doctor_id}")
    except Exception as e:
        log(f"[Chat] compound task create FAILED doctor={doctor_id}: {e}")
    return reply


# ---------------------------------------------------------------------------
# add_record intent handlers
# ---------------------------------------------------------------------------

async def _persist_add_record_patient(
    db: object, doctor_id: str, patient_name: str, intent_result: IntentResult,
) -> tuple[object, bool]:
    """Find or create patient for add_record. Returns (patient_id or ChatResponse, created)."""
    if not patient_name:
        return None, False
    patient = await find_patient_by_name(db, doctor_id, patient_name)
    if not patient:
        try:
            patient = await db_create_patient(
                db, doctor_id, patient_name, intent_result.gender, intent_result.age,
            )
        except InvalidMedicalRecordError as e:
            log(f"[Chat] auto-create patient validation FAILED doctor={doctor_id}: {e}")
            return _chat_response("⚠️ 患者姓名格式无效，请更正后再试。"), False
        return patient.id, True
    updated = False
    if intent_result.gender and intent_result.gender != patient.gender:
        patient.gender = intent_result.gender
        updated = True
    if intent_result.age:
        from db.repositories.patients import _year_of_birth
        new_yob = _year_of_birth(intent_result.age)
        if new_yob and new_yob != patient.year_of_birth:
            patient.year_of_birth = new_yob
            updated = True
    if updated:
        log(f"[Chat] updated patient demographics [{patient_name}] doctor={doctor_id}")
    return patient.id, False


async def _build_record_from_input(
    text: str, history: list, intent_result: IntentResult,
    patient_name: str, doctor_id: str, followup_name: Optional[str],
    patient_id: Optional[int] = None,
) -> "MedicalRecord | object":
    """将意图结果转化为 MedicalRecord；失败返回 ChatResponse 错误。

    Delegates to the shared assemble_record() in record_ops which applies
    clinical context filtering, encounter-type detection, and prior-visit
    summary injection — same logic as the WeChat path.
    """
    # When the text is just a bare follow-up name, skip it to avoid feeding
    # a patient name as clinical content.  Pass None so assemble_record
    # uses history-only mode.
    effective_text: str | None = text
    if followup_name and text.strip() == followup_name:
        effective_text = None
    try:
        with trace_block("router", "records.chat.assemble_record"):
            return await assemble_record(
                intent_result, effective_text or "", history, doctor_id,
                patient_id=patient_id,
            )
    except Exception as e:
        log(f"[Chat] structuring FAILED doctor={doctor_id} patient={patient_name}: {e}")
        return _chat_response("病历生成失败，请稍后重试。")


async def _save_emergency_record(
    doctor_id: str, text: str, record: MedicalRecord,
    patient_id: int, patient_name: str, intent_result: IntentResult,
):
    """紧急病历：跳过确认直接保存并触发后台任务。"""
    async with AsyncSessionLocal() as db:
        saved = await save_record(db, doctor_id, record, patient_id)
    asyncio.create_task(background_auto_learn(doctor_id, text, record.model_dump(exclude_none=True)))
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="record",
        resource_id=str(saved.id), trace_id=get_current_trace_id(),
    ))
    reply = intent_result.chat_reply or f"🚨 紧急病历已为【{patient_name}】直接保存。"
    log(f"[Chat] emergency record saved patient={patient_name} doctor={doctor_id}")
    return _chat_response(reply, record=record)


async def _create_pending_draft(
    doctor_id: str, record: MedicalRecord, patient_id: int,
    patient_name: str, intent_result: IntentResult,
):
    """创建待确认草稿并返回提示回复。"""
    _draft_ttl = int(os.environ.get("PENDING_RECORD_TTL_MINUTES", "30"))
    draft_id = uuid.uuid4().hex
    draft_data = record.model_dump()
    _cvd_raw = (intent_result.extra_data or {}).get("cvd_context") if intent_result.extra_data else None
    if _cvd_raw:
        draft_data["cvd_context"] = _cvd_raw
    _expires_at = datetime.now(timezone.utc) + timedelta(minutes=_draft_ttl)
    async with AsyncSessionLocal() as db:
        await create_pending_record(
            db, record_id=draft_id, doctor_id=doctor_id,
            draft_json=json.dumps(draft_data, ensure_ascii=False),
            patient_id=patient_id, patient_name=patient_name, ttl_minutes=_draft_ttl,
        )
    set_pending_record_id(doctor_id, draft_id)
    reply = intent_result.chat_reply or f"📋 已为【{patient_name}】生成病历草稿，请确认后保存。"
    log(f"[Chat] pending draft created patient={patient_name} draft_id={draft_id} doctor={doctor_id}")
    return _chat_response(
        reply, record=record, pending_id=draft_id,
        pending_patient_name=patient_name, pending_expires_at=_expires_at.isoformat(),
    )


async def handle_add_record(
    text: str, doctor_id: str, history: list, intent_result: IntentResult,
    followup_name: Optional[str],
):
    """录入病历：解析患者、生成结构化病历并保存。

    Patient resolution: intent_result.patient_name is already backfilled from
    session by _apply_session_context when the session has current_patient_id
    (set by handle_create_patient / handle_query_records on prior turns).
    History scanning is a fallback when no session context exists.
    """
    # Force-refresh session from DB on write-capable intents to prevent
    # stale patient attribution in multi-device/multi-tab workflows.
    await hydrate_session_state(doctor_id, write_intent=True)

    if not intent_result.patient_name or not is_valid_patient_name(intent_result.patient_name):
        _hist_name = patient_name_from_history(history)
        if _hist_name:
            intent_result.patient_name = _hist_name
            log(f"[Chat] resolved patient from history: {_hist_name} doctor={doctor_id}")
        else:
            from services.session import get_session as _get_session
            _sess = _get_session(doctor_id)
            _sess_name = _sess.current_patient_name
            if _sess_name and is_valid_patient_name(_sess_name):
                intent_result.patient_name = _sess_name
                log(f"[Chat] resolved patient from session: {_sess_name} doctor={doctor_id}")
            else:
                # Weak-attribution fallback: candidate/not-found patient names
                # from ephemeral session state. Only allow when the message has
                # explicit clinical/location context (ICU, PACU, bed number) to
                # reduce the risk of silent mis-attribution.
                _cand_name = getattr(_sess, "candidate_patient_name", None)
                _not_found_name = getattr(_sess, "patient_not_found_name", None)
                _has_location_ctx = _has_clinical_location_context(text)
                if _cand_name and is_valid_patient_name(_cand_name):
                    intent_result.patient_name = _cand_name
                    if not intent_result.gender:
                        intent_result.gender = getattr(_sess, "candidate_patient_gender", None)
                    if not intent_result.age:
                        intent_result.age = getattr(_sess, "candidate_patient_age", None)
                    clear_candidate_patient(doctor_id)
                    intent_result.extra_data = intent_result.extra_data or {}
                    intent_result.extra_data["needs_review"] = True
                    intent_result.extra_data["attribution_source"] = "candidate"
                    log(f"[Chat] resolved patient from candidate: {_cand_name} doctor={doctor_id} location_ctx={_has_location_ctx}")
                    if not intent_result.chat_reply:
                        intent_result.chat_reply = (
                            f"⚠️ 已为候选患者【{_cand_name}】生成病历草稿，"
                            "请核实患者信息后确认保存。"
                        )
                elif _not_found_name and is_valid_patient_name(_not_found_name) and _has_location_ctx:
                    # Only auto-create from not-found when there is explicit
                    # clinical location context (ICU/PACU/bed).
                    intent_result.patient_name = _not_found_name
                    clear_patient_not_found(doctor_id)
                    intent_result.extra_data = intent_result.extra_data or {}
                    intent_result.extra_data["needs_review"] = True
                    intent_result.extra_data["attribution_source"] = "not_found_with_location"
                    log(f"[Chat] creating patient from not-found query: {_not_found_name} doctor={doctor_id}")
                    if not intent_result.chat_reply:
                        intent_result.chat_reply = (
                            f"⚠️ 未找到【{_not_found_name}】，已为新患者生成病历草稿，"
                            "请核实后确认保存。"
                        )
                elif _not_found_name and is_valid_patient_name(_not_found_name):
                    # No location context — force explicit patient resolution
                    # instead of hiding a potential attribution failure.
                    clear_patient_not_found(doctor_id)
                    log(f"[Chat] weak attribution blocked (no location ctx): {_not_found_name} doctor={doctor_id}")
                    return _chat_response(
                        f"未找到患者【{_not_found_name}】，请先创建患者或明确指定患者姓名。"
                    )
                else:
                    return _chat_response("请问这位患者叫什么名字？")

    patient_name = intent_result.patient_name
    from routers.records import ChatResponse

    # Resolve patient FIRST so assemble_record gets patient_id for encounter
    # type detection and prior-visit summary injection.
    with trace_block("router", "records.chat.persist_record", {"doctor_id": doctor_id, "patient_name": patient_name}):
        async with AsyncSessionLocal() as db:
            patient_id, _ = await _persist_add_record_patient(db, doctor_id, patient_name, intent_result)
            if isinstance(patient_id, ChatResponse):
                return patient_id

    # Pin resolved patient so follow-up turns bind by ID, not by re-scanning.
    if isinstance(patient_id, int):
        set_current_patient(doctor_id, patient_id, patient_name)

    record = await _build_record_from_input(
        text, history, intent_result, patient_name, doctor_id, followup_name,
        patient_id=patient_id,
    )
    if isinstance(record, ChatResponse):
        return record

    if getattr(intent_result, "is_emergency", False):
        return await _save_emergency_record(doctor_id, text, record, patient_id, patient_name, intent_result)
    return await _create_pending_draft(doctor_id, record, patient_id, patient_name, intent_result)


# ---------------------------------------------------------------------------
# query_records + list_patients intent handlers
# ---------------------------------------------------------------------------

async def handle_query_records(doctor_id: str, intent_result: IntentResult):
    """查询病历：按患者姓名或全量返回病历列表。"""
    name = intent_result.patient_name
    with trace_block("router", "records.chat.query_records", {"doctor_id": doctor_id, "patient_name": name}):
        async with AsyncSessionLocal() as db:
            if name:
                patient = await find_patient_by_name(db, doctor_id, name)
                if not patient:
                    set_patient_not_found(doctor_id, name)
                    return _chat_response(f"未找到患者【{name}】。")
                # Pin this patient to session so follow-up add_record turns can
                # resolve them without re-scanning history (fixes Category D).
                set_current_patient(doctor_id, patient.id, patient.name)
                records = await get_records_for_patient(db, doctor_id, patient.id)
                if not records:
                    return _chat_response(f"📂 患者【{name}】暂无历史记录。")
                lines = [f"📂 患者【{name}】最近 {len(records)} 条记录："]
                for i, r in enumerate(records, 1):
                    date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
                    lines.append(f"{i}. [{date}] {(r.content or '—')[:60]}")
            else:
                records = await get_all_records_for_doctor(db, doctor_id)
                if not records:
                    return _chat_response("📂 暂无任何病历记录。")
                lines = [f"📂 最近 {len(records)} 条记录："]
                for r in records:
                    pname = r.patient.name if r.patient else "未关联"
                    date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
                    lines.append(f"【{pname}】[{date}] {(r.content or '—')[:60]}")
    asyncio.create_task(audit(
        doctor_id, "READ", resource_type="record",
        resource_id=name, trace_id=get_current_trace_id(),
    ))
    return _chat_response("\n".join(lines))


async def handle_list_patients(doctor_id: str):
    """患者列表：展示全部患者基本信息。"""
    with trace_block("router", "records.chat.list_patients", {"doctor_id": doctor_id}):
        async with AsyncSessionLocal() as db:
            patients = await get_all_patients(db, doctor_id)
    if not patients:
        return _chat_response("📂 暂无患者记录。")
    lines = [f"👥 共 {len(patients)} 位患者："]
    for i, p in enumerate(patients, 1):
        age_display = f"{datetime.now().year - p.year_of_birth}岁" if p.year_of_birth else None
        info = "、".join(filter(None, [p.gender, age_display]))
        lines.append(f"{i}. {p.name}" + (f"（{info}）" if info else ""))
    return _chat_response("\n".join(lines))
