"""Case memory — find similar confirmed cases from the doctor's history.

Uses keyword matching over medical_records with confirmed ai_suggestions.
No embeddings needed. The doctor's confirmed decisions become searchable
for future similar patients.
"""

import re
from typing import List, Dict, Any, Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.records import MedicalRecordDB
from db.models.ai_suggestion import AISuggestion
from utils.log import log


# Chinese medical term tokenizer — split on punctuation, keep meaningful chunks
_SPLIT_RE = re.compile(r'[，。、；：！？\s,.:;!?\n\t]+')
_STOP_WORDS = {
    "的", "了", "是", "在", "有", "和", "与", "及", "等", "或",
    "不", "无", "未", "已", "可", "为", "被", "将", "把", "从",
    "到", "对", "于", "以", "之", "其",
}


def _tokenize_medical(text: str) -> set:
    """Extract meaningful medical tokens from Chinese clinical text."""
    if not text:
        return set()
    tokens = set()
    for chunk in _SPLIT_RE.split(text):
        chunk = chunk.strip()
        if len(chunk) >= 2 and chunk not in _STOP_WORDS:
            tokens.add(chunk)
    return tokens


def _compute_similarity(query_tokens: set, case_tokens: set) -> float:
    """Jaccard-like similarity between two token sets."""
    if not query_tokens or not case_tokens:
        return 0.0
    intersection = query_tokens & case_tokens
    union = query_tokens | case_tokens
    return len(intersection) / len(union) if union else 0.0


async def find_similar_cases(
    session: AsyncSession,
    doctor_id: str,
    chief_complaint: str,
    present_illness: str = "",
    limit: int = 3,
    min_similarity: float = 0.15,
) -> List[Dict[str, Any]]:
    """Find similar confirmed cases from the doctor's history.

    Searches medical_records that have confirmed/edited ai_suggestions.
    Returns top N matches with similarity scores.
    """
    # Build query tokens from current patient
    query_text = f"{chief_complaint} {present_illness}".strip()
    query_tokens = _tokenize_medical(query_text)

    if not query_tokens:
        return []

    # Find records with confirmed decisions by this doctor
    stmt = (
        select(MedicalRecordDB)
        .join(AISuggestion, AISuggestion.record_id == MedicalRecordDB.id)
        .where(
            AISuggestion.doctor_id == doctor_id,
            AISuggestion.decision.in_(["confirmed", "edited"]),
        )
        .distinct()
        .limit(100)  # Cap search space
    )

    rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        return []

    # Score each record by token overlap
    scored = []
    for record in rows:
        # Build case tokens from the record's clinical text
        record_text = " ".join(filter(None, [
            record.chief_complaint or "",
            record.present_illness or "",
        ]))
        case_tokens = _tokenize_medical(record_text)

        sim = _compute_similarity(query_tokens, case_tokens)
        if sim >= min_similarity:
            scored.append((sim, record))

    if not scored:
        return []

    # Sort by similarity desc, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    # Fetch confirmed diagnoses for matched records
    results = []
    for sim, record in top:
        # Get the confirmed suggestion content
        diag_stmt = (
            select(AISuggestion)
            .where(
                AISuggestion.record_id == record.id,
                AISuggestion.doctor_id == doctor_id,
                AISuggestion.decision.in_(["confirmed", "edited"]),
            )
            .limit(3)
        )
        suggestions = (await session.execute(diag_stmt)).scalars().all()

        # Build the confirmed diagnosis text
        final_diagnosis = ", ".join(
            s.edited_text or s.content for s in suggestions if s.content
        )[:100]

        treatment = ""
        for s in suggestions:
            if s.section == "treatment" and s.content:
                treatment = (s.edited_text or s.content)[:80]
                break

        results.append({
            "record_id": record.id,
            "similarity": round(sim, 2),
            "chief_complaint": (record.chief_complaint or "")[:60],
            "final_diagnosis": final_diagnosis or "已确认",
            "treatment": treatment,
            "outcome": record.treatment_outcome or "",
            "patient_id": record.patient_id,
        })

    log(f"[case_matching] found {len(results)} similar cases for doctor {doctor_id}")
    return results
