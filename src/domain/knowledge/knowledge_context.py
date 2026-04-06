"""
Knowledge context: load, cache, score, and render items for LLM prompts.
"""

from __future__ import annotations

import re
import time as _time
from typing import List, Sequence

from db.crud import list_doctor_knowledge_items
from db.models import DoctorKnowledgeItem
from domain.knowledge.knowledge_crud import (
    _decode_knowledge_payload,
    _sanitize_for_prompt,
    knowledge_limits,
)

# ── Cache ──────────────────────────────────────────────────────────

_KNOWLEDGE_ITEMS_CACHE: dict[str, tuple[float, list]] = {}  # doctor_id → (timestamp, raw items)
_KNOWLEDGE_CACHE_TTL = 300  # 5 minutes


def _invalidate_cache(doctor_id: str) -> None:
    """Remove a doctor's entry from the in-process cache."""
    _KNOWLEDGE_ITEMS_CACHE.pop(doctor_id, None)


# ── Scoring helpers ────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Tokenize text for KB relevance scoring. Uses jieba for Chinese."""
    if not text:
        return []
    try:
        import jieba
        return [w.lower() for w in jieba.cut(text) if len(w.strip()) >= 2]
    except ImportError:
        return [tok.lower() for tok in re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", text or "") if tok]


def _score_item(query: str, item_content: str) -> int:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0
    haystack = (item_content or "").lower()
    score = 0
    for tok in query_tokens:
        if tok in haystack:
            score += 2
    return score


def _source_weight(source: str) -> float:
    return 0.5 if source == "doctor" else 0.2


# ── Rendering ─────────────────────────────────────────────────────

def render_knowledge_context(
    query: str,
    items: Sequence[DoctorKnowledgeItem],
    patient_context: str = "",
) -> str:
    if not items:
        return ""

    limits = knowledge_limits()
    # Expand scoring query with patient fields for better relevance
    scoring_query = query
    if patient_context:
        scoring_query = "{0} {1}".format(query, patient_context)

    scored = []
    for idx, item in enumerate(items):
        text, source, confidence, _source_url, _file_path = _decode_knowledge_payload(item.content)
        if not text:
            continue
        relevance = _score_item(scoring_query, text)
        weighted = float(relevance) + _source_weight(source) + float(confidence)
        scored.append((weighted, relevance, -idx, item, text))

    scored.sort(reverse=True)

    # Hard cap: top-5 items by score, then soft cap on total chars
    MAX_ITEMS = 5
    header = "【医生知识库】\n"
    lines: List[str] = []
    total = len(header)
    for weighted, relevance, _ord, item, text in scored:
        if len(lines) >= MAX_ITEMS:
            break
        snippet = _sanitize_for_prompt((text or "").strip())
        if not snippet:
            continue
        line = "[KB-{0}] {1}".format(item.id, snippet)
        projected = total + len(line) + 1
        if projected > limits["max_chars"]:
            break
        lines.append(line)
        total = projected

    if not lines:
        return ""

    return header + "\n".join(lines)


# ── Load helpers ───────────────────────────────────────────────────

async def load_knowledge(
    doctor_id: str,
    query: str = "",
    patient_context: str = "",
) -> str:
    """Load all knowledge items for a doctor, scored against query."""
    from db.engine import AsyncSessionLocal

    if not doctor_id:
        return ""

    limits = knowledge_limits()
    async with AsyncSessionLocal() as session:
        items = await list_doctor_knowledge_items(
            session, doctor_id, limit=limits["candidate_limit"],
        )
    if not items:
        return ""

    return render_knowledge_context(query=query, items=items, patient_context=patient_context)


async def load_knowledge_context_for_prompt(session, doctor_id: str, query: str) -> str:
    """Load knowledge items (cached by doctor_id) and render per-query.

    Raw items are cached by doctor_id with a 5-minute TTL to avoid repeated DB reads.
    Rendering (scoring/ranking against the query) is always done fresh so that
    different queries surface the most relevant items.
    """
    now = _time.time()
    cached = _KNOWLEDGE_ITEMS_CACHE.get(doctor_id)
    if cached and now - cached[0] < _KNOWLEDGE_CACHE_TTL:
        items = cached[1]
    else:
        limits = knowledge_limits()
        items = await list_doctor_knowledge_items(
            session,
            doctor_id,
            limit=limits["candidate_limit"],
        )
        _KNOWLEDGE_ITEMS_CACHE[doctor_id] = (now, list(items))
    return render_knowledge_context(query=query, items=items)
