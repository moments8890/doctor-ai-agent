"""
门诊病历图片导入管线：文件校验 → PDF/图片转换 → Vision LLM 提取 → 结构化记录 → 持久化。

Supports JPG, PNG, and PDF uploads. PDF pages are converted to images via
pdftoppm, then all images are sent to the configured vision LLM in a single
multi-image request. The LLM returns a validated OutpatientRecord via
structured_call.

Provider selection uses the VISION_LLM env var (must point to a
vision-capable model, e.g. gemini or a local ollama vision model).
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

from domain.records.schema import (
    FIELD_KEYS,
    OUTPATIENT_FIELD_META,
    OutpatientRecord,
)
from utils.log import log

# ---------------------------------------------------------------------------
# File validation
# ---------------------------------------------------------------------------

_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"%PDF": "application/pdf",
}
_ALLOWED_TYPES = frozenset(_MAGIC.values())
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
_MAX_PAGES = 10


def validate_upload(file_bytes: bytes, content_type: str) -> str:
    """Validate file type via magic bytes and size.

    Returns detected MIME type.
    Raises ValueError with ``413:`` or ``415:`` prefix for HTTP-mappable errors.
    """
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise ValueError("413:文件超过 20 MB 限制")
    for magic, mime in _MAGIC.items():
        if file_bytes[: len(magic)] == magic:
            return mime
    raise ValueError("415:不支持的文件类型，仅接受 JPG、PNG、PDF")


# ---------------------------------------------------------------------------
# File → images conversion
# ---------------------------------------------------------------------------

def _file_to_images(file_bytes: bytes, mime: str) -> List[bytes]:
    """Convert upload to a list of PNG image byte buffers."""
    if mime == "application/pdf":
        from utils.pdf_utils import pdf_to_images

        return pdf_to_images(file_bytes, max_pages=_MAX_PAGES)
    return [file_bytes]


# ---------------------------------------------------------------------------
# Vision LLM message construction
# ---------------------------------------------------------------------------

def _build_vision_messages(images: List[bytes], prompt_text: str) -> list:
    """Build OpenAI-format multi-image messages for the Vision LLM."""
    content: List[Dict[str, Any]] = []
    for img in images:
        b64 = base64.b64encode(img).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    content.append({"type": "text", "text": prompt_text})
    return [{"role": "user", "content": content}]


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

async def extract_from_images(images: List[bytes]) -> OutpatientRecord:
    """Send images to Vision LLM via structured_call, return validated OutpatientRecord.

    Uses VISION_LLM env var (must point to a vision-capable model).
    Raises ValueError (422 prefix) or propagates LLM errors.
    """
    from agent.llm import structured_call

    # PHI egress gate: image bytes contain clinical data.
    from infra.llm.egress import is_local_provider, check_cloud_egress
    from infra.llm.client import _get_providers

    provider_name = os.environ.get("VISION_LLM", "groq")
    if not is_local_provider(provider_name):
        check_cloud_egress(provider_name, "vision_import")

    providers = _get_providers()
    provider = providers.get(provider_name, providers.get("groq", {}))
    model = provider.get("model", "unknown")
    _tag = f"[vision-import:{provider_name}:{model}]"
    log(f"{_tag} request: images={len(images)}")

    from utils.prompt_loader import get_prompt

    prompt_text = await get_prompt("vision-import")
    messages = _build_vision_messages(images, prompt_text)

    record = await structured_call(
        response_model=OutpatientRecord,
        messages=messages,  # type: ignore[arg-type]  # vision messages use list content
        op_name="vision_import.extract",
        env_var="VISION_LLM",
        temperature=0.1,
        max_tokens=3000,
    )

    non_empty = sum(1 for k in FIELD_KEYS if getattr(record, k))
    log(f"[VisionImport] extraction ok non_empty={non_empty}/{len(FIELD_KEYS)}")
    return record


# ---------------------------------------------------------------------------
# Record → prose conversion
# ---------------------------------------------------------------------------

def record_to_prose(record: OutpatientRecord) -> str:
    """Convert OutpatientRecord to label-value prose for storage in DB content field."""
    lines: List[str] = []
    for key, label in OUTPATIENT_FIELD_META:
        value = getattr(record, key, None)
        if value:
            lines.append(f"\u3010{label}\u3011{value}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full import pipeline
# ---------------------------------------------------------------------------

async def import_medical_record(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    doctor_id: str,
    patient_id: Optional[int] = None,
) -> dict:
    """Full import pipeline: file -> images -> Vision LLM -> save record.

    Returns dict with created record info and extracted OutpatientRecord.
    Raises ValueError (413/415/422 prefix) or RuntimeError on LLM failure.
    """
    mime = validate_upload(file_bytes, content_type)
    images = _file_to_images(file_bytes, mime)

    try:
        record = await extract_from_images(images)
    except ValueError:
        raise
    except Exception as exc:
        log(f"[VisionImport] extraction failed: {exc}")
        raise RuntimeError(f"502:Vision LLM 不可用: {exc}") from exc

    content = record_to_prose(record)
    if not content.strip():
        content = f"[导入文件: {filename}] 未能提取到有效内容"

    # Build tags from diagnosis if available
    tags: List[str] = []
    if record.diagnosis:
        tags.append("导入")

    # Persist via the existing save_record() path
    from db.engine import AsyncSessionLocal
    from db.crud.records import save_record
    from db.models.medical_record import MedicalRecord

    medical_record = MedicalRecord(
        content=content,
        tags=tags or ["导入"],
        record_type="import",
    )

    async with AsyncSessionLocal() as session:
        db_record = await save_record(
            session,
            doctor_id=doctor_id,
            record=medical_record,
            patient_id=patient_id,
            needs_review=True,
        )
        record_id = db_record.id

    log(
        f"[VisionImport] record saved id={record_id} "
        f"doctor={doctor_id} patient={patient_id}"
    )

    return {
        "record_id": record_id,
        "record_type": "import",
        "needs_review": True,
        "content": content,
        "extracted": record.model_dump(),
    }
