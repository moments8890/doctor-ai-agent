"""
门诊病历图片导入管线：文件校验 → PDF/图片转换 → Vision LLM 提取 → 结构化记录 → 持久化。

Supports JPG, PNG, and PDF uploads. PDF pages are converted to images via
pdftoppm, then all images are sent to the configured vision LLM in a single
multi-image request. The LLM returns structured JSON matching the 14-field
OutpatientRecord schema.

Provider selection reuses the same env vars as ``services.ai.vision``:
    VISION_LLM          Provider: ollama | gemini | openai  (default: ollama)
    OLLAMA_VISION_MODEL / OLLAMA_BASE_URL / OLLAMA_API_KEY
    GEMINI_API_KEY / GEMINI_VISION_MODEL
    OPENAI_API_KEY
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Optional

from domain.records.schema import (
    FIELD_KEYS,
    OUTPATIENT_FIELD_META,
    OutpatientRecord,
    PatientInfo,
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
# JSON response parsing
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, with bracket-matching fallback.

    Raises ValueError with ``422:`` prefix if parsing fails.
    """
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Bracket-matching fallback
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("422:无法解析 Vision LLM 返回的 JSON")


# ---------------------------------------------------------------------------
# Vision LLM client (reuses vision.py provider config)
# ---------------------------------------------------------------------------

def _get_vision_client():
    """Return ``(AsyncOpenAI_client, model_name)`` for the vision LLM.

    Reuses the same provider-selection logic as ``services.ai.vision``.
    """
    from openai import AsyncOpenAI

    provider_name = os.environ.get("VISION_LLM", "ollama")

    # Reuse provider config from vision.py
    from infra.llm.vision import _PROVIDERS

    cfg = _PROVIDERS.get(provider_name, _PROVIDERS["ollama"])
    model = cfg["model_default"]
    if cfg["model_env"]:
        model = os.environ.get(cfg["model_env"], model)
    api_key = os.environ.get(cfg["api_key_env"], "nokeyneeded")
    client_kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "timeout": float(os.environ.get("VISION_LLM_TIMEOUT", "120")),
        "max_retries": 0,
    }
    if cfg["base_url"]:
        client_kwargs["base_url"] = cfg["base_url"]

    is_test = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", "")
    client = AsyncOpenAI(**client_kwargs)
    return client, model, provider_name


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

async def extract_from_images(images: List[bytes]) -> OutpatientRecord:
    """Send images to Vision LLM, return validated OutpatientRecord.

    Raises ValueError (422 prefix) or propagates LLM errors.
    """
    client, model, provider_name = _get_vision_client()

    # PHI egress gate: image bytes contain clinical data.
    from infra.llm.egress import is_local_provider, check_cloud_egress

    if not is_local_provider(provider_name):
        check_cloud_egress(provider_name, "vision_import")

    _tag = f"[vision-import:{provider_name}:{model}]"
    log(f"{_tag} request: images={len(images)}")

    from utils.prompt_loader import get_prompt

    prompt_text = await get_prompt("vision-import")
    messages = _build_vision_messages(images, prompt_text)

    from infra.llm.resilience import call_with_retry_and_fallback

    fallback_model: Optional[str] = None
    if provider_name == "ollama":
        fb = os.environ.get("OLLAMA_VISION_FALLBACK_MODEL", "")
        if fb:
            fallback_model = fb

    async def _call(model_name: str):
        kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 3000,
        }
        # Try json_object response format; fall back if model doesn't support it.
        try:
            return await client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception:
            return await client.chat.completions.create(**kwargs)

    resp = await call_with_retry_and_fallback(
        _call,
        primary_model=model,
        fallback_model=fallback_model,
        max_attempts=2,
        op_name="vision_import.extract",
    )

    raw = (resp.choices[0].message.content or "").strip()
    log(f"{_tag} response: {raw[:200]}")
    if not raw:
        raise ValueError("422:Vision LLM 返回空内容")
    data = _parse_json_response(raw)

    # Build PatientInfo from extracted data
    patient_data = data.pop("patient", {}) or {}
    age_raw = patient_data.get("age")
    age: Optional[int] = None
    if age_raw is not None:
        try:
            age = int(age_raw)
        except (ValueError, TypeError):
            pass
    patient_info = PatientInfo(
        name=patient_data.get("name") or None,
        gender=patient_data.get("gender") or None,
        age=age,
    )

    # Build OutpatientRecord — only keep recognised field keys
    fields: Dict[str, Optional[str]] = {}
    for k in FIELD_KEYS:
        v = data.get(k)
        fields[k] = str(v) if v else None

    record = OutpatientRecord(patient=patient_info, **fields)

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
