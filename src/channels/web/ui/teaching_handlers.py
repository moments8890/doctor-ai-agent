"""Teaching loop API: let doctors save significant edits as knowledge rules."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from channels.web.ui._utils import _resolve_ui_doctor_id
from db.engine import AsyncSessionLocal
from domain.knowledge.knowledge_crud import invalidate_knowledge_cache
from domain.knowledge.teaching import create_rule_from_edit
from utils.log import log

router = APIRouter(tags=["ui"], include_in_schema=False)


class CreateRuleRequest(BaseModel):
    doctor_id: str = "web_doctor"
    edit_id: int


@router.post("/api/manage/teaching/create-rule")
async def create_rule_from_doctor_edit(
    body: CreateRuleRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Save a doctor edit as a personal knowledge rule."""
    resolved = _resolve_ui_doctor_id(body.doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        rule = await create_rule_from_edit(db, doctor_id=resolved, edit_id=body.edit_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Edit not found or doctor mismatch")
        await db.commit()

    invalidate_knowledge_cache(resolved)
    log(f"[teaching] rule {rule.id} created from edit {body.edit_id} for doctor={resolved}")

    return {
        "status": "ok",
        "rule_id": rule.id,
        "title": rule.title,
    }
