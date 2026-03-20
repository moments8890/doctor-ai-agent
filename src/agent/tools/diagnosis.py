"""Diagnosis tools and case context injection for doctor chat."""
from __future__ import annotations

import time
from typing import Dict, Tuple

from db.engine import AsyncSessionLocal
from db.crud.case_history import match_cases
from utils.log import log

_case_context_cache: Dict[str, Tuple[str, float]] = {}
_CACHE_TTL = 300  # 5 minutes


async def _build_case_context(doctor_id: str, chief_complaint: str) -> str:
    """Build case context string with 5-min TTL cache.

    Returns a formatted context block for system prompt injection, or empty
    string when no similar cases are found or the query text is empty.
    """
    if not chief_complaint or not chief_complaint.strip():
        return ""

    cache_key = f"{doctor_id}:{chief_complaint[:50]}"
    now = time.time()

    if cache_key in _case_context_cache:
        cached, ts = _case_context_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return cached

    try:
        async with AsyncSessionLocal() as session:
            matched = await match_cases(
                session, doctor_id, chief_complaint, limit=2, threshold=0.5
            )

        if not matched:
            context = ""
        else:
            lines = [
                f"- {m['chief_complaint'][:30]} → {m['final_diagnosis']} ({m['similarity']:.0%})"
                for m in matched
            ]
            context = "【类似病例参考】\n" + "\n".join(lines)

        _case_context_cache[cache_key] = (context, now)
        return context

    except Exception as e:
        log(f"[case_context] failed: {e}", level="warning")
        return ""
