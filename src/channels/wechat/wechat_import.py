"""Backward-compat re-exports — logic moved to domain.records.import_history."""
from domain.records.import_history import (  # noqa: F401
    handle_import_history,
    _chunk_history_text,
    _preprocess_import_text,
    _format_import_preview,
    _mark_duplicates,
    _looks_like_chat_export,
    _extract_patient_from_ocr,
)
