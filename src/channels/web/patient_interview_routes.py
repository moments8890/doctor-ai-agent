"""Patient interview API endpoints (ADR 0016)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException

from channels.web.patient_portal import _authenticate_patient
from services.patient_interview.completeness import count_filled
from services.patient_interview.session import (
    create_session,
    get_active_session,
    load_session,
    save_session,
)
from services.patient_interview.summary import confirm_interview
from services.patient_interview.turn import interview_turn
from utils.log import log

router = APIRouter(prefix="/api/patient/interview", tags=["patient-interview"])

_GREETING = "您好！我是您的预问诊助手。请问您有什么不舒服？"


@router.post("/start")
async def start_interview(
    x_patient_token: Optional[str] = Header(default=None),
):
    """Create or resume an interview session."""
    patient = await _authenticate_patient(x_patient_token)

    # Check for existing active session
    active = await get_active_session(patient.id, patient.doctor_id)
    if active:
        return {
            "session_id": active.id,
            "reply": "欢迎回来！我们继续之前的问诊。",
            "collected": active.collected,
            "progress": {"filled": count_filled(active.collected), "total": 7},
            "status": active.status,
            "resumed": True,
        }

    session = await create_session(patient.doctor_id, patient.id)
    return {
        "session_id": session.id,
        "reply": _GREETING,
        "collected": {},
        "progress": {"filled": 0, "total": 7},
        "status": "interviewing",
        "resumed": False,
    }


@router.post("/turn")
async def turn(
    session_id: str = Body(...),
    text: str = Body(...),
    x_patient_token: Optional[str] = Header(default=None),
):
    """Send a patient message and get AI reply."""
    await _authenticate_patient(x_patient_token)

    if not text.strip():
        raise HTTPException(400, "消息不能为空")
    if len(text) > 2000:
        raise HTTPException(400, "消息过长")

    response = await interview_turn(session_id, text.strip())

    if response.status == "error":
        raise HTTPException(404, response.reply)

    return {
        "reply": response.reply,
        "collected": response.collected,
        "progress": response.progress,
        "status": response.status,
    }


@router.get("/current")
async def current_session(
    x_patient_token: Optional[str] = Header(default=None),
):
    """Get active interview session state, or null."""
    patient = await _authenticate_patient(x_patient_token)
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
    session_id: str = Body(...),
    x_patient_token: Optional[str] = Header(default=None),
):
    """Patient confirms interview summary -> creates record + task."""
    patient = await _authenticate_patient(x_patient_token)

    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "问诊会话不存在")
    if session.patient_id != patient.id:
        raise HTTPException(403, "无权操作")
    if session.status not in ("reviewing", "interviewing"):
        raise HTTPException(400, "该问诊已结束")

    # Perform handoff
    result = await confirm_interview(
        session_id=session.id,
        doctor_id=session.doctor_id,
        patient_id=session.patient_id,
        patient_name=patient.name,
        collected=session.collected,
    )

    # Mark session confirmed
    session.status = "confirmed"
    await save_session(session)

    return {
        "status": "confirmed",
        "record_id": result["record_id"],
        "task_id": result["task_id"],
        "message": "您的预问诊信息已提交给医生，请等待医生审阅。",
    }


@router.post("/cancel")
async def cancel(
    session_id: str = Body(...),
    x_patient_token: Optional[str] = Header(default=None),
):
    """Abandon interview session."""
    patient = await _authenticate_patient(x_patient_token)

    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "问诊会话不存在")
    if session.patient_id != patient.id:
        raise HTTPException(403, "无权操作")
    if session.status not in ("interviewing", "reviewing"):
        raise HTTPException(400, "该问诊已结束")

    session.status = "abandoned"
    await save_session(session)

    return {"status": "abandoned"}
