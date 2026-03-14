"""Shared constants used across channels and services."""
from __future__ import annotations

# ── MIME type sets ────────────────────────────────────────────────────────────

SUPPORTED_AUDIO_TYPES = frozenset({
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm",
    "audio/ogg", "audio/flac", "audio/m4a", "audio/x-m4a",
})

SUPPORTED_IMAGE_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/gif",
})
