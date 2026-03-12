"""
Unified add_record handler — channel-agnostic business logic.

Merges the Web (records_intent_handlers.py) and WeChat (wechat_domain.py)
add_record implementations into a single handler that returns HandlerResult.

Web-specific traits kept:
  - Comprehensive patient resolution with weak-attribution fallbacks
  - followup_name filtering (bare name after "请问叫什么名字")
  - hydrate_session_state before write

WeChat-specific traits added:
  - Specialty score extraction (detect_score_keywords / extract_specialty_scores)
  - Emergency task creation (create_emergency_task)
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from db.crud import (
    create_patient as db_create_patient,
    find_patient_by_name,
    save_record,
)
from db.crud.pending import create_pending_record
from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.ai.intent import IntentResult
from services.domain.intent_handlers._types import HandlerResult
from services.domain.name_utils import is_valid_patient_name, patient_name_from_history
from services.domain.record_ops import assemble_record
from services.notify.tasks import create_emergency_task
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from services.patient.score_extraction import detect_score_keywords, extract_specialty_scores
from services.session import (
    hydrate_session_state,
    set_current_patient, set_pending_record_id,
    set_patient_not_found, clear_candidate_patient, clear_patient_not_found,
)
from utils.errors import InvalidMedicalRecordError
from utils.log import log
from services.domain.compound_normalizer import has_clinical_location_context
from utils.runtime_config import load_runtime_json as _load_rc


# ---------------------------------------------------------------------------
# Patient resolution
# ---------------------------------------------------------------------------

async def _persist_patient(
    db: Any, doctor_id: str, patient_name: str, intent_result: IntentResult,
) -> "tuple[Any, bool]":
    """Find or create patient for add_record. Returns (patient_id or HandlerResult, created)."""
    if not patient_name:
        return None, False
    patient = await find_patient_by_name(db, doctor_id, patient_name)
    if not patient:
        try:
            patient = await db_create_patient(
                db, doctor_id, patient_name, intent_result.gender, intent_result.age,
            )
        except InvalidMedicalRecordError as e:
            log(f"[add_record] auto-create patient validation FAILED doctor={doctor_id}: {e}")
            return HandlerResult(reply="⚠️ 患者姓名格式无效，请更正后再试。"), False
        return patient.id, True
    # Update demographics if provided and different
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
        log(f"[add_record] updated patient demographics [{patient_name}] doctor={doctor_id}")
    return patient.id, False


async def _resolve_patient_name(
    text: str, doctor_id: str, history: list, intent_result: IntentResult,
) -> Optional[HandlerResult]:
    """Resolve patient_name on intent_result in-place. Returns HandlerResult on block."""
    from services.session import get_session as _get_session

    if intent_result.patient_name and is_valid_patient_name(intent_result.patient_name):
        return None  # already resolved

    # 1) History scanning fallback
    _hist_name = patient_name_from_history(history)
    if _hist_name:
        intent_result.patient_name = _hist_name
        log(f"[add_record] resolved patient from history: {_hist_name} doctor={doctor_id}")
        return None

    # 2) Session current_patient fallback
    _sess = _get_session(doctor_id)
    _sess_name = _sess.current_patient_name
    if _sess_name and is_valid_patient_name(_sess_name):
        intent_result.patient_name = _sess_name
        log(f"[add_record] resolved patient from session: {_sess_name} doctor={doctor_id}")
        return None

    # 3) Single-patient auto-bind: if the doctor has exactly one patient, use it
    from db.crud import get_all_patients
    async with AsyncSessionLocal() as _db:
        _all_patients = await get_all_patients(_db, doctor_id)
    if len(_all_patients) == 1:
        _only = _all_patients[0]
        set_current_patient(doctor_id, _only.id, _only.name)
        intent_result.patient_name = _only.name
        log(f"[add_record] single-patient auto-bind: {_only.name} doctor={doctor_id}")
        return None

    # 4) Weak-attribution fallbacks (candidate/not-found)
    _cand_name = getattr(_sess, "candidate_patient_name", None)
    _not_found_name = getattr(_sess, "patient_not_found_name", None)
    _has_location_ctx = has_clinical_location_context(text)

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
        log(f"[add_record] resolved patient from candidate: {_cand_name} doctor={doctor_id} location_ctx={_has_location_ctx}")
        if not intent_result.chat_reply:
            intent_result.chat_reply = (
                f"⚠️ 已为候选患者【{_cand_name}】生成病历草稿，"
                "请核实患者信息后确认保存。"
            )
        return None

    if _not_found_name and is_valid_patient_name(_not_found_name) and _has_location_ctx:
        intent_result.patient_name = _not_found_name
        clear_patient_not_found(doctor_id)
        intent_result.extra_data = intent_result.extra_data or {}
        intent_result.extra_data["needs_review"] = True
        intent_result.extra_data["attribution_source"] = "not_found_with_location"
        log(f"[add_record] creating patient from not-found query: {_not_found_name} doctor={doctor_id}")
        if not intent_result.chat_reply:
            intent_result.chat_reply = (
                f"⚠️ 未找到【{_not_found_name}】，已为新患者生成病历草稿，"
                "请核实后确认保存。"
            )
        return None

    if _not_found_name and is_valid_patient_name(_not_found_name):
        clear_patient_not_found(doctor_id)
        log(f"[add_record] weak attribution blocked (no location ctx): {_not_found_name} doctor={doctor_id}")
        return HandlerResult(
            reply=f"未找到患者【{_not_found_name}】，请先创建患者或明确指定患者姓名。"
        )

    return HandlerResult(reply="请问这位患者叫什么名字？")


# ---------------------------------------------------------------------------
# Record building
# ---------------------------------------------------------------------------

async def _build_record(
    text: str, history: list, intent_result: IntentResult,
    patient_name: str, doctor_id: str, followup_name: Optional[str],
    patient_id: Optional[int] = None,
    visit_scenario: Optional[str] = None,
    note_style: Optional[str] = None,
) -> "MedicalRecord | HandlerResult":
    """Build a MedicalRecord from intent; returns HandlerResult on error."""
    # When text is a bare follow-up name, skip it to avoid feeding
    # a patient name as clinical content.
    effective_text: Optional[str] = text
    if followup_name and text.strip() == followup_name:
        effective_text = None

    # WeChat structured_fields shortcut: when pre-structured fields exist,
    # skip LLM structuring and create a minimal dictation record.
    if intent_result.structured_fields:
        fields = dict(intent_result.structured_fields)
        content_text = (fields.get("content") or text).strip() or "门诊就诊"
        return MedicalRecord(content=content_text, record_type="dictation")

    try:
        with trace_block("router", "records.chat.assemble_record", {"doctor_id": doctor_id, "patient_id": patient_id, "patient_name": patient_name}):
            return await assemble_record(
                intent_result, effective_text or "", history, doctor_id,
                patient_id=patient_id,
                visit_scenario=visit_scenario,
                note_style=note_style,
            )
    except ValueError:
        return HandlerResult(reply="没能识别病历内容，请重新描述一下。")
    except Exception as e:
        log(f"[add_record] structuring FAILED doctor={doctor_id} patient={patient_name}: {e}")
        return HandlerResult(reply="病历生成失败，请稍后重试。")


# ---------------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------------

async def _save_emergency(
    doctor_id: str, text: str, record: MedicalRecord,
    patient_id: int, patient_name: str, intent_result: IntentResult,
) -> HandlerResult:
    """Emergency record: save immediately, create emergency task, audit."""
    log(
        f"[silent-save] emergency record saved WITHOUT confirmation "
        f"doctor={doctor_id} patient={patient_name!r} patient_id={patient_id}"
    )
    async with AsyncSessionLocal() as db:
        saved = await save_record(db, doctor_id, record, patient_id)

    # Background tasks (non-blocking)
    from services.domain.intent_handlers._confirm_pending import _bg_auto_learn
    asyncio.create_task(_bg_auto_learn(doctor_id, text, record))
    asyncio.create_task(audit(
        doctor_id, "WRITE", resource_type="record",
        resource_id=str(saved.id), trace_id=get_current_trace_id(),
    ))
    asyncio.create_task(create_emergency_task(
        doctor_id, saved.id, patient_name or "未关联患者", None, patient_id
    ))

    reply = intent_result.chat_reply or f"🚨 紧急病历已为【{patient_name}】直接保存。"
    log(f"[add_record] emergency record saved patient={patient_name} doctor={doctor_id}")
    return HandlerResult(reply=reply, record=record)


async def _create_draft(
    doctor_id: str, record: MedicalRecord, patient_id: int,
    patient_name: str, intent_result: IntentResult,
) -> HandlerResult:
    """Create a pending draft and return preview result."""
    _draft_ttl = int(
        os.environ.get("PENDING_RECORD_TTL_MINUTES")
        or _load_rc().get("PENDING_RECORD_TTL_MINUTES", 30)
    )
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
    log(f"[add_record] pending draft created patient={patient_name} draft_id={draft_id} doctor={doctor_id}")
    return HandlerResult(
        reply=reply, record=record, pending_id=draft_id,
        pending_patient_name=patient_name, pending_expires_at=_expires_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def handle_add_record(
    text: str, doctor_id: str, history: list, intent_result: IntentResult,
    followup_name: Optional[str] = None,
) -> HandlerResult:
    """Unified add_record handler for both Web and WeChat channels.

    Patient resolution: intent_result.patient_name is already backfilled from
    session by _apply_session_context when the session has current_patient_id.
    History scanning is a fallback when no session context exists.
    """
    # Force-refresh session from DB on write-capable intents.
    await hydrate_session_state(doctor_id, write_intent=True)

    # Resolve patient name (may block with error HandlerResult)
    block = await _resolve_patient_name(text, doctor_id, history, intent_result)
    if block is not None:
        return block

    patient_name = intent_result.patient_name

    # Resolve patient in DB (find or create)
    with trace_block("router", "records.chat.persist_record", {"doctor_id": doctor_id, "patient_name": patient_name, "intent": "add_record"}):
        async with AsyncSessionLocal() as db:
            patient_id, patient_created = await _persist_patient(db, doctor_id, patient_name, intent_result)
            if isinstance(patient_id, HandlerResult):
                return patient_id

    if patient_created:
        asyncio.create_task(audit(
            doctor_id, "WRITE", resource_type="patient",
            resource_id=str(patient_id), trace_id=get_current_trace_id(),
        ))

    # Pin resolved patient to session
    _prev = None
    if isinstance(patient_id, int):
        _prev = set_current_patient(doctor_id, patient_id, patient_name)

    # Read doctor profile preferences from session for structuring prompt
    from services.session import get_session as _get_session
    _profile_sess = _get_session(doctor_id)
    _visit_scenario = getattr(_profile_sess, "visit_scenario", None)
    _note_style = getattr(_profile_sess, "note_style", None)

    # Build record
    record = await _build_record(
        text, history, intent_result, patient_name, doctor_id, followup_name,
        patient_id=patient_id,
        visit_scenario=_visit_scenario,
        note_style=_note_style,
    )
    if isinstance(record, HandlerResult):
        return record

    # Specialty score extraction (merged from WeChat)
    if detect_score_keywords(text):
        try:
            record.specialty_scores = await extract_specialty_scores(record.content or text)
            if record.specialty_scores:
                log(f"[add_record] extracted {len(record.specialty_scores)} specialty score(s)")
        except Exception as exc:
            log(f"[add_record] score extraction failed (non-fatal): {exc}")

    # Save
    if getattr(intent_result, "is_emergency", False):
        result = await _save_emergency(doctor_id, text, record, patient_id, patient_name, intent_result)
    else:
        result = await _create_draft(doctor_id, record, patient_id, patient_name, intent_result)

    # Patient switch notification
    if _prev:
        result.switch_notification = f"🔄 已从【{_prev}】切换到【{patient_name}】"

    return result
