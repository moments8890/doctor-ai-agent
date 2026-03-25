"""
门诊病历图片导入管线：文件校验 → PDF/图片转换 → Vision OCR → 文本提取 → 结构化记录 → 持久化。

Pipeline: Photo → vision-ocr.md (VISION_LLM) → plain text → doctor-extract.md (ROUTING_LLM) → 14 fields

Supports JPG, PNG, and PDF uploads. PDF pages are converted to images via
pdftoppm. Each image is OCR'd via Vision LLM, then the combined text is
extracted into structured fields via doctor-extract.md.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from domain.patients.interview_summary import (
    DoctorExtractResult,
    generate_content,
    extract_tags,
)
from domain.records.schema import FIELD_KEYS
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


def _detect_mime(image_bytes: bytes) -> str:
    """Detect MIME type from magic bytes, default to image/png."""
    for magic, mime in _MAGIC.items():
        if image_bytes[: len(magic)] == magic:
            return mime
    return "image/png"


# ---------------------------------------------------------------------------
# Step 1: Vision OCR — images → plain text
# ---------------------------------------------------------------------------

async def _ocr_images(images: List[bytes]) -> str:
    """OCR each image via vision-ocr.md, return combined text."""
    from infra.llm.vision import extract_text_from_image

    texts = []
    for i, img in enumerate(images):
        mime = _detect_mime(img)
        try:
            text = await extract_text_from_image(img, mime)
            if text.strip():
                texts.append(text.strip())
                log(f"[vision-import] OCR page {i+1}: {len(text)} chars")
        except Exception as exc:
            log(f"[vision-import] OCR page {i+1} failed: {exc}", level="warning")

    return "\n\n".join(texts)


# ---------------------------------------------------------------------------
# Step 2: Text → structured fields via doctor-extract.md
# ---------------------------------------------------------------------------

async def _extract_fields(text: str) -> Dict[str, str]:
    """Extract 14 clinical fields from OCR text using doctor-extract.md."""
    from agent.llm import structured_call
    from utils.prompt_loader import get_prompt_sync

    template = get_prompt_sync("intent/doctor-extract")
    prompt = template.format(
        name="未知",
        gender="未知",
        age="未知",
        transcript=text,
    )

    result = await structured_call(
        response_model=DoctorExtractResult,
        messages=[{"role": "user", "content": prompt}],
        op_name="vision_import.extract",
        env_var="ROUTING_LLM",
        temperature=0.1,
        max_tokens=2500,
    )

    # Filter to non-empty fields
    return {
        k: v.strip()
        for k, v in result.model_dump().items()
        if isinstance(v, str) and v.strip()
    }


# ---------------------------------------------------------------------------
# Full import pipeline
# ---------------------------------------------------------------------------

async def extract_from_images(images: List[bytes]) -> Dict[str, str]:
    """Pipeline: images → OCR → doctor-extract → 14-field dict.

    Returns dict of field_name → value (empty fields filtered out).
    Raises ValueError (422 prefix) or propagates LLM errors.
    """
    # Step 1: OCR
    ocr_text = await _ocr_images(images)
    if not ocr_text.strip():
        raise ValueError("422:图片中未能提取到有效文字")

    log(f"[vision-import] OCR total: {len(ocr_text)} chars")

    # Step 2: Extract fields
    fields = await _extract_fields(ocr_text)
    non_empty = len(fields)
    log(f"[vision-import] extracted {non_empty}/{len(FIELD_KEYS)} fields")
    return fields


async def import_to_interview(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    doctor_id: str,
    patient_id: Optional[int] = None,
) -> dict:
    """Import pipeline: file → images → OCR → extract → create interview session.

    Returns dict with session_id and pre-populated fields for doctor review.
    Raises ValueError (413/415/422 prefix) or RuntimeError on LLM failure.
    """
    mime = validate_upload(file_bytes, content_type)
    images = _file_to_images(file_bytes, mime)

    try:
        fields = await extract_from_images(images)
    except ValueError:
        raise
    except Exception as exc:
        log(f"[vision-import] extraction failed: {exc}")
        raise RuntimeError(f"502:Vision LLM 不可用: {exc}") from exc

    # Create interview session pre-populated with extracted fields
    from domain.patients.interview_session import create_session

    session = await create_session(
        doctor_id=doctor_id,
        patient_id=patient_id,
        mode="doctor",
        initial_fields=fields,
    )

    log(f"[vision-import] session={session.id} pre-populated={len(fields)} fields from {filename}")

    return {
        "session_id": session.id,
        "mode": "doctor",
        "source": "image_import",
        "pre_populated": fields,
    }
