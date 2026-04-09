"""
Onboarding wizard and preseed demo data routes.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.patient import create_patient, find_patient_by_name
from db.crud.records import save_record
from db.engine import get_db
from db.models import Doctor
from db.models.ai_suggestion import AISuggestion, SuggestionSection
from db.models.doctor import DoctorKnowledgeItem
from db.models.medical_record import MedicalRecord
from db.models.message_draft import DraftStatus, MessageDraft
from db.models.patient_message import PatientMessage
from db.models.records import MedicalRecordDB, RecordStatus
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from infra.auth import UserRole, is_production
from infra.auth.unified import issue_token

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Models ────────────────────────────────────────────────────────────────────

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


class AutoHandledMessageItem(BaseModel):
    id: int
    patient_name: str
    content: str
    ai_reply: str
    triage: str  # "routine" | "info" | "urgent"
    status: str  # "sent" | "pending_doctor"
    draft_id: Optional[int] = None


class OnboardingExamplesResponse(BaseModel):
    status: str
    knowledge_item_id: int
    diagnosis_record_id: int
    reply_draft_id: int
    reply_message_id: int
    auto_handled_messages: List[AutoHandledMessageItem] = []


# ── Constants & helpers ──────────────────────────────────────────────────────

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
        "男",
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

    # Reuse existing suggestions if they match the expected onboarding set
    expected_contents = {"术后迟发性血肿", "尽快完成头颅CT平扫", "必要时急诊评估并处理"}
    existing_contents = {s.content for s in suggestions}
    if suggestions and existing_contents == expected_contents:
        # Already has the right suggestions, just reset decisions for re-review
        for s in suggestions:
            s.decision = None
            s.edited_text = None
        await db.commit()
        return record.id
    # Otherwise, clean slate
    if suggestions:
        for s in suggestions:
            await db.delete(s)
        await db.flush()

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


_ONBOARDING_AUTO_TRIAGE = "onboarding_auto_handled"


async def _ensure_auto_handled_messages(
    db,
    *,
    doctor_id: str,
    patient_id: int,
    knowledge_item_id: int,
) -> List[dict]:
    existing = (
        await db.execute(
            select(PatientMessage)
            .where(
                PatientMessage.doctor_id == doctor_id,
                PatientMessage.patient_id == patient_id,
                PatientMessage.triage_category == _ONBOARDING_AUTO_TRIAGE,
            )
        )
    ).scalars().all()

    if existing:
        for msg in existing:
            await db.execute(
                delete(MessageDraft).where(MessageDraft.source_message_id == msg.id)
            )
            await db.execute(
                delete(PatientMessage).where(PatientMessage.reference_id == msg.id)
            )
            await db.delete(msg)
        await db.flush()

    messages_spec = [
        {
            "content": "药还需要继续吃吗？",
            "ai_reply": "请继续按原方案服药，下次复诊时再评估。如有不适请随时联系。",
            "triage": "routine",
            "auto_send": True,
        },
        {
            "content": "复查报告出来了，一切正常",
            "ai_reply": "好的，结果已记录。如有不适随时联系。",
            "triage": "info",
            "auto_send": True,
        },
        {
            "content": "头痛又加重了，还吐了一次",
            "ai_reply": (
                "您术后头痛加重伴呕吐需要高度重视。请您尽快到医院急诊做头颅CT检查，"
                "排除术后出血可能。如果出现剧烈头痛、频繁呕吐或意识不清，请立即拨打120。"
                f" [KB-{knowledge_item_id}]"
            ),
            "triage": "urgent",
            "auto_send": False,
        },
    ]

    result = []
    for spec in messages_spec:
        inbound = PatientMessage(
            patient_id=patient_id,
            doctor_id=doctor_id,
            content=spec["content"],
            direction="inbound",
            source="patient",
            triage_category=_ONBOARDING_AUTO_TRIAGE,
            ai_handled=spec["auto_send"],
        )
        db.add(inbound)
        await db.flush()

        item = {
            "id": inbound.id,
            "patient_name": "陈伟强",
            "content": spec["content"],
            "ai_reply": spec["ai_reply"],
            "triage": spec["triage"],
        }

        if spec["auto_send"]:
            outbound = PatientMessage(
                patient_id=patient_id,
                doctor_id=doctor_id,
                content=spec["ai_reply"],
                direction="outbound",
                source="ai",
                reference_id=inbound.id,
                triage_category=_ONBOARDING_AUTO_TRIAGE,
            )
            db.add(outbound)
            item["status"] = "sent"
        else:
            draft = MessageDraft(
                doctor_id=doctor_id,
                patient_id=str(patient_id),
                source_message_id=inbound.id,
                draft_text=spec["ai_reply"],
                cited_knowledge_ids=json.dumps([knowledge_item_id], ensure_ascii=False),
                status=DraftStatus.generated.value,
            )
            db.add(draft)
            await db.flush()
            item["status"] = "pending_doctor"
            item["draft_id"] = draft.id

        result.append(item)

    await db.commit()
    return result


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/api/manage/onboarding/patient-entry",
    response_model=OnboardingPatientEntryResponse,
    include_in_schema=True,
)
async def create_onboarding_patient_entry(
    body: OnboardingPatientEntryRequest,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Create or reuse a patient, then return a deterministic patient-entry URL."""
    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    patient_name = (body.patient_name or "").strip()
    if not patient_name:
        raise HTTPException(status_code=422, detail="patient_name is required")
    if len(patient_name) > 128:
        raise HTTPException(status_code=422, detail="patient_name too long")

    patient = await find_patient_by_name(db, resolved_doctor_id, patient_name)
    created = False
    if patient is None:
        try:
            patient, _plaintext_code = await create_patient(
                db,
                resolved_doctor_id,
                patient_name,
                body.gender or "女",
                body.age or 65,
            )
            created = True
        except IntegrityError:
            await db.rollback()
            patient = await find_patient_by_name(db, resolved_doctor_id, patient_name)
            if patient is None:
                raise HTTPException(status_code=409, detail="患者创建冲突，请重试")

    # Seed a completed prior-visit record so the interview can reference history
    if created:
        from sqlalchemy import select as sa_select

        has_record = (await db.execute(
            sa_select(MedicalRecordDB.id).where(
                MedicalRecordDB.patient_id == patient.id,
                MedicalRecordDB.doctor_id == resolved_doctor_id,
                MedicalRecordDB.status == RecordStatus.completed.value,
            ).limit(1)
        )).scalar_one_or_none()
        if not has_record:
            seed = MedicalRecordDB(
                patient_id=patient.id,
                doctor_id=resolved_doctor_id,
                record_type="visit",
                status=RecordStatus.completed.value,
                chief_complaint="右侧颈动脉内膜剥脱术（CEA）后2周，右侧头痛3天，加重1天",
                present_illness="患者2周前因右侧颈内动脉重度狭窄（>90%）行CEA手术，术后恢复顺利。3天前无明显诱因出现右侧搏动性头痛，初起时可忍受，昨日开始加重，今晨自测血压160/95mmHg（平时130/80mmHg）。无恶心呕吐，无肢体无力，无言语障碍，无视物模糊。",
                past_history="高血压病史10年，口服氨氯地平5mg/日，血压控制可。2型糖尿病5年，口服二甲双胍。无药物过敏史。",
                allergy_history="无药物过敏史",
                family_history="无特殊",
                personal_history="无吸烟饮酒史",
                physical_exam="神清语利。右侧颈部切口愈合好，无红肿渗出。右侧颞部压痛（+）。双侧瞳孔等大等圆3mm，对光反射灵敏。四肢肌力V级，病理征（-）。",
                auxiliary_exam="术后复查颈动脉超声：右侧CEA术后改变，管腔通畅，无再狭窄。",
                content="右侧CEA术后2周，右侧头痛3天加重1天。高血压10年，糖尿病5年。",
            )
            db.add(seed)
            await db.commit()

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
    db: AsyncSession = Depends(get_db),
):
    """Create or reset deterministic onboarding proof data for dev/test use."""
    if is_production():
        raise HTTPException(status_code=404, detail="Not found")

    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)

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
    auto_handled = await _ensure_auto_handled_messages(
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
        auto_handled_messages=auto_handled,
    )


# ── Preseed Demo Data ─────────────────────────────────────────────────────────

def _require_demo_seed_access():
    if os.environ.get("ALLOW_DEMO_SEED", "true").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/api/manage/onboarding/seed-demo", include_in_schema=True)
async def seed_demo(
    body: OnboardingExamplesRequest,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Create preseed demo data (non-destructive). Safe for retry."""
    _require_demo_seed_access()
    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    from .preseed_service import seed_demo_data
    result = await seed_demo_data(db, resolved_doctor_id)
    if not result.already_seeded:
        await db.commit()
    return result.model_dump()


@router.post("/api/manage/onboarding/seed-demo/reset", include_in_schema=True)
async def seed_demo_reset(
    body: OnboardingExamplesRequest,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Delete and recreate all preseed demo data."""
    _require_demo_seed_access()
    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    from .preseed_service import cleanup_seed_data, seed_demo_data
    await cleanup_seed_data(db, resolved_doctor_id)
    result = await seed_demo_data(db, resolved_doctor_id)
    await db.commit()
    return result.model_dump()


@router.delete("/api/manage/onboarding/seed-demo", include_in_schema=True)
async def seed_demo_delete(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Remove all preseed demo data for a doctor."""
    _require_demo_seed_access()
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    from .preseed_service import cleanup_seed_data
    await cleanup_seed_data(db, resolved_doctor_id)
    await db.commit()
    return {"status": "ok", "deleted": True}
