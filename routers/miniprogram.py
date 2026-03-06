from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

import routers.records as records_router
import routers.tasks as tasks_router
import routers.ui as ui_router
import routers.voice as voice_router
from services.miniprogram_auth import (
    MiniProgramAuthError,
    MiniProgramPrincipal,
    parse_bearer_token,
    verify_miniprogram_token,
)

router = APIRouter(prefix="/api/mini", tags=["mini"])


def _require_mini_principal(authorization: Optional[str] = Header(default=None)) -> MiniProgramPrincipal:
    try:
        token = parse_bearer_token(authorization)
        principal = verify_miniprogram_token(token)
    except MiniProgramAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if principal.channel != "wechat_mini":
        raise HTTPException(status_code=403, detail="Token channel not allowed for mini endpoints")
    return principal


class MiniChatInput(BaseModel):
    text: str
    history: List[records_router.HistoryMessage] = Field(default_factory=list)


class MiniTaskPatchBody(BaseModel):
    status: str


@router.get("/me")
async def mini_me(principal: MiniProgramPrincipal = Depends(_require_mini_principal)) -> dict:
    return {
        "doctor_id": principal.doctor_id,
        "channel": principal.channel,
        "wechat_openid": principal.wechat_openid,
    }


@router.post("/chat", response_model=records_router.ChatResponse)
async def mini_chat(
    body: MiniChatInput,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> records_router.ChatResponse:
    return await records_router._chat_for_doctor(
        records_router.ChatInput(
            text=body.text,
            history=body.history,
            doctor_id=principal.doctor_id,
        ),
        principal.doctor_id,
    )


@router.get("/patients")
async def mini_patients(
    category: Optional[str] = None,
    risk: Optional[str] = None,
    follow_up_state: Optional[str] = None,
    stale_risk: Optional[str] = None,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
):
    return await ui_router.manage_patients(
        doctor_id=principal.doctor_id,
        category=category,
        risk=risk,
        follow_up_state=follow_up_state,
        stale_risk=stale_risk,
    )


@router.get("/records")
async def mini_records(
    patient_id: Optional[int] = None,
    patient_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
):
    return await ui_router.manage_records(
        doctor_id=principal.doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/tasks", response_model=List[tasks_router.TaskOut])
async def mini_tasks(
    status: Optional[str] = None,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> List[tasks_router.TaskOut]:
    return await tasks_router.get_tasks(doctor_id=principal.doctor_id, status=status)


@router.patch("/tasks/{task_id}", response_model=tasks_router.TaskOut)
async def mini_patch_task(
    task_id: int,
    body: MiniTaskPatchBody,
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> tasks_router.TaskOut:
    return await tasks_router.patch_task(
        task_id=task_id,
        doctor_id=principal.doctor_id,
        body=tasks_router.TaskStatusUpdate(status=body.status),
    )


@router.post("/voice/chat", response_model=voice_router.VoiceChatResponse)
async def mini_voice_chat(
    audio: UploadFile = File(...),
    history: Optional[str] = Form(default=None),
    principal: MiniProgramPrincipal = Depends(_require_mini_principal),
) -> voice_router.VoiceChatResponse:
    return await voice_router.voice_chat(
        audio=audio,
        doctor_id=principal.doctor_id,
        history=history,
    )
