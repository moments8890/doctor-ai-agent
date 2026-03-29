"""
Doctor profile routes: get and update doctor display name and specialty.
"""

from __future__ import annotations

import json
import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from db.crud.patient import create_patient, find_patient_by_name
from db.crud.records import save_record
from db.engine import AsyncSessionLocal
from db.models import Doctor
from db.models.ai_suggestion import AISuggestion, SuggestionSection
from db.models.doctor import DoctorKnowledgeItem
from db.models.medical_record import MedicalRecord
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient_message import PatientMessage
from db.models.records import MedicalRecordDB, RecordStatus
from channels.web.ui._utils import _resolve_ui_doctor_id
from infra.auth import UserRole, is_production
from infra.auth.unified import issue_token

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Models ────────────────────────────────────────────────────────────────────

class DoctorProfileUpdate(BaseModel):
    name: str
    specialty: Optional[str] = None
    clinic_name: Optional[str] = None
    bio: Optional[str] = None


class OnboardingPatientEntryRequest(BaseModel):
    doctor_id: str
    patient_name: str
    gender: Optional[str] = None
    age: Optional[int] = None


class OnboardingPatientEntryResponse(BaseModel):
    status: str
    patient_id: int
    patient_name: str
    created: bool
    portal_token: str
    portal_url: str
    expires_in_days: int


class OnboardingExamplesRequest(BaseModel):
    doctor_id: str
    knowledge_item_id: Optional[int] = None


class OnboardingExamplesResponse(BaseModel):
    status: str
    knowledge_item_id: int
    diagnosis_record_id: int
    reply_draft_id: int
    reply_message_id: int


_ONBOARDING_DIAGNOSIS_TAG = "onboarding_diagnosis_example"
_ONBOARDING_REPLY_TRIAGE = "onboarding_reply_example"
_ONBOARDING_PATIENT_NAME = "陈伟强"


def _extract_knowledge_text(item: DoctorKnowledgeItem) -> str:
    try:
        payload = json.loads(item.content or "")
        if isinstance(payload, dict):
            text = str(payload.get("text") or "").strip()
            if text:
                return text
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return (item.content or "").strip()


def _derive_rule_title(item: DoctorKnowledgeItem, text: str) -> str:
    title = (item.title or "").strip()
    if title:
        return title
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:18] or f"规则 #{item.id}"


async def _load_or_pick_knowledge_item(
    db,
    *,
    doctor_id: str,
    knowledge_item_id: Optional[int],
) -> DoctorKnowledgeItem:
    item: Optional[DoctorKnowledgeItem] = None
    if knowledge_item_id is not None:
        item = (
            await db.execute(
                select(DoctorKnowledgeItem)
                .where(
                    DoctorKnowledgeItem.id == knowledge_item_id,
                    DoctorKnowledgeItem.doctor_id == doctor_id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=404, detail="Knowledge item not found")

    if item is None:
        item = (
            await db.execute(
                select(DoctorKnowledgeItem)
                .where(DoctorKnowledgeItem.doctor_id == doctor_id)
                .order_by(DoctorKnowledgeItem.created_at.desc(), DoctorKnowledgeItem.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=422, detail="请先添加一条知识")
    return item


async def _ensure_onboarding_patient(db, *, doctor_id: str):
    patient = await find_patient_by_name(db, doctor_id, _ONBOARDING_PATIENT_NAME)
    if patient is not None:
        return patient
    patient, _plaintext_code = await create_patient(
        db,
        doctor_id,
        _ONBOARDING_PATIENT_NAME,
        "male",
        42,
    )
    return patient


async def _ensure_diagnosis_example(
    db,
    *,
    doctor_id: str,
    patient_id: int,
    knowledge_item_id: int,
) -> int:
    record = (
        await db.execute(
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.doctor_id == doctor_id,
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.tags.like(f"%{_ONBOARDING_DIAGNOSIS_TAG}%"),
            )
            .order_by(MedicalRecordDB.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if record is None:
        record = await save_record(
            db,
            doctor_id,
            MedicalRecord(
                content="主诉：术后头痛加剧伴恶心1天\n现病史：脑膜瘤术后第7天，今日晨起头痛较昨日明显加重，伴恶心，无发热。",
                record_type="interview_summary",
                tags=[_ONBOARDING_DIAGNOSIS_TAG],
                structured={
                    "department": "神经外科",
                    "chief_complaint": "术后头痛加剧伴恶心1天",
                    "present_illness": "脑膜瘤术后第7天，今日晨起头痛较昨日明显加重，伴恶心，无发热。",
                    "past_history": "右额叶脑膜瘤术后第7天。",
                    "allergy_history": "否认明确药物过敏。",
                    "family_history": "无特殊。",
                    "personal_history": "无吸烟饮酒嗜好。",
                    "marital_reproductive": "已婚。",
                },
            ),
            patient_id,
            status=RecordStatus.pending_review.value,
            commit=False,
        )
    else:
        record.status = RecordStatus.pending_review.value

    suggestions = (
        await db.execute(
            select(AISuggestion)
            .where(AISuggestion.record_id == record.id)
            .order_by(AISuggestion.id.asc())
        )
    ).scalars().all()

    diagnosis_detail = (
        "脑膜瘤术后第7天头痛加剧伴恶心，需排除迟发性硬膜外/硬膜下血肿，建议急查头颅CT平扫。 "
        f"[KB-{knowledge_item_id}]"
    )
    workup_detail = (
        "必要时结合生命体征和神经系统查体，优先排除术后再出血或脑水肿。 "
        f"[KB-{knowledge_item_id}]"
    )
    treatment_detail = (
        "若影像提示术后并发症，应尽快转入急诊或病房进一步处理。 "
        f"[KB-{knowledge_item_id}]"
    )

    if suggestions:
        for suggestion in suggestions:
            suggestion.decision = None
            suggestion.edited_text = None
            suggestion.reason = None
            suggestion.decided_at = None
            if suggestion.section == SuggestionSection.differential.value:
                suggestion.content = "术后迟发性血肿"
                suggestion.detail = diagnosis_detail
                suggestion.confidence = "高"
                suggestion.urgency = "urgent"
            elif suggestion.section == SuggestionSection.workup.value:
                suggestion.content = "尽快完成头颅CT平扫"
                suggestion.detail = workup_detail
                suggestion.confidence = "高"
                suggestion.urgency = "urgent"
            elif suggestion.section == SuggestionSection.treatment.value:
                suggestion.content = "必要时急诊评估并处理"
                suggestion.detail = treatment_detail
                suggestion.confidence = "中"
                suggestion.intervention = "urgent"
    else:
        db.add_all([
            AISuggestion(
                record_id=record.id,
                doctor_id=doctor_id,
                section=SuggestionSection.differential.value,
                content="术后迟发性血肿",
                detail=diagnosis_detail,
                confidence="高",
                urgency="urgent",
            ),
            AISuggestion(
                record_id=record.id,
                doctor_id=doctor_id,
                section=SuggestionSection.workup.value,
                content="尽快完成头颅CT平扫",
                detail=workup_detail,
                confidence="高",
                urgency="urgent",
            ),
            AISuggestion(
                record_id=record.id,
                doctor_id=doctor_id,
                section=SuggestionSection.treatment.value,
                content="必要时急诊评估并处理",
                detail=treatment_detail,
                confidence="中",
                intervention="urgent",
            ),
        ])

    await db.commit()
    return record.id


async def _ensure_reply_example(
    db,
    *,
    doctor_id: str,
    patient_id: int,
    knowledge_item_id: int,
) -> tuple[int, int]:
    message = (
        await db.execute(
            select(PatientMessage)
            .where(
                PatientMessage.doctor_id == doctor_id,
                PatientMessage.patient_id == patient_id,
                PatientMessage.direction == "inbound",
                PatientMessage.triage_category == _ONBOARDING_REPLY_TRIAGE,
            )
            .order_by(PatientMessage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if message is None:
        message = PatientMessage(
            patient_id=patient_id,
            doctor_id=doctor_id,
            content="张医生，我今天早上起来头痛比昨天厉害了，还有点恶心，需要去急诊吗？",
            direction="inbound",
            source="patient",
            triage_category=_ONBOARDING_REPLY_TRIAGE,
            ai_handled=True,
        )
        db.add(message)
        await db.flush()

    draft = (
        await db.execute(
            select(MessageDraft)
            .where(
                MessageDraft.doctor_id == doctor_id,
                MessageDraft.source_message_id == message.id,
            )
            .order_by(MessageDraft.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    draft_text = (
        "陈先生，您术后头痛加剧伴恶心需要高度重视。请您尽快到医院急诊做头颅CT检查，"
        "排除术后出血可能。如果出现剧烈头痛、频繁呕吐或意识不清，请立即拨打120。"
    )
    cited_ids = json.dumps([knowledge_item_id], ensure_ascii=False)

    if draft is None:
        draft = MessageDraft(
            doctor_id=doctor_id,
            patient_id=str(patient_id),
            source_message_id=message.id,
            draft_text=draft_text,
            cited_knowledge_ids=cited_ids,
            confidence=0.95,
            status=DraftStatus.generated.value,
        )
        db.add(draft)
        await db.flush()
    else:
        draft.draft_text = draft_text
        draft.edited_text = None
        draft.cited_knowledge_ids = cited_ids
        draft.confidence = 0.95
        draft.status = DraftStatus.generated.value

    await db.commit()
    return draft.id, message.id


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/manage/profile", include_in_schema=True)
async def get_doctor_profile(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the doctor's display name, specialty, and onboarding status."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Doctor).where(Doctor.doctor_id == resolved_id))
        doctor = result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")

    name = doctor.name or ""
    specialty = getattr(doctor, "specialty", None) or ""
    clinic_name = getattr(doctor, "clinic_name", None) or ""
    bio = getattr(doctor, "bio", None) or ""
    onboarded = bool(name and name != resolved_id)
    return {
        "doctor_id": resolved_id,
        "name": name,
        "specialty": specialty,
        "clinic_name": clinic_name,
        "bio": bio,
        "onboarded": onboarded,
    }


@router.patch("/api/manage/profile", include_in_schema=True)
async def patch_doctor_profile(
    body: DoctorProfileUpdate,
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Update the doctor's display name and specialty."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Doctor).where(Doctor.doctor_id == resolved_id))
        doctor = result.scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status_code=404, detail="Doctor not found")
        doctor.name = name
        try:
            doctor.specialty = body.specialty or None
        except Exception:
            pass  # specialty column not yet migrated — skip
        try:
            doctor.clinic_name = body.clinic_name or None
            doctor.bio = body.bio or None
        except Exception:
            pass  # columns not yet migrated — skip
        await db.commit()

    return {"ok": True, "name": name, "specialty": body.specialty or "", "clinic_name": body.clinic_name or "", "bio": body.bio or ""}


@router.post(
    "/api/manage/onboarding/patient-entry",
    response_model=OnboardingPatientEntryResponse,
    include_in_schema=True,
)
async def create_onboarding_patient_entry(
    body: OnboardingPatientEntryRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Create or reuse a patient, then return a deterministic patient-entry URL."""
    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    patient_name = (body.patient_name or "").strip()
    if not patient_name:
        raise HTTPException(status_code=422, detail="patient_name is required")
    if len(patient_name) > 128:
        raise HTTPException(status_code=422, detail="patient_name too long")

    async with AsyncSessionLocal() as db:
        patient = await find_patient_by_name(db, resolved_doctor_id, patient_name)
        created = False
        if patient is None:
            patient, _plaintext_code = await create_patient(
                db,
                resolved_doctor_id,
                patient_name,
                body.gender,
                body.age,
            )
            created = True

    ttl_days = 30
    ttl_seconds = ttl_days * 24 * 3600
    portal_token = issue_token(
        role=UserRole.patient,
        doctor_id=resolved_doctor_id,
        patient_id=patient.id,
        name=patient.name,
        ttl_seconds=ttl_seconds,
    )
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:5173")
    portal_url = f"{base_url}/patient?{urlencode({'token': portal_token})}"

    return OnboardingPatientEntryResponse(
        status="ok",
        patient_id=patient.id,
        patient_name=patient.name,
        created=created,
        portal_token=portal_token,
        portal_url=portal_url,
        expires_in_days=ttl_days,
    )


@router.post(
    "/api/manage/onboarding/examples",
    response_model=OnboardingExamplesResponse,
    include_in_schema=True,
)
async def ensure_onboarding_examples(
    body: OnboardingExamplesRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Create or reset deterministic onboarding proof data for dev/test use."""
    if is_production():
        raise HTTPException(status_code=404, detail="Not found")

    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        item = await _load_or_pick_knowledge_item(
            db,
            doctor_id=resolved_doctor_id,
            knowledge_item_id=body.knowledge_item_id,
        )
        knowledge_text = _extract_knowledge_text(item)
        item.title = _derive_rule_title(item, knowledge_text)
        patient = await _ensure_onboarding_patient(db, doctor_id=resolved_doctor_id)
        diagnosis_record_id = await _ensure_diagnosis_example(
            db,
            doctor_id=resolved_doctor_id,
            patient_id=patient.id,
            knowledge_item_id=item.id,
        )
        reply_draft_id, reply_message_id = await _ensure_reply_example(
            db,
            doctor_id=resolved_doctor_id,
            patient_id=patient.id,
            knowledge_item_id=item.id,
        )

    return OnboardingExamplesResponse(
        status="ok",
        knowledge_item_id=item.id,
        diagnosis_record_id=diagnosis_record_id,
        reply_draft_id=reply_draft_id,
        reply_message_id=reply_message_id,
    )
