"""
Preseed demo data service — creates/resets/deletes demo data for onboarding.

All operations run in a single transaction. No intermediate commits.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ai_suggestion import AISuggestion, SuggestionSection
from db.models.doctor import DoctorKnowledgeItem
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.records import MedicalRecordDB, RecordStatus
from db.models.tasks import DoctorTask

from .preseed_schema import SeedSpec

_SEED_SOURCE = "onboarding_preseed"
_DEMO_SOURCE = "onboarding_demo"
_DATA_FILE = Path(__file__).parent / "preseed_data.json"
_DEMO_FILE = Path(__file__).parent / "preseed_demo.json"
_spec_cache: Optional[SeedSpec] = None
_demo_cache: Optional[SeedSpec] = None


def _load_spec() -> SeedSpec:
    global _spec_cache
    if _spec_cache is None:
        with open(_DATA_FILE, encoding="utf-8") as f:
            _spec_cache = SeedSpec(**json.load(f))
    return _spec_cache


def _load_demo_spec() -> SeedSpec:
    global _demo_cache
    if _demo_cache is None:
        with open(_DEMO_FILE, encoding="utf-8") as f:
            _demo_cache = SeedSpec(**json.load(f))
    return _demo_cache


def _ts(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _resolve_kb_refs(text: str, kb_map: dict[str, int]) -> str:
    for placeholder, real_id in kb_map.items():
        text = text.replace(placeholder, f"[KB-{real_id}]")
    return text


class SeedPatientResult(BaseModel):
    id: int
    name: str
    record_count: int = 0
    message_count: int = 0
    task_count: int = 0


class SeedResult(BaseModel):
    status: str = "ok"
    already_seeded: bool = False
    knowledge_items: list[dict] = []
    patients: list[SeedPatientResult] = []


async def is_seeded(db: AsyncSession, doctor_id: str) -> bool:
    """Check if the thin preseed has been applied to this doctor."""
    row = (await db.execute(
        select(Patient.id).where(
            Patient.doctor_id == doctor_id,
            Patient.seed_source == _SEED_SOURCE,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def is_demo_seeded(db: AsyncSession, doctor_id: str) -> bool:
    """Check if rich demo data has been applied to this doctor."""
    row = (await db.execute(
        select(Patient.id).where(
            Patient.doctor_id == doctor_id,
            Patient.seed_source == _DEMO_SOURCE,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def cleanup_seed_data(db: AsyncSession, doctor_id: str) -> None:
    """Delete all preseed data + onboarding sim patients for a doctor.

    Onboarding sim patients come from two generations of the wizard and are
    never tagged with seed_source:
      - 体验患者*  (older wizard output)
      - 模拟患者 / *_模拟 / *模拟* (current wizard output)

    Order below respects FK relationships (suggestions → records → patient).
    """
    # 0. Find onboarding sim patients (not tagged with seed_source)
    from sqlalchemy import or_
    onboarding_patients = (await db.execute(
        select(Patient).where(
            Patient.doctor_id == doctor_id,
            or_(
                Patient.name.like("体验患者%"),
                Patient.name.like("%模拟%"),
            ),
        )
    )).scalars().all()
    for p in onboarding_patients:
        pid = p.id
        await db.execute(delete(AISuggestion).where(AISuggestion.record_id.in_(
            select(MedicalRecordDB.id).where(MedicalRecordDB.patient_id == pid)
        )))
        await db.execute(delete(MessageDraft).where(MessageDraft.source_message_id.in_(
            select(PatientMessage.id).where(PatientMessage.patient_id == pid)
        )))
        await db.execute(delete(DoctorTask).where(DoctorTask.patient_id == pid))
        await db.execute(delete(PatientMessage).where(PatientMessage.patient_id == pid))
        await db.execute(delete(MedicalRecordDB).where(MedicalRecordDB.patient_id == pid))
        await db.delete(p)
    # 1. AI suggestions (FK → records)
    await db.execute(delete(AISuggestion).where(
        AISuggestion.doctor_id == doctor_id,
        AISuggestion.seed_source.in_([_SEED_SOURCE, _DEMO_SOURCE]),
    ))
    # 2. Message drafts (FK → messages)
    await db.execute(delete(MessageDraft).where(
        MessageDraft.doctor_id == doctor_id,
        MessageDraft.seed_source.in_([_SEED_SOURCE, _DEMO_SOURCE]),
    ))
    # 3. Tasks (FK → patients/records)
    await db.execute(delete(DoctorTask).where(
        DoctorTask.doctor_id == doctor_id,
        DoctorTask.seed_source.in_([_SEED_SOURCE, _DEMO_SOURCE]),
    ))
    # 4. Messages (FK → patients)
    await db.execute(delete(PatientMessage).where(
        PatientMessage.doctor_id == doctor_id,
        PatientMessage.seed_source.in_([_SEED_SOURCE, _DEMO_SOURCE]),
    ))
    # 5. Records (FK → patients)
    await db.execute(delete(MedicalRecordDB).where(
        MedicalRecordDB.doctor_id == doctor_id,
        MedicalRecordDB.seed_source.in_([_SEED_SOURCE, _DEMO_SOURCE]),
    ))
    # 6. Knowledge items
    await db.execute(delete(DoctorKnowledgeItem).where(
        DoctorKnowledgeItem.doctor_id == doctor_id,
        DoctorKnowledgeItem.seed_source.in_([_SEED_SOURCE, _DEMO_SOURCE]),
    ))
    # 7. Patients (last — others reference patient_id)
    await db.execute(delete(Patient).where(
        Patient.doctor_id == doctor_id,
        Patient.seed_source.in_([_SEED_SOURCE, _DEMO_SOURCE]),
    ))
    await db.flush()


async def seed_demo_data(db: AsyncSession, doctor_id: str) -> SeedResult:
    """Apply the original (thin) preseed — fired on new-doctor registration."""
    if await is_seeded(db, doctor_id):
        return await _build_existing_result(db, doctor_id)
    return await _apply_spec(db, doctor_id, _load_spec(), _SEED_SOURCE)


async def seed_demo_data_rich(db: AsyncSession, doctor_id: str) -> SeedResult:
    """Apply the rich demo spec (6 patients, 8 KBs, varied urgency, diverse
    citations). Idempotent — tagged with _DEMO_SOURCE so it coexists with the
    thin preseed and can be cleaned independently via cleanup_seed_data().
    Caller must db.commit() after this returns.
    """
    if await is_demo_seeded(db, doctor_id):
        return await _build_existing_result(db, doctor_id, source=_DEMO_SOURCE)
    return await _apply_spec(db, doctor_id, _load_demo_spec(), _DEMO_SOURCE)


async def _apply_spec(
    db: AsyncSession, doctor_id: str, spec: SeedSpec, source: str
) -> SeedResult:
    """Shared mutation path — creates knowledge items, patients, records,
    suggestions, messages, drafts, and tasks from a spec, tagged with `source`.
    """
    now = datetime.now(timezone.utc)

    # Phase 1: Knowledge items
    kb_map: dict[str, int] = {}  # "[KB-1]" → real_id
    kb_results = []
    for i, kb_spec in enumerate(spec.knowledge_items, start=1):
        item = DoctorKnowledgeItem(
            doctor_id=doctor_id,
            title=kb_spec.title,
            content=json.dumps({"text": kb_spec.content}, ensure_ascii=False),
            category="custom",
            seed_source=source,
            created_at=now - timedelta(hours=1),
        )
        db.add(item)
        await db.flush()
        kb_map[f"[KB-{kb_spec.key}]"] = item.id
        kb_map[f"[KB-{i}]"] = item.id  # also support numeric refs
        kb_results.append({"id": item.id, "title": kb_spec.title})

    # Phase 2: Patients + records + suggestions + messages + drafts + tasks
    patient_results = []
    for p_spec in spec.patients:
        # Create or reuse patient (name uniqueness constraint per doctor)
        year_of_birth = now.year - p_spec.age
        existing_patient = (await db.execute(
            select(Patient).where(
                Patient.doctor_id == doctor_id,
                Patient.name == p_spec.name,
            ).limit(1)
        )).scalar_one_or_none()

        if existing_patient:
            patient = existing_patient
            patient.seed_source = source
        else:
            patient = Patient(
                doctor_id=doctor_id,
                name=p_spec.name,
                gender=p_spec.gender,
                year_of_birth=year_of_birth,
                phone=p_spec.phone,
                seed_source=source,
                created_at=_ts(max((r.days_ago for r in p_spec.records), default=0)),
            )
            db.add(patient)
        await db.flush()

        p_result = SeedPatientResult(id=patient.id, name=patient.name)

        # Records + suggestions
        for r_spec in p_spec.records:
            record = MedicalRecordDB(
                patient_id=patient.id,
                doctor_id=doctor_id,
                record_type=r_spec.record_type,
                status=r_spec.status,
                department=r_spec.department,
                chief_complaint=r_spec.chief_complaint,
                present_illness=_resolve_kb_refs(r_spec.present_illness or "", kb_map) or None,
                past_history=r_spec.past_history,
                allergy_history=r_spec.allergy_history,
                personal_history=r_spec.personal_history,
                marital_reproductive=r_spec.marital_reproductive,
                family_history=r_spec.family_history,
                physical_exam=r_spec.physical_exam,
                specialist_exam=r_spec.specialist_exam,
                auxiliary_exam=r_spec.auxiliary_exam,
                diagnosis=r_spec.diagnosis,
                treatment_plan=r_spec.treatment_plan,
                orders_followup=r_spec.orders_followup,
                content=r_spec.content,
                seed_source=source,
                created_at=_ts(r_spec.days_ago),
                updated_at=_ts(r_spec.days_ago),
            )
            db.add(record)
            await db.flush()
            p_result.record_count += 1

            is_completed = r_spec.status == "completed"
            for s_spec in r_spec.suggestions:
                suggestion = AISuggestion(
                    record_id=record.id,
                    doctor_id=doctor_id,
                    section=s_spec.section,
                    content=s_spec.content,
                    detail=_resolve_kb_refs(s_spec.detail, kb_map),
                    confidence=s_spec.confidence,
                    urgency=s_spec.urgency,
                    intervention=s_spec.intervention,
                    seed_source=source,
                    decision="confirmed" if is_completed else None,
                    decided_at=_ts(r_spec.days_ago) if is_completed else None,
                )
                db.add(suggestion)

        # Messages + drafts
        for m_spec in p_spec.messages:
            inbound = PatientMessage(
                patient_id=patient.id,
                doctor_id=doctor_id,
                content=m_spec.content,
                direction="inbound",
                source="patient",
                triage_category=m_spec.triage,
                ai_handled=m_spec.auto_send,
                seed_source=source,
                created_at=_ts(m_spec.days_ago),
            )
            db.add(inbound)
            await db.flush()
            p_result.message_count += 1

            reply_text = _resolve_kb_refs(m_spec.ai_reply, kb_map)
            clean_reply = re.sub(r"\[KB-\d+\]", "", reply_text).strip()

            if m_spec.auto_send:
                outbound = PatientMessage(
                    patient_id=patient.id,
                    doctor_id=doctor_id,
                    content=clean_reply,
                    direction="outbound",
                    source="ai",
                    reference_id=inbound.id,
                    seed_source=source,
                    created_at=_ts(m_spec.days_ago) + timedelta(minutes=2),
                )
                db.add(outbound)
            else:
                # Only cite KB items actually referenced in the reply
                from domain.knowledge.citation_parser import extract_citations
                from domain.knowledge.usage_tracking import log_citations
                cited = extract_citations(reply_text)
                valid_cited = [kid for kid in cited.cited_ids if kid in set(kb_map.values())]
                draft = MessageDraft(
                    doctor_id=doctor_id,
                    patient_id=str(patient.id),
                    source_message_id=inbound.id,
                    draft_text=re.sub(r"\[KB-\d+\]", "", reply_text).strip(),
                    cited_knowledge_ids=json.dumps(valid_cited, ensure_ascii=False),
                    status=DraftStatus.generated.value,
                    seed_source=source,
                )
                db.add(draft)
                await db.flush()  # get draft.id before citation logging
                # Mirror live draft_reply path: also log to knowledge_usage_log
                # and bump reference_count so stats and 引用记录 stay in lockstep.
                if valid_cited:
                    await log_citations(
                        db, doctor_id, valid_cited,
                        "followup", patient_id=str(patient.id), draft_id=draft.id,
                    )

        # Tasks
        for t_spec in p_spec.tasks:
            is_done = t_spec.status == "completed"
            task = DoctorTask(
                doctor_id=doctor_id,
                patient_id=patient.id,
                task_type=t_spec.task_type,
                title=t_spec.title,
                content=t_spec.content,
                status=t_spec.status,
                due_at=now + timedelta(days=t_spec.due_days),
                completed_at=_ts(-t_spec.due_days) if is_done else None,
                source_type="manual",
                seed_source=source,
            )
            db.add(task)
            p_result.task_count += 1

        # Set last_activity_at to the most recent activity (record or message)
        recent_dates = []
        for r_spec in p_spec.records:
            recent_dates.append(_ts(r_spec.days_ago))
        for m_spec in p_spec.messages:
            recent_dates.append(_ts(m_spec.days_ago))
        patient.last_activity_at = max(recent_dates) if recent_dates else now
        patient_results.append(p_result)

    return SeedResult(
        knowledge_items=kb_results,
        patients=patient_results,
    )


async def _build_existing_result(
    db: AsyncSession, doctor_id: str, source: str = _SEED_SOURCE
) -> SeedResult:
    """Build result from existing seeded data tagged with `source`."""
    patients = (await db.execute(
        select(Patient).where(
            Patient.doctor_id == doctor_id,
            Patient.seed_source == source,
        )
    )).scalars().all()

    kb_items = (await db.execute(
        select(DoctorKnowledgeItem).where(
            DoctorKnowledgeItem.doctor_id == doctor_id,
            DoctorKnowledgeItem.seed_source == source,
        )
    )).scalars().all()

    results = []
    for p in patients:
        results.append(SeedPatientResult(id=p.id, name=p.name))

    return SeedResult(
        already_seeded=True,
        knowledge_items=[{"id": k.id, "title": k.title} for k in kb_items],
        patients=results,
    )
