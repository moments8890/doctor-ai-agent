"""数据库驱动的提示词加载器（含 TTL 缓存）。

Shared DB-backed prompt loader with TTL cache.

All AI prompts are stored in the ``system_prompts`` table under a symbolic key.
Hardcoded constants in each service module serve as:
  - the seed value written to DB on first startup
  - the in-code fallback if DB is unavailable

The DB is the runtime source of truth; prompts can be edited via the admin UI
at /admin → System Prompts and changes take effect within the cache TTL
(default 60 s) without a restart.

Prompt key registry
-------------------
Routing / intent
  agent.routing               Full medical intent routing system prompt
  agent.routing.compact       Compact version (default; fewer tokens)
  agent.intent_classifier     Fallback intent detection (rarely invoked)

Medical record structuring
  structuring                 Base structuring prompt
  structuring.extension       Optional doctor-defined addition (appended)
  structuring.neuro_cvd       Neuro/CVD structured extraction
  structuring.fast_cvd        Fast CVD field extraction (short dictations)
  structuring.consultation_suffix  Appended for doctor-patient dialog mode
  structuring.followup_suffix      Appended for follow-up/return visits

Other AI services
  memory.compress             Conversation compression template ({today} placeholder)
  vision.ocr                  Image OCR instruction
  transcription.medical       Whisper medical vocab bias
  transcription.consultation  Whisper consultation mode vocab
  extraction.specialty_scores Specialty scale (NIHSS/mRS/GCS/…) extraction
  patient.chat                Patient-facing health Q&A
  report.extract              Outpatient report field extraction ({records_text} placeholder)
"""

from __future__ import annotations

import time
from typing import Optional

# key → (fetched_at_monotonic, content)
_CACHE: dict[str, tuple[float, str]] = {}
_DEFAULT_TTL: float = 60.0  # seconds


async def get_prompt(key: str, fallback: str, ttl: float = _DEFAULT_TTL) -> str:
    """Return prompt content for *key* from DB, falling back to *fallback*.

    Results are cached for *ttl* seconds.  Pass ``ttl=0`` to force a DB read.

    Args:
        key:      Symbolic prompt key (e.g. ``'agent.routing.compact'``).
        fallback: Hardcoded string used when the DB row is absent or unreachable.
        ttl:      Cache lifetime in seconds.

    Returns:
        Prompt string (from DB or fallback).
    """
    if ttl > 0:
        entry = _CACHE.get(key)
        if entry and time.monotonic() - entry[0] < ttl:
            return entry[1]

    db_content = await _load_from_db(key)
    content = db_content if db_content is not None else fallback
    _CACHE[key] = (time.monotonic(), content)
    return content


async def _load_from_db(key: str) -> Optional[str]:
    try:
        from db.crud import get_system_prompt
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            row = await get_system_prompt(session, key)
            return row.content if row else None
    except Exception:
        return None


def invalidate(key: Optional[str] = None) -> None:
    """Evict *key* from the in-process cache (or all keys if *key* is None).

    Call after admin prompt edits to make changes visible immediately.
    """
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)
