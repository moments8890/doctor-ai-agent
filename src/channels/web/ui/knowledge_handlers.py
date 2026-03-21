"""Knowledge base management API for doctor training."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud.doctor import (
    list_doctor_knowledge_items,
    delete_knowledge_item,
)
from domain.knowledge.doctor_knowledge import (
    save_knowledge_item,
    invalidate_knowledge_cache,
)
from channels.web.ui._utils import _resolve_ui_doctor_id

router = APIRouter(tags=["ui"], include_in_schema=False)


class AddKnowledgeRequest(BaseModel):
    content: str
    category: str = "custom"


@router.get("/api/manage/knowledge")
async def list_knowledge(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as session:
        items = await list_doctor_knowledge_items(session, resolved, limit=100)

    result = []
    for item in items:
        # Decode the JSON payload to extract clean text
        text = item.content
        source = "doctor"
        confidence = 1.0
        try:
            import json
            payload = json.loads(item.content)
            if isinstance(payload, dict):
                text = payload.get("text", item.content)
                source = payload.get("source", "doctor")
                confidence = payload.get("confidence", 1.0)
        except (json.JSONDecodeError, TypeError):
            pass

        result.append({
            "id": item.id,
            "text": text,
            "source": source,
            "confidence": confidence,
            "category": getattr(item, "category", None) or "custom",
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })
    return {"items": result}


@router.post("/api/manage/knowledge")
async def add_knowledge(
    body: AddKnowledgeRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "内容不能为空")

    async with AsyncSessionLocal() as session:
        item = await save_knowledge_item(
            session, resolved, content,
            source="doctor", confidence=1.0,
            category=body.category,
        )
    invalidate_knowledge_cache(resolved)
    if not item:
        raise HTTPException(409, "重复内容，已存在相同知识条目")
    return {"status": "ok", "id": item.id}


@router.delete("/api/manage/knowledge/{item_id}")
async def remove_knowledge(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as session:
        deleted = await delete_knowledge_item(session, resolved, item_id)
    if not deleted:
        raise HTTPException(404, "未找到该知识条目")
    invalidate_knowledge_cache(resolved)
    return {"status": "ok"}
