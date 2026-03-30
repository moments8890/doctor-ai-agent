"""
Shared utilities for export modules: filename helpers and hash utilities.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import quote


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_SAFE_FILENAME_RE = re.compile(r"[^\w\u4e00-\u9fff\-]")


def _safe_pdf_filename(prefix: str, patient_id: int, suffix: str = "") -> str:
    """Return an opaque filename that does not contain patient name (PHI)."""
    safe_suffix = _SAFE_FILENAME_RE.sub("_", suffix)[:20] if suffix else ""
    parts = [prefix, str(patient_id)]
    if safe_suffix:
        parts.append(safe_suffix)
    return "_".join(parts) + ".pdf"


def _content_disposition(filename: str) -> str:
    """RFC 5987 Content-Disposition header value safe for any Unicode filename.

    Starlette encodes header values as latin-1, so we must percent-encode the
    filename and use the filename* parameter (RFC 6266 / RFC 5987).
    """
    encoded = quote(filename, safe="")
    return f"attachment; filename*=UTF-8''{encoded}"
