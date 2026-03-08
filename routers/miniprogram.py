"""
小程序 API 路由：聚合记录、任务、患者和知识库的小程序专用 REST 接口。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

import routers.records as records_router
import routers.tasks as tasks_router
import routers.ui as ui_router
import routers.voice as voice_router
from db.crud import (
    append_conversation_turns,
    create_patient,
    delete_patient_for_doctor,
    get_patient_for_doctor,
    get_recent_conversation_turns,
    save_record,
)
from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.auth.miniprogram_auth import (
    MiniProgramAuthError,
    MiniProgramPrincipal,
    parse_bearer_token,
    verify_miniprogram_token,
)
from services.auth.rate_limit import enforce_doctor_rate_limit

router = APIRouter(prefix="/api/mini", tags=["mini"])


def _require_mini_principal(authorization: Optional[str] = Header(default=None)) -> MiniProgramPrincipal:
    try:
        token = parse_bearer_token(authorization)
        principal = verify_miniprogram_token(token)
    except MiniProgramAuthError as exc:
        logging.getLogger("auth").warning("[Mini] token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    # Accept wechat_mini (WeChat openID login) and app (invite-code login).
    if principal.channel not in {"wechat_mini", "app"}:
        raise HTTPException(status_code=403, detail="Token channel not allowed for mini endpoints")
    return principal


# ── Chat ─────────────────────────────────────────────────────────────────────

class MiniChatInput(BaseModel):
    text: str
    # history is optional; if omitted the server loads it from DB
    history: Optional[List[records_router.HistoryMessage]] = None


@router.get("/history")
async def mini_history(
    limit: int = 20,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> dict:
    """Return recent conversation turns from the shared DB-backed history."""
    async with AsyncSessionLocal() as db:
        turns = await get_recent_conversation_turns(db, principal.doctor_id, limit=limit)
    return {
        "history": [{"role": t.role, "content": t.content} for t in turns]
    }


@router.post("/chat", response_model=records_router.ChatResponse)
async def mini_chat(
    body: MiniChatInput,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> records_router.ChatResponse:
    enforce_doctor_rate_limit(principal.doctor_id, scope="mini.chat")

    # Load history from DB if not provided by client.
    if body.history is None:
        async with AsyncSessionLocal() as db:
            turns = await get_recent_conversation_turns(db, principal.doctor_id, limit=20)
        history = [records_router.HistoryMessage(role=t.role, content=t.content) for t in turns]
    else:
        history = body.history

    response = await records_router._chat_for_doctor(
        records_router.ChatInput(
            text=body.text,
            history=history,
            doctor_id=principal.doctor_id,
        ),
        principal.doctor_id,
    )

    # Persist this exchange to shared conversation turns (best-effort).
    try:
        async with AsyncSessionLocal() as db:
            await append_conversation_turns(db, principal.doctor_id, [
                {"role": "user", "content": body.text},
                {"role": "assistant", "content": response.reply},
            ])
            await db.commit()
    except Exception:
        pass  # turn persistence is non-critical; don't fail the response

    return response


# ── Patients ─────────────────────────────────────────────────────────────────

class MiniPatientCreateBody(BaseModel):
    name: str
    gender: Optional[str] = None
    age: Optional[int] = None


class MiniPatientUpdateBody(BaseModel):
    gender: Optional[str] = None
    age: Optional[int] = None


@router.get("/patients")
async def mini_patients(
    category: Optional[str] = None,
    risk: Optional[str] = None,
    follow_up_state: Optional[str] = None,
    stale_risk: Optional[str] = None,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
):
    return await ui_router._manage_patients_for_doctor(
        principal.doctor_id,
        category=category,
        risk=risk,
        follow_up_state=follow_up_state,
        stale_risk=stale_risk,
    )


@router.post("/patients", status_code=201)
async def mini_create_patient(
    body: MiniPatientCreateBody,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> dict:
    enforce_doctor_rate_limit(principal.doctor_id, scope="mini.patients.write")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    async with AsyncSessionLocal() as db:
        patient = await create_patient(db, principal.doctor_id, name, body.gender, body.age)
    return {
        "id": patient.id,
        "name": patient.name,
        "gender": patient.gender,
        "year_of_birth": patient.year_of_birth,
    }


@router.patch("/patients/{patient_id}")
async def mini_update_patient(
    patient_id: int,
    body: MiniPatientUpdateBody,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> dict:
    enforce_doctor_rate_limit(principal.doctor_id, scope="mini.patients.write")
    async with AsyncSessionLocal() as db:
        patient = await get_patient_for_doctor(db, principal.doctor_id, patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail="Patient not found")
        if body.gender in ("男", "女") and body.gender != patient.gender:
            patient.gender = body.gender
        if body.age is not None:
            from db.repositories.patients import _year_of_birth
            yob = _year_of_birth(body.age)
            if yob:
                patient.year_of_birth = yob
        await db.commit()
        await db.refresh(patient)
    return {
        "id": patient.id,
        "name": patient.name,
        "gender": patient.gender,
        "year_of_birth": patient.year_of_birth,
    }


@router.delete("/patients/{patient_id}", status_code=204)
async def mini_delete_patient(
    patient_id: int,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> None:
    enforce_doctor_rate_limit(principal.doctor_id, scope="mini.patients.write")
    async with AsyncSessionLocal() as db:
        deleted = await delete_patient_for_doctor(db, principal.doctor_id, patient_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Patient not found")


# ── Records ───────────────────────────────────────────────────────────────────

class MiniRecordCreateBody(BaseModel):
    patient_id: int
    content: str
    record_type: str = "visit"
    tags: List[str] = Field(default_factory=list)


@router.get("/records")
async def mini_records(
    patient_id: Optional[int] = None,
    patient_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
):
    return await ui_router._manage_records_for_doctor(
        principal.doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.post("/records", status_code=201)
async def mini_create_record(
    body: MiniRecordCreateBody,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> dict:
    enforce_doctor_rate_limit(principal.doctor_id, scope="mini.records.write")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="content is required")
    record = MedicalRecord(content=content, record_type=body.record_type, tags=body.tags)
    async with AsyncSessionLocal() as db:
        # Verify patient belongs to this doctor.
        patient = await get_patient_for_doctor(db, principal.doctor_id, body.patient_id)
        if patient is None:
            raise HTTPException(status_code=404, detail="Patient not found")
        db_record = await save_record(db, principal.doctor_id, record, body.patient_id)
    return {
        "id": db_record.id,
        "patient_id": db_record.patient_id,
        "content": db_record.content,
        "record_type": db_record.record_type,
        "created_at": db_record.created_at.isoformat() if db_record.created_at else None,
    }


# ── Tasks ─────────────────────────────────────────────────────────────────────

class MiniTaskPatchBody(BaseModel):
    status: str


class MiniTaskDueBody(BaseModel):
    due_at: str


class MiniTaskCreateBody(BaseModel):
    task_type: str
    title: str
    due_at: Optional[str] = None
    patient_id: Optional[int] = None
    content: Optional[str] = None


@router.get("/tasks", response_model=List[tasks_router.TaskOut])
async def mini_tasks(
    status: Optional[str] = None,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> List[tasks_router.TaskOut]:
    return await tasks_router._get_tasks_for_doctor(doctor_id=principal.doctor_id, status=status)


@router.patch("/tasks/{task_id}", response_model=tasks_router.TaskOut)
async def mini_patch_task(
    task_id: int,
    body: MiniTaskPatchBody,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> tasks_router.TaskOut:
    return await tasks_router._patch_task_for_doctor(
        task_id=task_id,
        doctor_id=principal.doctor_id,
        body=tasks_router.TaskStatusUpdate(status=body.status),
    )


@router.patch("/tasks/{task_id}/due", response_model=tasks_router.TaskOut)
async def mini_postpone_task(
    task_id: int,
    body: MiniTaskDueBody,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> tasks_router.TaskOut:
    return await tasks_router._postpone_task_for_doctor(
        task_id=task_id,
        doctor_id=principal.doctor_id,
        body=tasks_router.TaskDueUpdate(due_at=body.due_at),
    )


@router.post("/tasks", response_model=tasks_router.TaskOut, status_code=201)
async def mini_create_task(
    body: MiniTaskCreateBody,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> tasks_router.TaskOut:
    return await tasks_router._create_task_for_doctor(
        doctor_id=principal.doctor_id,
        body=tasks_router.TaskCreate(
            task_type=body.task_type,
            title=body.title,
            due_at=body.due_at,
            patient_id=body.patient_id,
            content=body.content,
        ),
    )


# ── Voice ─────────────────────────────────────────────────────────────────────

@router.post("/voice/chat", response_model=voice_router.VoiceChatResponse)
async def mini_voice_chat(
    audio: UploadFile = File(...),
    history: Optional[str] = Form(default=None),
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> voice_router.VoiceChatResponse:
    enforce_doctor_rate_limit(principal.doctor_id, scope="mini.voice")
    return await voice_router._voice_chat_for_doctor(
        audio=audio,
        doctor_id=principal.doctor_id,
        history=history,
    )


# ── Identity ──────────────────────────────────────────────────────────────────

@router.get("/me")
async def mini_me(principal: MiniProgramPrincipal = Depends(_require_mini_principal)) -> dict:
    return {
        "doctor_id": principal.doctor_id,
        "channel": principal.channel,
        "wechat_openid": principal.wechat_openid,
    }
