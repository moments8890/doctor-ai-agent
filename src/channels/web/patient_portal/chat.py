"""
Patient portal chat routes: polling + agent-style triage endpoint.

Provides:
  GET  /chat/messages — poll for new messages (patient/ai/doctor)
  POST /chat          — send a message through AI triage pipeline
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import _authenticate_patient
from db.engine import AsyncSessionLocal, get_db
from db.models.patient_message import PatientMessage
from domain.patient_lifecycle.triage import (
    TriageCategory,
    classify,
    handle_escalation,
    handle_informational,
    handle_urgent,
    load_patient_context,
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
    source: str  # patient / ai / doctor
    sender_id: Optional[str] = None
    triage_category: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_source(msg: PatientMessage) -> str:
    """Return the message source, inferring from direction for old rows."""
    if msg.source:
        return msg.source
    # Pre-migration rows: infer from direction column
    return "patient" if msg.direction == "inbound" else "ai"


def _msg_to_out(msg: PatientMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        content=msg.content,
        source=_infer_source(msg),
        sender_id=msg.sender_id,
        triage_category=msg.triage_category,
        created_at=msg.created_at,
    )


# ---------------------------------------------------------------------------
# Categories that the AI handles directly (no doctor escalation).
# ---------------------------------------------------------------------------

_AI_HANDLED_CATEGORIES = {TriageCategory.informational}


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
    """Save patient message and generate a draft reply for doctor review.

    No auto-reply to patient. No triage classification.
    All replies go through doctor review via draft_reply pipeline.
    """
    patient = await _authenticate_patient(x_patient_token, authorization)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息内容不能为空")

    enforce_doctor_rate_limit(
        str(patient.id), scope="patient_portal.chat", max_requests=10,
    )

    doctor_id = patient.doctor_id

    try:
        # Save inbound message
        from db.crud.patient_message import save_patient_message
        saved_msg = await save_patient_message(
            db, patient_id=patient.id, doctor_id=doctor_id,
            content=text, direction="inbound", source="patient",
            ai_handled=False,
        )

        # Load patient context for draft generation
        patient_context = await load_patient_context(patient.id, doctor_id, db)
        context_str = json.dumps(patient_context, ensure_ascii=False) if patient_context else ""

        # Generate draft reply for doctor (fire-and-forget)
        from domain.patient_lifecycle.triage_handlers import _generate_draft_for_escalated
        safe_create_task(
            _generate_draft_for_escalated(
                doctor_id, patient.id, saved_msg.id, text, context_str,
            ),
            name=f"draft-reply-{saved_msg.id}",
        )

        # Update last_activity_at
        try:
            from db.crud.patient import touch_patient_activity
            async with AsyncSessionLocal() as _act_db:
                await touch_patient_activity(_act_db, patient.id)
        except Exception:
            pass

        logger.info("[PatientChat] message saved, draft scheduled | patient_id=%s", patient.id)

    except Exception:
        logger.exception("[PatientChat] failed | patient_id=%s", patient.id)
        from db.crud.patient_message import save_patient_message
        async with AsyncSessionLocal() as fallback_db:
            await save_patient_message(
                fallback_db, patient_id=patient.id, doctor_id=doctor_id,
                content=text, direction="inbound", source="patient",
            )
            await fallback_db.commit()

    safe_create_task(audit(
        doctor_id, "WRITE",
        resource_type="patient_chat", resource_id=str(patient.id),
    ))

    return ChatResponse(
        reply="",
        triage_category="pending",
        ai_handled=False,
    )


@chat_router.get("/chat/messages")
async def get_chat_messages(
    since: Optional[int] = Query(default=None, description="Last message ID for polling"),
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Poll for chat messages (patient/ai/doctor).

    If *since* is provided, only messages with ``id > since`` are returned
    (long-polling pattern).  Otherwise returns the full conversation.
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
    stmt = stmt.order_by(PatientMessage.created_at.asc()).limit(200)

    result = await db.execute(stmt)
    messages = result.scalars().all()

    safe_create_task(audit(
        "patient", "READ",
        resource_type="chat_messages", resource_id=str(patient.id),
    ))
    return [_msg_to_out(m) for m in messages]


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

    # Verify the message belongs to this patient
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
