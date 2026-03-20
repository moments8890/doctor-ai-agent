# src/db/crud/case_history.py
"""CRUD operations for case history knowledge base."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.case_history import CaseHistory
from db.models.base import _utcnow
from domain.knowledge.embedding import embed, get_model_name
from utils.log import log

SEED_DOCTOR_ID = "__seed__"


def _build_embed_text(
    chief_complaint: str,
    present_illness: Optional[str] = None,
    final_diagnosis: Optional[str] = None,
    treatment: Optional[str] = None,
) -> str:
    """Build the text to embed from case fields."""
    parts = [chief_complaint]
    if present_illness:
        parts.append(present_illness)
    if final_diagnosis:
        parts.append(f"诊断：{final_diagnosis}")
    if treatment:
        parts.append(f"治疗：{treatment}")
    return " ".join(parts)


async def create_case(
    session: AsyncSession,
    doctor_id: str,
    record_id: Optional[int],
    patient_id: Optional[int],
    chief_complaint: str,
    present_illness: str = "",
    source: Optional[str] = "review",
) -> CaseHistory:
    """Create a preliminary case. Embedding computed from chief_complaint + present_illness."""
    embed_text = _build_embed_text(chief_complaint, present_illness)
    try:
        vec = embed(embed_text)
        embedding_json = json.dumps(vec)
    except Exception as e:
        log(f"[case_history] embedding failed: {e}", level="warning")
        embedding_json = None
        vec = None

    entry = CaseHistory(
        doctor_id=doctor_id,
        record_id=record_id,
        patient_id=patient_id,
        chief_complaint=chief_complaint,
        present_illness=present_illness or None,
        confidence_status="preliminary",
        embedding=embedding_json,
        embedding_model=get_model_name() if vec else None,
        source=source,
        created_at=_utcnow(),
    )
    session.add(entry)
    return entry


async def confirm_case(
    session: AsyncSession,
    case_id: int,
    doctor_id: str,
    final_diagnosis: str,
    treatment: Optional[str] = None,
    outcome: Optional[str] = None,
    notes: Optional[str] = None,
    key_symptoms: Optional[List[str]] = None,
) -> Optional[CaseHistory]:
    """Promote a case to confirmed. Re-computes embedding with diagnosis text."""
    case = (await session.execute(
        select(CaseHistory).where(
            CaseHistory.id == case_id,
            CaseHistory.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if case is None:
        return None

    case.final_diagnosis = final_diagnosis
    case.treatment = treatment
    case.outcome = outcome
    case.notes = notes
    if key_symptoms:
        case.key_symptoms = json.dumps(key_symptoms, ensure_ascii=False)
    case.confidence_status = "confirmed"
    case.updated_at = _utcnow()

    # Re-embed with diagnosis included
    embed_text = _build_embed_text(
        case.chief_complaint, case.present_illness,
        final_diagnosis, treatment,
    )
    try:
        vec = embed(embed_text)
        case.embedding = json.dumps(vec)
        case.embedding_model = get_model_name()
    except Exception as e:
        log(f"[case_history] re-embedding failed on confirm: {e}", level="warning")

    return case


async def match_cases(
    session: AsyncSession,
    doctor_id: str,
    query_text: str,
    limit: int = 5,
    threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """Find similar confirmed cases by cosine similarity.
    Includes seed cases (__seed__ doctor_id) alongside doctor's own."""
    # Embed query
    try:
        query_vec = embed(query_text)
    except Exception as e:
        log(f"[case_history] query embedding failed: {e}", level="warning")
        return []

    # Load confirmed cases (doctor's own + seeds)
    result = await session.execute(
        select(CaseHistory).where(
            CaseHistory.doctor_id.in_([doctor_id, SEED_DOCTOR_ID]),
            CaseHistory.confidence_status == "confirmed",
            CaseHistory.embedding.isnot(None),
        )
    )
    cases = result.scalars().all()
    if not cases:
        return []

    # Compute similarities
    matches = []
    for case in cases:
        try:
            case_vec = json.loads(case.embedding)
            similarity = sum(a * b for a, b in zip(query_vec, case_vec))
            if similarity >= threshold:
                matches.append({
                    "id": case.id,
                    "chief_complaint": case.chief_complaint,
                    "final_diagnosis": case.final_diagnosis,
                    "treatment": case.treatment,
                    "outcome": case.outcome,
                    "key_symptoms": json.loads(case.key_symptoms) if case.key_symptoms else [],
                    "similarity": round(similarity, 4),
                    "is_seed": case.doctor_id == SEED_DOCTOR_ID,
                })
        except (json.JSONDecodeError, ValueError):
            continue

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:limit]


async def update_case(
    session: AsyncSession,
    case_id: int,
    doctor_id: str,
    **fields: Any,
) -> Optional[CaseHistory]:
    """Edit any field on a case. Re-computes embedding if text fields changed."""
    case = (await session.execute(
        select(CaseHistory).where(
            CaseHistory.id == case_id,
            CaseHistory.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if case is None:
        return None

    text_fields = {"chief_complaint", "present_illness", "final_diagnosis", "treatment"}
    text_changed = False
    for key, value in fields.items():
        if hasattr(case, key):
            setattr(case, key, value)
            if key in text_fields:
                text_changed = True
    case.updated_at = _utcnow()

    if text_changed:
        embed_text = _build_embed_text(
            case.chief_complaint, case.present_illness,
            case.final_diagnosis, case.treatment,
        )
        try:
            vec = embed(embed_text)
            case.embedding = json.dumps(vec)
            case.embedding_model = get_model_name()
        except Exception as e:
            log(f"[case_history] re-embedding failed on update: {e}", level="warning")

    return case


async def list_cases(
    session: AsyncSession,
    doctor_id: str,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[CaseHistory]:
    """List cases for a doctor, optionally filtered by status."""
    q = select(CaseHistory).where(CaseHistory.doctor_id == doctor_id)
    if status:
        q = q.where(CaseHistory.confidence_status == status)
    q = q.order_by(CaseHistory.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())
