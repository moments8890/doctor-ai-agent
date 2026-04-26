"""
Patient portal chat routes — IntakeEngine-backed dispatch.

Provides:
  GET  /chat/messages          — poll for new messages (patient/ai/doctor/system)
  POST /chat                   — send a message; routes to IntakeEngine on
                                 symptom_report, otherwise hands off to a
                                 doctor-review draft and acknowledges to patient
  POST /chat/confirm           — patient confirms the active intake session;
                                 IntakeEngine.confirm() persists the record and
                                 we write its id back onto intake_sessions
  POST /messages/{id}/read     — mark a message as read

The dispatch is intentionally thin: the engine owns the turn loop, prompt
shape, completeness, and persistence. This module's only job is to wire
patient_messages, triage classification, and engine calls together.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import _authenticate_patient
from db.engine import AsyncSessionLocal
from db.engine import get_db
from db.models.intake_session import IntakeSessionDB, IntakeStatus
from db.models.patient_message import PatientMessage
from domain.intake.engine import IntakeEngine
from domain.patient_lifecycle.triage import (
    TriageCategory,
    classify,
    load_patient_context,
)
from domain.patient_lifecycle.triage_handlers import _generate_draft_for_escalated
from domain.patients.intake_session import (
    create_session,
    get_active_session,
    load_session,
)
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit
from utils.log import safe_create_task

logger = logging.getLogger(__name__)

chat_router = APIRouter(tags=["patient-portal"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    text: str = Field(..., max_length=2000)


class ChatResponse(BaseModel):
    reply: str
    triage_category: str
    ai_handled: bool


class ChatMessageOut(BaseModel):
    id: int
    content: str
    source: str  # patient / ai / doctor / system
    sender_id: Optional[str] = None
    triage_category: Optional[str] = None
    ai_handled: Optional[bool] = None
    created_at: datetime


class ConfirmRequest(BaseModel):
    session_id: str = Field(..., max_length=64)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Single shared engine instance — same pattern as patient_intake_routes.
_ENGINE: IntakeEngine | None = None


def _get_engine() -> IntakeEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = IntakeEngine()
    return _ENGINE


def _infer_source(msg: PatientMessage) -> str:
    """Return the message source, inferring from direction for legacy rows."""
    if msg.source:
        return msg.source
    return "patient" if msg.direction == "inbound" else "ai"


def _msg_to_out(msg: PatientMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        content=msg.content,
        source=_infer_source(msg),
        sender_id=msg.sender_id,
        triage_category=msg.triage_category,
        ai_handled=msg.ai_handled,
        created_at=msg.created_at,
    )


# Patient-side ack used for non-intake messages. The doctor's reviewed reply
# is what eventually reaches the patient — this just closes the "did my
# message send?" gap.
_NON_INTAKE_ACK_TEXT = "您的医生将尽快查看并回复您，请稍候。"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@chat_router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Save patient message and route to intake engine or doctor draft."""
    await _authenticate_patient(x_patient_token, authorization)
    return await _intake_dispatch(body, x_patient_token, authorization, db)


async def _intake_dispatch(
    body: ChatRequest,
    x_patient_token: Optional[str],
    authorization: Optional[str],
    db: AsyncSession,
) -> ChatResponse:
    """Route an inbound chat turn.

    intake (symptom_report)  → IntakeEngine.next_turn(); engine handles
                               extraction, completeness, status transitions,
                               and conversation persistence.
    non-intake               → schedule a doctor-review draft in the
                               background and emit a system ack for the
                               patient. AI never auto-replies clinically;
                               the doctor's reviewed reply is what reaches
                               the patient.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息内容不能为空")

    enforce_doctor_rate_limit(
        str(patient.id), scope="patient_portal.chat", max_requests=10,
    )

    doctor_id = patient.doctor_id
    patient_id = patient.id

    # 1. Save the inbound patient message immediately. intake_session_id is
    #    patched after we know which session this turn belongs to (if any).
    patient_msg = PatientMessage(
        patient_id=patient_id, doctor_id=doctor_id,
        content=text, direction="inbound", source="patient",
        ai_handled=False,
        is_whitelist_reply=False, retracted=False,
    )
    db.add(patient_msg)
    await db.flush()

    # 2. Triage classify — used solely to decide is_intake vs. non-intake.
    try:
        patient_context = await load_patient_context(patient_id, doctor_id, db)
        triage = await classify(
            message=text,
            patient_context=patient_context or {},
            doctor_id=doctor_id,
        )
        category_value = triage.category.value
        is_intake = triage.category == TriageCategory.symptom_report
    except Exception:
        logger.exception(
            "[PatientChat] triage classify failed | patient_id=%s", patient_id,
        )
        # Safe fallback: treat as non-intake so the doctor still gets a draft.
        category_value = "general_question"
        is_intake = False

    # 3a. Non-intake path: queue a doctor draft, emit a system ack, return.
    if not is_intake:
        try:
            ctx_str = json.dumps(patient_context, ensure_ascii=False) if patient_context else ""
        except Exception:
            ctx_str = ""

        await db.commit()  # commit the inbound row before scheduling work

        safe_create_task(
            _generate_draft_for_escalated(
                doctor_id, patient_id, patient_msg.id, text, ctx_str,
            ),
            name=f"draft-reply-{patient_msg.id}",
        )

        # System ack — visible to the patient as a "we got your message" line.
        async with AsyncSessionLocal() as ack_db:
            ack_db.add(PatientMessage(
                patient_id=patient_id, doctor_id=doctor_id,
                content=_NON_INTAKE_ACK_TEXT,
                direction="outbound", source="system",
                ai_handled=True,
                is_whitelist_reply=False, retracted=False,
            ))
            await ack_db.commit()

        safe_create_task(audit(
            doctor_id, "WRITE",
            resource_type="patient_chat", resource_id=str(patient_id),
        ))
        return ChatResponse(
            reply=_NON_INTAKE_ACK_TEXT,
            triage_category="other",
            ai_handled=True,
        )

    # 3b. Intake path: find or create an active intake session, then turn.
    session = await get_active_session(patient_id, doctor_id)
    if session is None:
        session = await create_session(
            doctor_id=doctor_id,
            patient_id=patient_id,
            mode="patient",
            template_id="medical_general_v1",
        )

    # Stamp the session id on the inbound message before committing.
    patient_msg.intake_session_id = session.id
    await db.commit()

    # IntakeEngine owns the turn loop: it loads the session, calls the LLM,
    # merges fields, appends the assistant turn, and saves the session.
    try:
        result = await _get_engine().next_turn(session.id, text)
    except Exception:
        logger.exception(
            "[PatientChat] IntakeEngine.next_turn failed | session=%s",
            session.id,
        )
        return ChatResponse(
            reply="系统暂时繁忙，请稍后再试。",
            triage_category=category_value,
            ai_handled=False,
        )

    # Mirror the engine's assistant reply into patient_messages so the chat
    # poller surfaces it next to the patient's turn.
    async with AsyncSessionLocal() as ai_db:
        ai_db.add(PatientMessage(
            patient_id=patient_id, doctor_id=doctor_id,
            content=result.reply,
            direction="outbound", source="ai",
            ai_handled=True,
            intake_session_id=session.id,
            is_whitelist_reply=False, retracted=False,
        ))
        await ai_db.commit()

    safe_create_task(audit(
        doctor_id, "WRITE",
        resource_type="patient_chat", resource_id=str(patient_id),
    ))
    return ChatResponse(
        reply=result.reply,
        triage_category=category_value,
        ai_handled=True,
    )


# ---------------------------------------------------------------------------
# Polling endpoint
# ---------------------------------------------------------------------------

@chat_router.get("/chat/messages")
async def get_chat_messages(
    since: Optional[int] = Query(default=None, description="Last message ID for polling"),
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Poll for chat messages (patient/ai/doctor/system).

    If *since* is provided, only messages with ``id > since`` are returned.
    Drafts awaiting doctor review (source=ai + ai_handled=False) are filtered
    out so the patient never sees them.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)

    stmt = (
        select(PatientMessage)
        .where(
            PatientMessage.patient_id == patient.id,
            PatientMessage.doctor_id == patient.doctor_id,
        )
    )
    if since is not None:
        stmt = stmt.where(PatientMessage.id > since)

    stmt = stmt.where(
        or_(
            PatientMessage.source != "ai",
            and_(
                PatientMessage.source == "ai",
                PatientMessage.ai_handled == True,  # noqa: E712
            ),
        )
    )
    stmt = stmt.order_by(PatientMessage.created_at.asc()).limit(200)

    result = await db.execute(stmt)
    messages = result.scalars().all()

    safe_create_task(audit(
        "patient", "READ",
        resource_type="chat_messages", resource_id=str(patient.id),
    ))
    return [_msg_to_out(m) for m in messages]


# ---------------------------------------------------------------------------
# Confirm endpoint — patient finalizes the intake summary
# ---------------------------------------------------------------------------

@chat_router.post("/chat/confirm")
async def confirm_intake_session(
    body: ConfirmRequest,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Patient confirms the active intake session.

    Calls IntakeEngine.confirm(), which runs batch re-extract, persists the
    medical_record via the template's writer, and marks the session
    confirmed. We then stamp the resulting medical_record_id onto the
    intake_sessions row so callers can navigate session → record.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)

    session = await load_session(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="问诊会话不存在")
    if session.patient_id != patient.id:
        raise HTTPException(status_code=403, detail="无权操作")
    if session.status not in (IntakeStatus.active, IntakeStatus.reviewing):
        raise HTTPException(status_code=400, detail="该问诊已结束")

    try:
        ref = await _get_engine().confirm(body.session_id)
    except Exception:
        logger.exception(
            "[PatientChat] IntakeEngine.confirm failed | session=%s",
            body.session_id,
        )
        raise HTTPException(status_code=500, detail="提交失败，请稍后再试")

    # Write medical_record_id back onto intake_sessions. Engine.confirm()
    # already flips status to confirmed, but it doesn't know about the
    # foreign-key column we added in 6a5d3c2e1f47.
    if ref.kind == "medical_record":
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(IntakeSessionDB).where(IntakeSessionDB.id == body.session_id)
            )).scalar_one_or_none()
            if row is not None:
                row.medical_record_id = ref.id
                await db.commit()

    safe_create_task(audit(
        session.doctor_id, "WRITE",
        resource_type="intake_session", resource_id=body.session_id,
    ))
    return {
        "status": "confirmed",
        "session_id": body.session_id,
        "record_id": ref.id if ref.kind == "medical_record" else None,
        "ref": {"kind": ref.kind, "id": ref.id},
        "message": "您的问诊信息已提交给医生，请等待医生审阅。",
    }


# ---------------------------------------------------------------------------
# Mark-read endpoint
# ---------------------------------------------------------------------------

@chat_router.post("/messages/{message_id}/read")
async def mark_message_read(
    message_id: int,
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Mark a message as read by setting read_at = utcnow().

    Only messages belonging to the authenticated patient can be marked.
    Idempotent: if already read, returns ok without updating.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)

    msg = (
        await db.execute(
            select(PatientMessage).where(
                PatientMessage.id == message_id,
                PatientMessage.patient_id == patient.id,
            )
        )
    ).scalar_one_or_none()

    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")

    if msg.read_at is None:
        msg.read_at = datetime.now(timezone.utc)
        await db.commit()

    return {"status": "ok"}
