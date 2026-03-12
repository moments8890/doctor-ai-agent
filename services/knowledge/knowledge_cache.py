"""
Shared knowledge-context cache: load and cache doctor knowledge context
for use in both WeChat and web chat paths.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Dict, Tuple

from db.engine import AsyncSessionLocal
from services.knowledge.doctor_knowledge import load_knowledge_context_for_prompt
from utils.log import log


# ── Cache state ───────────────────────────────────────────────────────────────

KB_CONTEXT_CACHE: Dict[str, Tuple[str, float]] = {}
KB_CONTEXT_TTL: float = 300.0  # 5 minutes

_KB_CONTEXT_LOCKS: Dict[str, asyncio.Lock] = {}
_KB_REGISTRY_LOCK = threading.Lock()


def get_kb_lock(doctor_id: str) -> asyncio.Lock:
    """Return a per-doctor asyncio lock for serialising cache updates."""
    with _KB_REGISTRY_LOCK:
        if doctor_id not in _KB_CONTEXT_LOCKS:
            _KB_CONTEXT_LOCKS[doctor_id] = asyncio.Lock()
        return _KB_CONTEXT_LOCKS[doctor_id]


# ── Public API ────────────────────────────────────────────────────────────────

async def load_cached_knowledge_context(doctor_id: str, text: str) -> str:
    """Return cached or freshly loaded knowledge context string.

    Thread/task-safe via a per-doctor asyncio.Lock.  On cache miss the function
    opens its own DB session, calls ``load_knowledge_context_for_prompt``, and
    stores the result with a TTL of ``KB_CONTEXT_TTL`` seconds.

    On any exception the function returns ``""`` so callers never need to
    worry about error handling.
    """
    async with get_kb_lock(doctor_id):
        cached_ctx, expiry = KB_CONTEXT_CACHE.get(doctor_id, ("", 0.0))
        if expiry > time.perf_counter():
            return cached_ctx
        try:
            async with AsyncSessionLocal() as session:
                ctx = await load_knowledge_context_for_prompt(session, doctor_id, text)
            KB_CONTEXT_CACHE[doctor_id] = (ctx, time.perf_counter() + KB_CONTEXT_TTL)
            return ctx
        except Exception as e:
            log(f"[KnowledgeCache] load FAILED doctor={doctor_id}: {e}")
            return ""


def invalidate_knowledge_cache(doctor_id: str) -> None:
    """Clear cached knowledge context for a single doctor."""
    KB_CONTEXT_CACHE.pop(doctor_id, None)
