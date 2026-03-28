"""Knowledge base management API for doctor training."""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud.doctor import (
    list_doctor_knowledge_items,
    delete_knowledge_item,
)
from domain.knowledge.doctor_knowledge import (
    save_knowledge_item,
    invalidate_knowledge_cache,
    extract_and_process_document,
    save_uploaded_knowledge,
    process_knowledge_text,
)
from channels.web.ui._utils import _resolve_ui_doctor_id
from db.models.doctor import KnowledgeCategory

router = APIRouter(tags=["ui"], include_in_schema=False)


class AddKnowledgeRequest(BaseModel):
    content: str
    category: KnowledgeCategory = KnowledgeCategory.custom


class ProcessTextRequest(BaseModel):
    text: str


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
            "title": item.title or "",
            "summary": item.summary or "",
            "reference_count": getattr(item, "reference_count", None) or 0,
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
    if len(content) > 3000:
        raise HTTPException(400, "内容过长（最多3000字）")

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


@router.post("/api/manage/knowledge/process-text")
async def process_text(
    body: ProcessTextRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Process manual text through LLM if >=500 chars."""
    _resolve_ui_doctor_id(doctor_id, authorization)  # auth check

    try:
        result = await process_knowledge_text(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return result


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


# ---------------------------------------------------------------------------
# Document upload endpoints
# ---------------------------------------------------------------------------

_ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "docx", "doc", "txt"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/api/manage/knowledge/upload/extract")
async def upload_extract(
    file: UploadFile = File(...),
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Extract text from an uploaded document, optionally LLM-processed."""
    _resolve_ui_doctor_id(doctor_id, authorization)  # auth check

    # Validate extension
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(400, "不支持的文件格式，仅支持: pdf, docx, doc, txt")

    # Read and validate size
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "文件过大，最大支持 10MB")
    if not file_bytes:
        raise HTTPException(400, "文件内容为空")

    try:
        result = await extract_and_process_document(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return result


class UploadSaveRequest(BaseModel):
    text: str
    source_filename: str
    category: KnowledgeCategory = KnowledgeCategory.custom


@router.post("/api/manage/knowledge/upload/save")
async def upload_save(
    body: UploadSaveRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Save doctor-approved extracted text as a knowledge item."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    text = body.text.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    if len(text) > 3000:
        raise HTTPException(413, "内容过长（超过3000字）")

    try:
        result = await save_uploaded_knowledge(resolved, text, body.source_filename, category=body.category)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"status": "ok", "id": result["id"], "text_preview": result["text_preview"]}


@router.get("/api/manage/knowledge/batch")
async def batch_knowledge(
    ids: str = Query(..., description="Comma-separated knowledge item IDs"),
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Fetch specific knowledge items by ID for this doctor."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    # Parse comma-separated IDs
    id_list: List[int] = []
    for part in ids.split(","):
        part = part.strip()
        if part:
            try:
                id_list.append(int(part))
            except ValueError:
                continue
    if not id_list:
        return {"items": []}

    async with AsyncSessionLocal() as session:
        items = await list_doctor_knowledge_items(session, resolved, limit=100)

    # Filter to requested IDs only
    id_set = set(id_list)
    result = []
    for item in items:
        if item.id not in id_set:
            continue
        text = item.content
        source = "doctor"
        try:
            payload = json.loads(item.content)
            if isinstance(payload, dict):
                text = payload.get("text", item.content)
                source = payload.get("source", "doctor")
        except (json.JSONDecodeError, TypeError):
            pass
        result.append({
            "id": item.id,
            "text": text,
            "source": source,
        })

    return {"items": result}
