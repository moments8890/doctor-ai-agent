from __future__ import annotations
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from db.models import (
    SystemPrompt,
    DoctorContext,
    DoctorKnowledgeItem,
    DoctorSessionState,
    DoctorNotifyPreference,
    SchedulerLease,
    RuntimeCursor,
    RuntimeToken,
    RuntimeConfig,
    DoctorConversationTurn,
    Doctor,
    Patient,
    MedicalRecordDB,
    NeuroCaseDB,
    DoctorTask,
    PatientLabel,
)
from db.repositories import PatientRepository, RecordRepository
from models.medical_record import MedicalRecord
from services.patient_categorization import recompute_patient_category
from services.patient_risk import recompute_patient_risk
from services.observability import trace_block
from services.errors import InvalidMedicalRecordError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_WECHAT_ID_RE = re.compile(r"^(?:wm|wx|ww|wo)[A-Za-z0-9_-]{6,}$")


def _is_wechat_identifier(raw: str) -> bool:
    value = (raw or "").strip()
    return bool(_WECHAT_ID_RE.match(value))


def _infer_channel(doctor_id: str) -> str:
    return "wechat" if _is_wechat_identifier(doctor_id) else "app"


async def _resolve_doctor_id(session: AsyncSession, doctor_id: str, name: Optional[str] = None) -> str:
    """Resolve incoming identifier to canonical doctor_id and keep doctors registry fresh."""
    incoming = (doctor_id or "").strip()
    if not incoming:
        return doctor_id

    now = _utcnow()
    channel = _infer_channel(incoming)
    wechat_user_id = incoming if channel == "wechat" else None

    existing_by_id = (
        await session.execute(select(Doctor).where(Doctor.doctor_id == incoming).limit(1))
    ).scalar_one_or_none()
    if existing_by_id is not None:
        existing_by_id.updated_at = now
        if name and not existing_by_id.name:
            existing_by_id.name = name
        if existing_by_id.channel != channel and existing_by_id.channel == "app":
            existing_by_id.channel = channel
        if wechat_user_id and not existing_by_id.wechat_user_id:
            existing_by_id.wechat_user_id = wechat_user_id
        return existing_by_id.doctor_id

    if wechat_user_id:
        existing_by_wechat = (
            await session.execute(
                select(Doctor)
                .where(Doctor.channel == "wechat", Doctor.wechat_user_id == wechat_user_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing_by_wechat is not None:
            existing_by_wechat.updated_at = now
            if name and not existing_by_wechat.name:
                existing_by_wechat.name = name
            return existing_by_wechat.doctor_id

    session.add(
        Doctor(
            doctor_id=incoming,
            name=name,
            channel=channel,
            wechat_user_id=wechat_user_id,
            created_at=now,
            updated_at=now,
        )
    )
    try:
        await session.flush()
        return incoming
    except IntegrityError:
        await session.rollback()
        if wechat_user_id:
            row = (
                await session.execute(
                    select(Doctor)
                    .where(Doctor.channel == "wechat", Doctor.wechat_user_id == wechat_user_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is not None:
                return row.doctor_id
        raise


async def _ensure_doctor_exists(session: AsyncSession, doctor_id: str, name: Optional[str] = None) -> str:
    return await _resolve_doctor_id(session, doctor_id, name=name)


async def get_doctor_by_id(session: AsyncSession, doctor_id: str) -> Optional[Doctor]:
    result = await session.execute(
        select(Doctor).where(Doctor.doctor_id == doctor_id).limit(1)
    )
    return result.scalar_one_or_none()


async def get_doctor_wechat_user_id(session: AsyncSession, doctor_id: str) -> Optional[str]:
    row = await get_doctor_by_id(session, doctor_id)
    if row is None or not row.wechat_user_id:
        return None
    return str(row.wechat_user_id).strip() or None


async def get_system_prompt(session: AsyncSession, key: str) -> SystemPrompt | None:
    result = await session.execute(
        select(SystemPrompt).where(SystemPrompt.key == key)
    )
    return result.scalar_one_or_none()


async def upsert_system_prompt(session: AsyncSession, key: str, content: str) -> None:
    row = await get_system_prompt(session, key)
    if row:
        row.content = content
        row.updated_at = _utcnow()
    else:
        session.add(SystemPrompt(key=key, content=content))
    await session.commit()


async def get_doctor_context(session: AsyncSession, doctor_id: str) -> DoctorContext | None:
    result = await session.execute(
        select(DoctorContext).where(DoctorContext.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def upsert_doctor_context(session: AsyncSession, doctor_id: str, summary: str) -> None:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    ctx = await get_doctor_context(session, doctor_id)
    if ctx:
        ctx.summary = summary
        ctx.updated_at = _utcnow()
    else:
        session.add(DoctorContext(doctor_id=doctor_id, summary=summary))
    await session.commit()


async def add_doctor_knowledge_item(session: AsyncSession, doctor_id: str, content: str) -> DoctorKnowledgeItem:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    now = _utcnow()
    row = DoctorKnowledgeItem(
        doctor_id=doctor_id,
        content=content.strip(),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_doctor_knowledge_items(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 30,
) -> List[DoctorKnowledgeItem]:
    stmt = (
        select(DoctorKnowledgeItem)
        .where(DoctorKnowledgeItem.doctor_id == doctor_id)
        .order_by(DoctorKnowledgeItem.updated_at.desc(), DoctorKnowledgeItem.id.desc())
        .limit(max(1, int(limit)))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def get_doctor_session_state(session: AsyncSession, doctor_id: str) -> Optional[DoctorSessionState]:
    result = await session.execute(
        select(DoctorSessionState).where(DoctorSessionState.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def get_doctor_notify_preference(
    session: AsyncSession, doctor_id: str
) -> Optional[DoctorNotifyPreference]:
    result = await session.execute(
        select(DoctorNotifyPreference).where(DoctorNotifyPreference.doctor_id == doctor_id)
    )
    return result.scalar_one_or_none()


async def try_acquire_scheduler_lease(
    session: AsyncSession,
    lease_key: str,
    owner_id: str,
    now: datetime,
    lease_ttl_seconds: int,
) -> bool:
    """Attempt to acquire distributed lease for scheduler execution."""
    ttl_seconds = max(1, int(lease_ttl_seconds))
    lease_until = now + timedelta(seconds=ttl_seconds)

    existing = await session.execute(
        select(SchedulerLease).where(SchedulerLease.lease_key == lease_key).limit(1)
    )
    row = existing.scalar_one_or_none()
    if row is None:
        session.add(
            SchedulerLease(
                lease_key=lease_key,
                owner_id=owner_id,
                lease_until=lease_until,
                updated_at=now,
            )
        )
        await session.commit()
        return True

    can_take = (
        row.owner_id == owner_id
        or row.lease_until is None
        or row.lease_until <= now
    )
    if not can_take:
        return False

    row.owner_id = owner_id
    row.lease_until = lease_until
    row.updated_at = now
    await session.commit()
    return True


async def release_scheduler_lease(
    session: AsyncSession,
    lease_key: str,
    owner_id: str,
    now: datetime,
) -> None:
    row = (
        await session.execute(
            select(SchedulerLease).where(SchedulerLease.lease_key == lease_key).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return
    if row.owner_id != owner_id:
        return
    row.lease_until = now
    row.updated_at = now
    await session.commit()


async def upsert_doctor_notify_preference(
    session: AsyncSession,
    doctor_id: str,
    *,
    notify_mode: Optional[str] = None,
    schedule_type: Optional[str] = None,
    interval_minutes: Optional[int] = None,
    cron_expr: Optional[str] = None,
    last_auto_run_at: Optional[datetime] = None,
) -> DoctorNotifyPreference:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    row = await get_doctor_notify_preference(session, doctor_id)
    if row is None:
        row = DoctorNotifyPreference(doctor_id=doctor_id)
        session.add(row)

    if notify_mode is not None:
        row.notify_mode = notify_mode
    if schedule_type is not None:
        row.schedule_type = schedule_type
    if interval_minutes is not None:
        row.interval_minutes = interval_minutes
    if cron_expr is not None or schedule_type == "cron":
        row.cron_expr = cron_expr
    if last_auto_run_at is not None:
        row.last_auto_run_at = last_auto_run_at
    row.updated_at = _utcnow()

    await session.commit()
    await session.refresh(row)
    return row


async def get_runtime_cursor(
    session: AsyncSession,
    cursor_key: str,
) -> Optional[str]:
    result = await session.execute(
        select(RuntimeCursor).where(RuntimeCursor.cursor_key == cursor_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return row.cursor_value


async def upsert_runtime_cursor(
    session: AsyncSession,
    cursor_key: str,
    cursor_value: Optional[str],
) -> None:
    result = await session.execute(
        select(RuntimeCursor).where(RuntimeCursor.cursor_key == cursor_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = RuntimeCursor(cursor_key=cursor_key)
        session.add(row)
    row.cursor_value = cursor_value
    row.updated_at = _utcnow()
    await session.commit()


async def get_runtime_token(
    session: AsyncSession,
    token_key: str,
) -> Optional[RuntimeToken]:
    result = await session.execute(
        select(RuntimeToken).where(RuntimeToken.token_key == token_key).limit(1)
    )
    return result.scalar_one_or_none()


async def get_runtime_config(
    session: AsyncSession,
    config_key: str,
) -> Optional[RuntimeConfig]:
    result = await session.execute(
        select(RuntimeConfig).where(RuntimeConfig.config_key == config_key).limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_runtime_config(
    session: AsyncSession,
    config_key: str,
    content_json: str,
) -> RuntimeConfig:
    result = await session.execute(
        select(RuntimeConfig).where(RuntimeConfig.config_key == config_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = RuntimeConfig(config_key=config_key, content_json=content_json)
        session.add(row)
    else:
        row.content_json = content_json
        row.updated_at = _utcnow()
    await session.commit()
    await session.refresh(row)
    return row


async def upsert_runtime_token(
    session: AsyncSession,
    token_key: str,
    token_value: Optional[str],
    expires_at: Optional[datetime],
) -> None:
    result = await session.execute(
        select(RuntimeToken).where(RuntimeToken.token_key == token_key).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = RuntimeToken(token_key=token_key)
        session.add(row)
    row.token_value = token_value
    row.expires_at = expires_at
    row.updated_at = _utcnow()
    await session.commit()


async def get_recent_conversation_turns(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 20,
) -> List[DoctorConversationTurn]:
    safe_limit = max(1, int(limit))
    result = await session.execute(
        select(DoctorConversationTurn)
        .where(DoctorConversationTurn.doctor_id == doctor_id)
        .order_by(DoctorConversationTurn.created_at.desc(), DoctorConversationTurn.id.desc())
        .limit(safe_limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def append_conversation_turns(
    session: AsyncSession,
    doctor_id: str,
    turns: List[dict],
    max_turns: int = 10,
) -> None:
    if not turns:
        return

    safe_max_messages = max(2, int(max_turns) * 2)
    for turn in turns:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if role not in {"user", "assistant", "system"}:
            continue
        if not content:
            continue
        session.add(
            DoctorConversationTurn(
                doctor_id=doctor_id,
                role=role,
                content=content,
                created_at=_utcnow(),
            )
        )
    await session.flush()

    keep_result = await session.execute(
        select(DoctorConversationTurn.id)
        .where(DoctorConversationTurn.doctor_id == doctor_id)
        .order_by(DoctorConversationTurn.created_at.desc(), DoctorConversationTurn.id.desc())
        .limit(safe_max_messages)
    )
    keep_ids = list(keep_result.scalars().all())
    if keep_ids:
        await session.execute(
            delete(DoctorConversationTurn).where(
                DoctorConversationTurn.doctor_id == doctor_id,
                DoctorConversationTurn.id.notin_(keep_ids),
            )
        )
    await session.commit()


async def clear_conversation_turns(
    session: AsyncSession,
    doctor_id: str,
) -> None:
    await session.execute(
        delete(DoctorConversationTurn).where(DoctorConversationTurn.doctor_id == doctor_id)
    )
    await session.commit()


async def purge_conversation_turns_before(
    session: AsyncSession,
    older_than: datetime,
) -> int:
    result = await session.execute(
        delete(DoctorConversationTurn).where(DoctorConversationTurn.created_at < older_than)
    )
    await session.commit()
    return int(result.rowcount or 0)


async def upsert_doctor_session_state(
    session: AsyncSession,
    doctor_id: str,
    current_patient_id: Optional[int],
    pending_create_name: Optional[str],
) -> None:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    row = await get_doctor_session_state(session, doctor_id)
    if row:
        row.current_patient_id = current_patient_id
        row.pending_create_name = pending_create_name
        row.updated_at = _utcnow()
    else:
        session.add(
            DoctorSessionState(
                doctor_id=doctor_id,
                current_patient_id=current_patient_id,
                pending_create_name=pending_create_name,
                updated_at=_utcnow(),
            )
        )
    await session.commit()


async def get_patient_for_doctor(session: AsyncSession, doctor_id: str, patient_id: int) -> Optional[Patient]:
    repo = PatientRepository(session)
    return await repo.get_for_doctor(doctor_id, patient_id)


async def create_patient(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    gender: Optional[str],
    age: Optional[int],
) -> Patient:
    with trace_block("db", "crud.create_patient", {"doctor_id": doctor_id}):
        cleaned_name = (name or "").strip()
        if not cleaned_name or len(cleaned_name) > 128:
            raise InvalidMedicalRecordError("Invalid patient name", context={"doctor_id": doctor_id})
        doctor_id = await _ensure_doctor_exists(session, doctor_id)
        repo = PatientRepository(session)
        return await repo.create(
            doctor_id=doctor_id,
            name=cleaned_name,
            gender=gender,
            age=age,
        )


async def find_patient_by_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> Patient | None:
    with trace_block("db", "crud.find_patient_by_name", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.find_by_name(doctor_id, name)


async def find_patients_by_exact_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> list[Patient]:
    with trace_block("db", "crud.find_patients_by_exact_name", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.find_by_exact_name(doctor_id, name)


async def delete_patient_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
) -> Optional[Patient]:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
        .limit(1)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        return None

    patient.labels.clear()
    await session.flush()

    await session.execute(
        delete(MedicalRecordDB).where(
            MedicalRecordDB.doctor_id == doctor_id,
            MedicalRecordDB.patient_id == patient_id,
        )
    )
    await session.execute(
        delete(DoctorTask).where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.patient_id == patient_id,
        )
    )
    await session.execute(
        delete(NeuroCaseDB).where(
            NeuroCaseDB.doctor_id == doctor_id,
            NeuroCaseDB.patient_id == patient_id,
        )
    )
    await session.execute(
        update(DoctorSessionState)
        .where(
            DoctorSessionState.doctor_id == doctor_id,
            DoctorSessionState.current_patient_id == patient_id,
        )
        .values(current_patient_id=None, updated_at=_utcnow())
    )
    await session.delete(patient)
    await session.commit()
    return patient


async def save_record(
    session: AsyncSession,
    doctor_id: str,
    record: MedicalRecord,
    patient_id: int | None,
) -> MedicalRecordDB:
    with trace_block("db", "crud.save_record", {"doctor_id": doctor_id, "patient_id": patient_id}):
        doctor_id = await _ensure_doctor_exists(session, doctor_id)
        repo = RecordRepository(session)
        db_record = await repo.create(
            doctor_id=doctor_id,
            record=record,
            patient_id=patient_id,
        )
        if patient_id is not None:
            await recompute_patient_category(patient_id, session)
            risk = await recompute_patient_risk(patient_id, session)
            if _env_flag_true("AUTO_FOLLOWUP_TASKS_ENABLED") and record.follow_up_plan:
                await _ensure_auto_follow_up_task(
                    session=session,
                    doctor_id=doctor_id,
                    patient_id=patient_id,
                    record_id=db_record.id,
                    patient_name=await _patient_name(session, patient_id),
                    follow_up_plan=record.follow_up_plan,
                    risk_level=risk.primary_risk_level if risk else None,
                )
        return db_record


def _env_flag_true(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


_CN_DIGITS = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_cn_or_int(raw: str) -> Optional[int]:
    n = _CN_DIGITS.get(raw)
    if n is not None:
        return n
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _extract_follow_up_days(follow_up_plan: str) -> int:
    if not follow_up_plan:
        return 7

    if "明天" in follow_up_plan:
        return 1
    if "下周" in follow_up_plan or "下星期" in follow_up_plan:
        return 7

    m = re.search(r'([一两二三四五六七八九十\d]+)周', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n * 7

    m = re.search(r'([一两二三四五六七八九十\d]+)个月', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n * 30

    m = re.search(r'([一两二三四五六七八九十\d]+)天', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n

    return 7


async def _patient_name(session: AsyncSession, patient_id: int) -> str:
    result = await session.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    return patient.name if patient is not None else "患者"


async def _ensure_auto_follow_up_task(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    record_id: int,
    patient_name: str,
    follow_up_plan: str,
    risk_level: Optional[str] = None,
) -> None:
    existing = await session.execute(
        select(DoctorTask).where(
            DoctorTask.doctor_id == doctor_id,
            DoctorTask.record_id == record_id,
            DoctorTask.task_type == "follow_up",
            DoctorTask.trigger_source == "risk_engine",
            DoctorTask.status == "pending",
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    days = _extract_follow_up_days(follow_up_plan)
    due_at = _utcnow().replace(microsecond=0) + timedelta(days=days)

    reason = "auto follow-up from record follow_up_plan"
    if risk_level:
        reason = f"{reason}; risk_level={risk_level}"

    session.add(
        DoctorTask(
            doctor_id=doctor_id,
            patient_id=patient_id,
            record_id=record_id,
            task_type="follow_up",
            title=f"随访提醒：{patient_name}",
            content=follow_up_plan,
            status="pending",
            due_at=due_at,
            trigger_source="risk_engine",
            trigger_reason=reason,
        )
    )
    await session.commit()


async def get_records_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    limit: int = 5,
) -> list[MedicalRecordDB]:
    with trace_block("db", "crud.get_records_for_patient", {"doctor_id": doctor_id, "patient_id": patient_id}):
        repo = RecordRepository(session)
        return await repo.list_for_patient(
            doctor_id=doctor_id,
            patient_id=patient_id,
            limit=limit,
        )


async def get_all_patients(
    session: AsyncSession,
    doctor_id: str,
) -> list[Patient]:
    with trace_block("db", "crud.get_all_patients", {"doctor_id": doctor_id}):
        repo = PatientRepository(session)
        return await repo.list_for_doctor(doctor_id)


async def get_all_records_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 10,
) -> list[MedicalRecordDB]:
    with trace_block("db", "crud.get_all_records_for_doctor", {"doctor_id": doctor_id}):
        repo = RecordRepository(session)
        return await repo.list_for_doctor(
            doctor_id=doctor_id,
            limit=limit,
        )


async def save_neuro_case(
    session: AsyncSession,
    doctor_id: str,
    case: "NeuroCase",  # type: ignore[name-defined]
    log: "ExtractionLog",  # type: ignore[name-defined]
    patient_id: Optional[int] = None,
) -> NeuroCaseDB:
    """Promote key scalar fields, serialise both objects, persist row."""
    pp = case.patient_profile if isinstance(case.patient_profile, dict) else {}
    ne = case.neuro_exam if isinstance(case.neuro_exam, dict) else {}
    cc = case.chief_complaint if isinstance(case.chief_complaint, dict) else {}
    dx = case.diagnosis if isinstance(case.diagnosis, dict) else {}
    enc = case.encounter if isinstance(case.encounter, dict) else {}

    nihss_raw = ne.get("nihss_total")
    nihss: Optional[int] = None
    if nihss_raw is not None:
        try:
            nihss = int(nihss_raw)
        except (TypeError, ValueError):
            nihss = None

    age_raw = pp.get("age")
    age: Optional[int] = None
    if age_raw is not None:
        try:
            age = int(age_raw)
        except (TypeError, ValueError):
            age = None

    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    row = NeuroCaseDB(
        doctor_id=doctor_id,
        patient_id=patient_id,
        patient_name=pp.get("name"),
        gender=pp.get("gender"),
        age=age,
        encounter_type=enc.get("type"),
        chief_complaint=cc.get("text"),
        primary_diagnosis=dx.get("primary"),
        nihss=nihss,
        raw_json=json.dumps(case.model_dump(), ensure_ascii=False),
        extraction_log_json=json.dumps(log.model_dump(), ensure_ascii=False),
    )
    session.add(row)
    await session.commit()
    return row


async def get_neuro_cases_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 20,
) -> List[NeuroCaseDB]:
    """Return most-recent neuro cases for a doctor."""
    result = await session.execute(
        select(NeuroCaseDB)
        .where(NeuroCaseDB.doctor_id == doctor_id)
        .order_by(NeuroCaseDB.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# DoctorTask CRUD
# ---------------------------------------------------------------------------


async def create_task(
    session: AsyncSession,
    doctor_id: str,
    task_type: str,
    title: str,
    content: Optional[str] = None,
    patient_id: Optional[int] = None,
    record_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
) -> DoctorTask:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    task = DoctorTask(
        doctor_id=doctor_id,
        task_type=task_type,
        title=title,
        content=content,
        patient_id=patient_id,
        record_id=record_id,
        due_at=due_at,
        status="pending",
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def list_tasks(
    session: AsyncSession,
    doctor_id: str,
    status: Optional[str] = None,
) -> List[DoctorTask]:
    q = select(DoctorTask).where(DoctorTask.doctor_id == doctor_id)
    if status is not None:
        q = q.where(DoctorTask.status == status)
    q = q.order_by(DoctorTask.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_task_status(
    session: AsyncSession,
    task_id: int,
    doctor_id: str,
    status: str,
) -> Optional[DoctorTask]:
    result = await session.execute(
        select(DoctorTask).where(DoctorTask.id == task_id, DoctorTask.doctor_id == doctor_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        return None
    task.status = status
    await session.commit()
    await session.refresh(task)
    return task


async def get_due_tasks(
    session: AsyncSession,
    now: datetime,
) -> List[DoctorTask]:
    result = await session.execute(
        select(DoctorTask).where(
            DoctorTask.status == "pending",
            DoctorTask.due_at <= now,
            DoctorTask.notified_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def mark_task_notified(
    session: AsyncSession,
    task_id: int,
) -> None:
    result = await session.execute(
        select(DoctorTask).where(DoctorTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if task:
        task.notified_at = _utcnow()
        await session.commit()


# ── Label management ──────────────────────────────────────────────────────────

async def create_label(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    color: Optional[str] = None,
) -> PatientLabel:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    label = PatientLabel(doctor_id=doctor_id, name=name, color=color)
    session.add(label)
    await session.commit()
    return label


async def get_labels_for_doctor(
    session: AsyncSession,
    doctor_id: str,
) -> List[PatientLabel]:
    result = await session.execute(
        select(PatientLabel)
        .where(PatientLabel.doctor_id == doctor_id)
        .order_by(PatientLabel.created_at)
    )
    return list(result.scalars().all())


async def update_label(
    session: AsyncSession,
    label_id: int,
    doctor_id: str,
    *,
    name: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[PatientLabel]:
    result = await session.execute(
        select(PatientLabel).where(
            PatientLabel.id == label_id,
            PatientLabel.doctor_id == doctor_id,
        )
    )
    label = result.scalar_one_or_none()
    if label is None:
        return None
    if name is not None:
        label.name = name
    if color is not None:
        label.color = color
    await session.commit()
    return label


async def delete_label(
    session: AsyncSession,
    label_id: int,
    doctor_id: str,
) -> bool:
    result = await session.execute(
        select(PatientLabel)
        .options(selectinload(PatientLabel.patients))
        .where(
            PatientLabel.id == label_id,
            PatientLabel.doctor_id == doctor_id,
        )
    )
    label = result.scalar_one_or_none()
    if label is None:
        return False
    # Clear via ORM — updates in-memory Patient.labels back-populates and
    # removes patient_label_assignments rows without needing raw SQL.
    label.patients.clear()
    await session.flush()
    await session.delete(label)
    await session.commit()
    return True


# ── Patient-label assignment ──────────────────────────────────────────────────

async def assign_label(
    session: AsyncSession,
    patient_id: int,
    label_id: int,
    doctor_id: str,
) -> None:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found for doctor {doctor_id}")

    label_result = await session.execute(
        select(PatientLabel).where(
            PatientLabel.id == label_id,
            PatientLabel.doctor_id == doctor_id,
        )
    )
    label = label_result.scalar_one_or_none()
    if label is None:
        raise ValueError(f"Label {label_id} not found for doctor {doctor_id}")

    if label not in patient.labels:
        patient.labels.append(label)
        await session.commit()


async def remove_label(
    session: AsyncSession,
    patient_id: int,
    label_id: int,
    doctor_id: str,
) -> None:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        raise ValueError(f"Patient {patient_id} not found for doctor {doctor_id}")
    patient.labels = [lbl for lbl in patient.labels if lbl.id != label_id]
    await session.commit()


async def get_patient_labels(
    session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> List[PatientLabel]:
    patient_result = await session.execute(
        select(Patient)
        .options(selectinload(Patient.labels))
        .where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        return []
    return list(patient.labels)
