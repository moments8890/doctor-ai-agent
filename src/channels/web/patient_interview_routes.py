"""Patient interview API endpoints (ADR 0016)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from channels.web.patient_portal_auth import _authenticate_patient


class InterviewTurnRequest(BaseModel):
    session_id: str
    text: str


class InterviewSessionRequest(BaseModel):
    session_id: str
from db.models.interview_session import InterviewStatus
from domain.patients.completeness import count_filled
from domain.patients.interview_session import (
    create_session,
    get_active_session,
    load_session,
    save_session,
)
from domain.patients.interview_summary import confirm_interview
from domain.patients.interview_turn import interview_turn
from utils.log import log

router = APIRouter(prefix="/api/patient/interview", tags=["patient-interview"])


# ── Agent-powered chat (new) ──────────────────────────────────────────


class PatientChatRequest(BaseModel):
    text: str


@router.post("/chat")
async def patient_chat(
    body: PatientChatRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Patient chat — routes through ReAct agent with interview + chat tools.

    This is the primary endpoint for the mini-program. The agent decides
    whether to advance the interview, answer off-topic questions, or
    confirm the interview based on conversation context.
    """
    from agent import handle_turn

    patient = await _authenticate_patient(authorization)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    if len(text) > 2000:
        raise HTTPException(400, "消息过长")

    reply = await handle_turn(text, "patient", str(patient.id))
    return {"reply": reply}


# ── Legacy endpoints (backward compat) ────────────────────────────────


async def _get_doctor_name(doctor_id: str) -> str:
    """Look up doctor display name."""
    from db.engine import AsyncSessionLocal
    from db.models import Doctor
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        doctor = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == doctor_id)
        )).scalar_one_or_none()
    return (doctor.name if doctor else None) or "医生"


@router.post("/start")
async def start_interview(
    authorization: Optional[str] = Header(default=None),
):
    """Create or resume an interview session."""
    patient = await _authenticate_patient(authorization)
    doctor_name = await _get_doctor_name(patient.doctor_id)

    # Check for existing active session
    active = await get_active_session(patient.id, patient.doctor_id)
    if active:
        return {
            "session_id": active.id,
            "reply": f"欢迎回来！我们继续为{doctor_name}医生整理您的病情信息。",
            "collected": active.collected,
            "progress": {"filled": count_filled(active.collected), "total": 7},
            "status": active.status,
            "resumed": True,
        }

    session = await create_session(patient.doctor_id, patient.id)
    return {
        "session_id": session.id,
        "reply": f"您好！我是{doctor_name}医生的AI助手。请描述您的症状，我来帮您整理病历信息。",
        "collected": {},
        "progress": {"filled": 0, "total": 7},
        "status": InterviewStatus.interviewing,
        "resumed": False,
    }


@router.post("/turn")
async def turn(
    body: InterviewTurnRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Send a patient message and get AI reply."""
    patient = await _authenticate_patient(authorization)

    if not body.text.strip():
        raise HTTPException(400, "消息不能为空")
    if len(body.text) > 2000:
        raise HTTPException(400, "消息过长")

    # Verify session ownership before processing
    session = await load_session(body.session_id)
    if session is None:
        raise HTTPException(404, "问诊会话不存在")
    if session.patient_id != patient.id:
        raise HTTPException(403, "无权操作")

    response = await interview_turn(body.session_id, body.text.strip())

    if response.status == "error":
        raise HTTPException(404, response.reply)

    return {
        "reply": response.reply,
        "collected": response.collected,
        "progress": response.progress,
        "status": response.status,
        "missing_fields": response.missing or [],
        "complete": len(response.missing or []) == 0,
        "suggestions": response.suggestions or [],
    }


@router.get("/current")
async def current_session(
    authorization: Optional[str] = Header(default=None),
):
    """Get active interview session state, or null."""
    patient = await _authenticate_patient(authorization)
    active = await get_active_session(patient.id, patient.doctor_id)

    if active is None:
        return None

    return {
        "session_id": active.id,
        "collected": active.collected,
        "conversation": active.conversation,
        "progress": {"filled": count_filled(active.collected), "total": 7},
        "status": active.status,
    }


@router.post("/confirm")
async def confirm(
    body: InterviewSessionRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Patient confirms interview summary -> creates record + task."""
    patient = await _authenticate_patient(authorization)

    session = await load_session(body.session_id)
    if session is None:
        raise HTTPException(404, "问诊会话不存在")
    if session.patient_id != patient.id:
        raise HTTPException(403, "无权操作")
    if session.status not in (InterviewStatus.reviewing, InterviewStatus.interviewing):
        raise HTTPException(400, "该问诊已结束")

    # Perform handoff (includes reconciliation sweep over full transcript)
    result = await confirm_interview(
        session_id=session.id,
        doctor_id=session.doctor_id,
        patient_id=session.patient_id,
        patient_name=patient.name,
        collected=session.collected,
        conversation=session.conversation,
    )

    # Mark session confirmed
    session.status = InterviewStatus.confirmed
    await save_session(session)

    return {
        "status": InterviewStatus.confirmed,
        "record_id": result.get("record_id"),
        "review_id": result.get("review_id"),
        "message": "您的预问诊信息已提交给医生，请等待医生审阅。",
    }


@router.post("/cancel")
async def cancel(
    body: InterviewSessionRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Abandon interview session."""
    patient = await _authenticate_patient(authorization)

    session = await load_session(body.session_id)
    if session is None:
        raise HTTPException(404, "问诊会话不存在")
    if session.patient_id != patient.id:
        raise HTTPException(403, "无权操作")
    if session.status not in (InterviewStatus.interviewing, InterviewStatus.reviewing):
        raise HTTPException(400, "该问诊已结束")

    session.status = InterviewStatus.abandoned
    await save_session(session)

    return {"status": InterviewStatus.abandoned}
