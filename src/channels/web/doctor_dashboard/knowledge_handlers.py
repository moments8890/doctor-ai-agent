"""Knowledge base management API for doctor training."""
from __future__ import annotations

import json
import pathlib as _pathlib
import pathlib
from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
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
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.models.doctor import KnowledgeCategory

# Base directory for storing original uploaded files
_UPLOADS_DIR = pathlib.Path(__file__).resolve().parents[4] / "uploads"

router = APIRouter(tags=["ui"], include_in_schema=False)


class AddKnowledgeRequest(BaseModel):
    content: str
    category: KnowledgeCategory = KnowledgeCategory.custom


class ProcessTextRequest(BaseModel):
    text: str


class VoiceExtractError(str, Enum):
    no_rule_found = "no_rule_found"
    multi_rule_detected = "multi_rule_detected"
    audio_unclear = "audio_unclear"
    too_long = "too_long"
    internal = "internal"


class VoiceRuleCandidate(BaseModel):
    content: str
    category: KnowledgeCategory


class VoiceExtractLLMResult(BaseModel):
    """Raw LLM output shape — strict JSON contract enforced via structured_call."""
    content: str | None = None
    category: KnowledgeCategory | None = None
    error: Literal["no_rule_found", "multi_rule_detected"] | None = None


class VoiceExtractResponse(BaseModel):
    """HTTP response shape returned to miniapp."""
    transcript: str
    candidate: VoiceRuleCandidate | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Voice → rule extraction helpers
# ---------------------------------------------------------------------------

from agent.llm import structured_call as _structured_call

_VOICE_PROMPT_PATH = (
    _pathlib.Path(__file__).resolve().parents[4]
    / "src" / "agent" / "prompts" / "voice_to_rule.md"
)


async def _call_voice_extract_llm(
    transcript: str,
    specialty: str,
) -> VoiceExtractLLMResult:
    """Call the LLM with voice_to_rule prompt. Returns structured result."""
    prompt_template = _VOICE_PROMPT_PATH.read_text(encoding="utf-8")
    filled = prompt_template.replace(
        "{{transcript}}", transcript
    ).replace("{{specialty}}", specialty or "")
    return await _structured_call(
        messages=[{"role": "user", "content": filled}],
        response_model=VoiceExtractLLMResult,
        op_name="voice_to_rule",
        env_var="ROUTING_LLM",
        temperature=0.1,
        max_tokens=600,
    )


async def extract_rule_from_transcript(
    transcript: str,
    specialty: str,
) -> VoiceExtractResponse:
    """Extract a candidate rule from an ASR transcript.

    Returns VoiceExtractResponse with one of:
      - candidate populated, error=None (success)
      - candidate=None, error="audio_unclear" (empty transcript)
      - candidate=None, error="no_rule_found" | "multi_rule_detected"
    """
    if not transcript.strip():
        return VoiceExtractResponse(
            transcript="",
            candidate=None,
            error="audio_unclear",
        )

    llm_result = await _call_voice_extract_llm(transcript, specialty)

    if llm_result.error:
        return VoiceExtractResponse(
            transcript=transcript,
            candidate=None,
            error=llm_result.error,
        )

    if llm_result.content and llm_result.category:
        return VoiceExtractResponse(
            transcript=transcript,
            candidate=VoiceRuleCandidate(
                content=llm_result.content,
                category=llm_result.category,
            ),
            error=None,
        )

    return VoiceExtractResponse(
        transcript=transcript,
        candidate=None,
        error="no_rule_found",
    )


@router.get("/api/manage/knowledge")
async def list_knowledge(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    items = await list_doctor_knowledge_items(session, resolved, limit=100)

    result = []
    for item in items:
        # Decode the JSON payload to extract clean text
        text = item.content
        source = "doctor"
        confidence = 1.0
        source_url = None
        file_path = None
        try:
            payload = json.loads(item.content)
            if isinstance(payload, dict):
                text = payload.get("text", item.content)
                source = payload.get("source", "doctor")
                confidence = payload.get("confidence", 1.0)
                source_url = payload.get("source_url") or None
                file_path = payload.get("file_path") or None
        except (json.JSONDecodeError, TypeError):
            pass

        entry = {
            "id": item.id,
            "text": text,
            "source": source,
            "confidence": confidence,
            "category": getattr(item, "category", None) or "custom",
            "title": item.title or "",
            "summary": item.summary or "",
            "reference_count": getattr(item, "reference_count", None) or 0,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        if source_url is not None:
            entry["source_url"] = source_url
        if file_path is not None:
            entry["file_path"] = file_path
        result.append(entry)

    return {"items": result}


@router.post("/api/manage/knowledge")
async def add_knowledge(
    body: AddKnowledgeRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "内容不能为空")
    if len(content) > 3000:
        raise HTTPException(400, "内容过长（最多3000字）")

    item = await save_knowledge_item(
        session, resolved, content,
        source="doctor", confidence=1.0,
        category=body.category,
    )
    invalidate_knowledge_cache(resolved)
    # save_knowledge_item returns the existing row on duplicate (idempotent add).
    # Both the web and WeChat channels rely on this — duplicate add is success, not error.
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


class UpdateKnowledgeRequest(BaseModel):
    text: str
    title: Optional[str] = None


@router.put("/api/manage/knowledge/{item_id}")
async def update_knowledge(
    item_id: int,
    body: UpdateKnowledgeRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Update a knowledge item's content."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    text = body.text.strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    if len(text) > 3000:
        raise HTTPException(413, "内容过长（超过3000字）")

    from db.crud.doctor import update_knowledge_item
    item = await update_knowledge_item(session, resolved, item_id, text, title=body.title)
    if not item:
        raise HTTPException(404, "未找到该知识条目")
    invalidate_knowledge_cache(resolved)
    return {"status": "ok", "id": item.id}


# ── Phase 0.5: KB curation onboarding ──────────────────────────────
# Per-item patient_safe flag and per-doctor onboarding-done flag.
# Both must be True for the curation_gate to allow a KB item in
# patient-facing replies (see src/domain/knowledge/curation_gate.py).


class PatientSafeUpdate(BaseModel):
    patient_safe: bool


@router.patch("/api/manage/knowledge/{item_id}/patient_safe")
async def update_patient_safe(
    item_id: int,
    body: PatientSafeUpdate,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Toggle the per-item patient_safe flag.

    Only the owning doctor may flip the flag. The flag has no effect
    until the doctor also sets `kb_curation_onboarding_done` (see
    POST /api/manage/knowledge/curation_onboarding_done).
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    from db.models.doctor import DoctorKnowledgeItem

    item = await session.get(DoctorKnowledgeItem, item_id)
    if not item or item.doctor_id != resolved:
        raise HTTPException(404, "未找到该知识条目")
    item.patient_safe = body.patient_safe
    await session.commit()
    invalidate_knowledge_cache(resolved)
    return {"id": item_id, "patient_safe": item.patient_safe}


@router.post("/api/manage/knowledge/curation_onboarding_done")
async def mark_curation_onboarding_done(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Mark this doctor as having completed the KB curation walkthrough.

    Idempotent — re-calling once already done is a no-op (returns the
    same shape). Doctor must hit this once after reviewing every
    existing KB item, otherwise no item's patient_safe flag is
    honored by the curation_gate.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    from db.models.doctor import Doctor

    doctor = await session.get(Doctor, resolved)
    if not doctor:
        raise HTTPException(404, "未找到该医生")
    doctor.kb_curation_onboarding_done = True
    await session.commit()
    invalidate_knowledge_cache(resolved)
    return {
        "doctor_id": resolved,
        "kb_curation_onboarding_done": True,
    }


@router.delete("/api/manage/knowledge/{item_id}")
async def remove_knowledge(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    deleted = await delete_knowledge_item(session, resolved, item_id)
    if not deleted:
        raise HTTPException(404, "未找到该知识条目")
    invalidate_knowledge_cache(resolved)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Document upload endpoints
# ---------------------------------------------------------------------------

_ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "docx", "doc", "txt", "jpg", "jpeg", "png", "webp"}
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/api/manage/knowledge/upload/extract")
async def upload_extract(
    file: UploadFile = File(...),
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Extract text from an uploaded document, optionally LLM-processed."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    # Validate extension
    filename = file.filename or "unknown"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(400, "不支持的文件格式，仅支持: pdf, docx, doc, txt, jpg, png, webp")

    # Read and validate size
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "文件过大，最大支持 10MB")
    if not file_bytes:
        raise HTTPException(400, "文件内容为空")

    # Save original file to uploads/{doctor_id}/{timestamp}_{filename}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    doctor_dir = _UPLOADS_DIR / resolved
    doctor_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = pathlib.Path(filename).name  # strip any path components
    saved_name = "{0}_{1}".format(timestamp, safe_filename)
    saved_path = doctor_dir / saved_name
    saved_path.write_bytes(file_bytes)
    # Relative path from project root for storage in payload
    relative_path = "uploads/{0}/{1}".format(resolved, saved_name)

    try:
        result = await extract_and_process_document(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(400, str(e))

    result["file_path"] = relative_path
    return result


class FetchUrlRequest(BaseModel):
    url: str


@router.post("/api/manage/knowledge/fetch-url")
async def fetch_url_extract(
    body: FetchUrlRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Fetch a URL, extract text, and LLM-process into knowledge."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    url = (body.url or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(400, "请输入有效的网址（以 http:// 或 https:// 开头）")

    from domain.knowledge.knowledge_ingest import extract_text_from_url
    try:
        result = await extract_text_from_url(url)
    except Exception as e:
        raise HTTPException(400, "无法获取该网页: {0}".format(str(e)))

    return result


class UploadSaveRequest(BaseModel):
    text: str
    source_filename: str
    category: KnowledgeCategory = KnowledgeCategory.custom
    source_url: Optional[str] = None
    file_path: Optional[str] = None


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
        result = await save_uploaded_knowledge(
            resolved, text, body.source_filename,
            category=body.category, source_url=body.source_url,
            file_path=body.file_path,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"status": "ok", "id": result["id"], "text_preview": result["text_preview"]}


@router.get("/api/manage/knowledge/batch")
async def batch_knowledge(
    ids: str = Query(..., description="Comma-separated knowledge item IDs"),
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
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

    items = await list_doctor_knowledge_items(session, resolved, limit=100)

    # Filter to requested IDs only
    id_set = set(id_list)
    result = []
    for item in items:
        if item.id not in id_set:
            continue
        text = item.content
        source = "doctor"
        source_url = None
        file_path = None
        try:
            payload = json.loads(item.content)
            if isinstance(payload, dict):
                text = payload.get("text", item.content)
                source = payload.get("source", "doctor")
                source_url = payload.get("source_url") or None
                file_path = payload.get("file_path") or None
        except (json.JSONDecodeError, TypeError):
            pass
        entry = {
            "id": item.id,
            "title": item.title or (text[:40] if text else ""),
            "text": text,
            "source": source,
        }
        if source_url is not None:
            entry["source_url"] = source_url
        if file_path is not None:
            entry["file_path"] = file_path
        result.append(entry)

    return {"items": result}


# ---------------------------------------------------------------------------
# Serve original uploaded files
# ---------------------------------------------------------------------------

@router.get("/api/manage/knowledge/file/{file_path:path}")
async def serve_knowledge_file(
    file_path: str,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
):
    """Serve an original uploaded document file.

    Security: verifies the file_path belongs to the requesting doctor
    and prevents path traversal.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    # Security: must start with uploads/{doctor_id}/
    expected_prefix = "uploads/{0}/".format(resolved)
    if not file_path.startswith(expected_prefix):
        raise HTTPException(403, "无权访问该文件")

    # Prevent path traversal
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(400, "非法文件路径")

    # Resolve to absolute path via project root
    abs_path = _UPLOADS_DIR.parent / file_path
    abs_path = abs_path.resolve()

    # Extra safety: ensure resolved path is still under _UPLOADS_DIR
    try:
        abs_path.relative_to(_UPLOADS_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "非法文件路径")

    if not abs_path.is_file():
        raise HTTPException(404, "文件不存在")

    return FileResponse(str(abs_path), filename=abs_path.name)


# ---------------------------------------------------------------------------
# Voice → rule extraction endpoint
# ---------------------------------------------------------------------------

async def _get_doctor_specialty(session: AsyncSession, doctor_id: str) -> str | None:
    """Fetch the doctor's specialty field (nullable) for prompt context."""
    from sqlalchemy import select
    from db.models.doctor import Doctor

    stmt = select(Doctor.specialty).where(Doctor.doctor_id == doctor_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row


class VoiceExtractRequestBody(BaseModel):
    doctor_id: str
    transcript: str


@router.post("/api/manage/knowledge/voice-extract")
async def voice_extract(
    body: VoiceExtractRequestBody,
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Run LLM rule extraction on a pre-transcribed string from the miniapp."""
    resolved = _resolve_ui_doctor_id(body.doctor_id, authorization)
    transcript = (body.transcript or "").strip()
    if not transcript:
        return VoiceExtractResponse(transcript="", candidate=None, error="audio_unclear")

    specialty = await _get_doctor_specialty(session, resolved) or ""
    try:
        return await extract_rule_from_transcript(transcript=transcript, specialty=specialty)
    except Exception:
        raise HTTPException(502, "Extraction error")
