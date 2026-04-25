"""Patient interview API endpoints (ADR 0016)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from channels.web.patient_portal.auth import _authenticate_patient


class InterviewTurnRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    # Patient-controlled free text. 16k chars is generous for a single
    # interview turn but bounded so a malicious client can't DOS by
    # POSTing megabyte-scale strings.
    text: str = Field(..., max_length=16000)


class InterviewSessionRequest(BaseModel):
    session_id: str = Field(..., max_length=64)


class InterviewStartRequest(BaseModel):
    """Optional body for /start — lets the patient portal pass an explicit
    ``template_id``. When omitted the handler falls back to the doctor's
    ``preferred_template_id`` and finally to ``medical_general_v1``.
    """
    template_id: Optional[str] = Field(default=None, max_length=64)


from db.models.interview_session import InterviewStatus
from domain.patients.completeness import count_filled
from domain.patients.interview_session import (
    create_session,
    get_active_session,
    load_session,
    save_session,
)
from domain.patients.interview_summary import confirm_interview
from domain.interview.engine import InterviewEngine
from domain.interview.templates import UnknownTemplate, get_template


def _session_readiness(session) -> tuple[bool, list[str]]:
    """Run the active template's extractor-level completeness check.

    Returns ``(ready_to_review, missing)`` where ``missing`` is the
    ``required_missing`` list (empty when ``can_complete``). Callers use
    ``ready_to_review`` to decide whether to flip status to ``reviewing``.

    Bug B fix (Phase 4 r2): previously this went through the legacy
    ``check_completeness`` helper hardcoded to ``medical_general_v1`` fields,
    so non-default templates (e.g. ``medical_neuro_v1``) got judged against
    the wrong field set.
    """
    template = get_template(session.template_id)
    state = template.extractor.completeness(session.collected or {}, "patient")
    return state.can_complete, list(state.required_missing)

router = APIRouter(prefix="/api/patient/interview", tags=["patient-interview"])

_ENGINE: InterviewEngine | None = None


def _get_engine() -> InterviewEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = InterviewEngine()
    return _ENGINE


# ── Endpoints ─────────────────────────────────────────────────────────


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


async def _resolve_start_template_id(
    doctor_id: str, explicit_template_id: Optional[str]
) -> str:
    """Resolve the template id for /start using the documented order:

    1. Explicit ``template_id`` from the request (query or body).
    2. ``doctors.preferred_template_id`` from the authenticated doctor row.
    3. Fallback: ``medical_general_v1``.

    Raises ``HTTPException(422)`` if the resolved id is not in the template
    registry so the patient sees a clear failure rather than silently
    running on a missing template.
    """
    from db.engine import AsyncSessionLocal
    from db.models.doctor import Doctor
    from sqlalchemy import select

    resolved = (explicit_template_id or "").strip() or None
    if resolved is None:
        async with AsyncSessionLocal() as db:
            doctor = (await db.execute(
                select(Doctor).where(Doctor.doctor_id == doctor_id)
            )).scalar_one_or_none()
            pref = getattr(doctor, "preferred_template_id", None) if doctor else None
            if pref and pref.strip():
                resolved = pref.strip()
    if resolved is None:
        resolved = "medical_general_v1"

    try:
        get_template(resolved)
    except UnknownTemplate:
        raise HTTPException(
            status_code=422,
            detail=f"未知的问诊模板: {resolved}",
        )
    return resolved


@router.post("/start")
async def start_interview(
    authorization: Optional[str] = Header(default=None),
    template_id: Optional[str] = Query(default=None),
    body: Optional[InterviewStartRequest] = None,
):
    """Create or resume an interview session.

    ``template_id`` may be supplied either as a query parameter or inside the
    JSON body. Resolution order on a fresh session:

    1. Explicit ``template_id`` from the request.
    2. Doctor's ``preferred_template_id``.
    3. ``medical_general_v1`` default.
    """
    patient = await _authenticate_patient(authorization)
    doctor_name = await _get_doctor_name(patient.doctor_id)

    # Check for existing active session
    active = await get_active_session(patient.id, patient.doctor_id)
    if active:
        can_complete, _missing = _session_readiness(active)
        ready_to_review = (
            active.status == InterviewStatus.reviewing or can_complete
        )
        if ready_to_review and active.status != InterviewStatus.reviewing:
            active.status = InterviewStatus.reviewing
            await save_session(active)
        return {
            "session_id": active.id,
            "reply": (
                f"欢迎回来！我已经为{doctor_name}医生整理好主要信息，请确认后提交；"
                "如果还有补充，也可以继续补充。"
                if ready_to_review
                else f"欢迎回来！我们继续为{doctor_name}医生整理您的病情信息。"
            ),
            "collected": active.collected,
            "conversation": active.conversation or [],
            "progress": {"filled": count_filled(active.collected), "total": 7},
            "status": InterviewStatus.reviewing if ready_to_review else active.status,
            "ready_to_review": ready_to_review,
            "resumed": True,
        }

    # Resolution order: explicit (query > body) → doctor.preferred_template_id → default.
    explicit = template_id if (template_id and template_id.strip()) else (
        body.template_id if (body and body.template_id) else None
    )
    resolved_template_id = await _resolve_start_template_id(
        patient.doctor_id, explicit,
    )

    session = await create_session(
        patient.doctor_id, patient.id, template_id=resolved_template_id,
    )
    return {
        "session_id": session.id,
        "reply": f"您好！我是{doctor_name if doctor_name.endswith('医生') else doctor_name + '医生'}的AI助手。请描述您的症状，我来帮您整理病历信息。",
        "collected": {},
        "progress": {"filled": 0, "total": 7},
        "status": InterviewStatus.interviewing,
        "ready_to_review": False,
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

    # Phase 2.5: routed through InterviewEngine.next_turn (engine owns the turn loop).
    from domain.patients.interview_models import InterviewResponse, _build_progress

    result = await _get_engine().next_turn(body.session_id, body.text.strip())
    reloaded = await load_session(body.session_id)

    if reloaded is None:
        response = InterviewResponse(
            reply=result.reply, collected={},
            progress={"filled": 0, "total": 0}, status="error",
            missing=list(result.state.required_missing + result.state.recommended_missing),
            suggestions=list(result.suggestions),
            ready_to_review=result.state.can_complete,
        )
    else:
        response = InterviewResponse(
            reply=result.reply,
            collected=reloaded.collected,
            progress=_build_progress(reloaded.collected, reloaded.mode),
            status=reloaded.status,
            missing=list(result.state.required_missing + result.state.recommended_missing),
            suggestions=list(result.suggestions),
            ready_to_review=result.state.can_complete,
            patient_name=result.metadata.get("patient_name"),
            patient_gender=result.metadata.get("patient_gender"),
            patient_age=result.metadata.get("patient_age"),
        )

    if response.status == "error":
        raise HTTPException(404, response.reply)

    return {
        "reply": response.reply,
        "collected": response.collected,
        "progress": response.progress,
        "status": response.status,
        "ready_to_review": response.ready_to_review,
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

    can_complete, _missing = _session_readiness(active)
    ready_to_review = (
        active.status == InterviewStatus.reviewing or can_complete
    )
    if ready_to_review and active.status != InterviewStatus.reviewing:
        active.status = InterviewStatus.reviewing
        await save_session(active)

    return {
        "session_id": active.id,
        "collected": active.collected,
        "conversation": active.conversation,
        "progress": {"filled": count_filled(active.collected), "total": 7},
        "status": InterviewStatus.reviewing if ready_to_review else active.status,
        "ready_to_review": ready_to_review,
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

    from domain.patients.interview_turn import release_session_lock
    release_session_lock(body.session_id)

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

    from domain.patients.interview_turn import release_session_lock
    release_session_lock(body.session_id)

    return {"status": InterviewStatus.abandoned}
