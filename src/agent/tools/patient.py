"""Patient-role tools for the LangChain ReAct agent."""
from __future__ import annotations

from typing import Any, Dict, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.identity import get_current_identity


class AdvanceInterviewInput(BaseModel):
    answer: str = Field(description="患者本轮回答的原文，如'我头疼三天了'、'左边太阳穴'。")


async def _get_patient(patient_id: int) -> Optional[Any]:
    """Fetch patient by ID."""
    from db.engine import AsyncSessionLocal
    from db.models import Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Patient).where(Patient.id == patient_id))
        return result.scalar_one_or_none()


async def _get_or_create_session(patient_id: int, doctor_id: str) -> Any:
    """Find active interview session for this patient, or create one."""
    from domain.patients.interview_session import get_active_session, create_session

    session = await get_active_session(patient_id, doctor_id)
    if session is None:
        session = await create_session(doctor_id, patient_id)
    return session


@tool(args_schema=AdvanceInterviewInput)
async def advance_interview(answer: str) -> Dict[str, Any]:
    """推进预问诊流程。将患者回答传入，系统提取临床信息并返回下一个问题。
    当患者提供症状、病史、用药等临床信息时调用。闲聊或与问诊无关的消息不要调用。"""
    from domain.patients.interview_turn import interview_turn

    patient_id = int(get_current_identity())
    patient = await _get_patient(patient_id)
    if patient is None:
        return {"status": "error", "message": "未找到患者信息"}

    session = await _get_or_create_session(patient_id, patient.doctor_id)
    if session is None:
        return {"status": "error", "message": "无法创建问诊会话"}

    result = await interview_turn(session.id, answer)
    return {
        "reply": result.reply,
        "collected": result.collected,
        "progress": result.progress,
        "status": result.status,
        "complete": result.status == "reviewing",
    }


@tool
async def confirm_interview() -> Dict[str, Any]:
    """确认预问诊结果并提交给医生。在患者确认问诊内容无误后调用。"""
    from domain.patients.interview_session import get_active_session
    from domain.patients.interview_summary import confirm_interview

    patient_id = int(get_current_identity())
    patient = await _get_patient(patient_id)
    if patient is None:
        return {"status": "error", "message": "未找到患者信息"}

    session = await get_active_session(patient_id, patient.doctor_id)
    if session is None or session.status != "reviewing":
        return {"status": "error", "message": "没有待确认的问诊记录"}

    result = await confirm_interview(
        session.id, patient.doctor_id, patient_id,
        patient.name, session.collected,
    )
    return {
        "status": "confirmed",
        "message": f"问诊记录已提交给医生，请等待回复。",
        "record_id": result.get("record_id"),
    }


PATIENT_TOOLS = [advance_interview, confirm_interview]
