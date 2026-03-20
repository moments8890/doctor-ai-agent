"""CRUD operations for diagnosis results (clinical decision support)."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.diagnosis_result import DiagnosisResult, DiagnosisStatus
from db.models.base import _utcnow


async def create_pending_diagnosis(
    session: AsyncSession,
    record_id: int,
    doctor_id: str,
) -> DiagnosisResult:
    """Create a pending diagnosis_results row (status=pending)."""
    diagnosis = DiagnosisResult(
        record_id=record_id,
        doctor_id=doctor_id,
        status=DiagnosisStatus.pending,
        created_at=_utcnow(),
    )
    session.add(diagnosis)
    return diagnosis


async def save_completed_diagnosis(
    session: AsyncSession,
    diagnosis_id: int,
    ai_output_json: str,
    red_flags: Optional[str],
    case_references: Optional[str],
) -> Optional[DiagnosisResult]:
    """Update pending → completed with AI results."""
    diagnosis = (await session.execute(
        select(DiagnosisResult).where(DiagnosisResult.id == diagnosis_id)
    )).scalar_one_or_none()
    if diagnosis is None:
        return None

    diagnosis.ai_output = ai_output_json
    diagnosis.red_flags = red_flags
    diagnosis.case_references = case_references
    diagnosis.status = DiagnosisStatus.completed
    diagnosis.completed_at = _utcnow()
    return diagnosis


async def save_failed_diagnosis(
    session: AsyncSession,
    diagnosis_id: int,
    error_message: str,
) -> Optional[DiagnosisResult]:
    """Update pending → failed with error message."""
    diagnosis = (await session.execute(
        select(DiagnosisResult).where(DiagnosisResult.id == diagnosis_id)
    )).scalar_one_or_none()
    if diagnosis is None:
        return None

    diagnosis.status = DiagnosisStatus.failed
    diagnosis.error_message = error_message
    diagnosis.completed_at = _utcnow()
    return diagnosis


async def get_diagnosis_by_record(
    session: AsyncSession,
    record_id: int,
    doctor_id: str,
) -> Optional[DiagnosisResult]:
    """Get diagnosis for a record, scoped by doctor_id."""
    return (await session.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.record_id == record_id,
            DiagnosisResult.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()


async def update_item_decision(
    session: AsyncSession,
    diagnosis_id: int,
    doctor_id: str,
    item_type: str,
    index: int,
    decision: str,
) -> Optional[DiagnosisResult]:
    """Update doctor_decisions JSON for a specific item.

    Reads current doctor_decisions, adds/updates the entry, writes back.
    ai_output is never touched.
    """
    diagnosis = (await session.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.id == diagnosis_id,
            DiagnosisResult.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if diagnosis is None:
        return None

    decisions: Dict[str, Any] = (
        json.loads(diagnosis.doctor_decisions) if diagnosis.doctor_decisions else {}
    )
    if item_type not in decisions:
        decisions[item_type] = {}
    decisions[item_type][str(index)] = decision
    diagnosis.doctor_decisions = json.dumps(decisions, ensure_ascii=False)
    return diagnosis


async def confirm_diagnosis(
    session: AsyncSession,
    diagnosis_id: int,
    doctor_id: str,
) -> Optional[DiagnosisResult]:
    """Set status=confirmed, compute agreement_score from doctor_decisions vs ai_output."""
    diagnosis = (await session.execute(
        select(DiagnosisResult).where(
            DiagnosisResult.id == diagnosis_id,
            DiagnosisResult.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if diagnosis is None:
        return None

    ai = json.loads(diagnosis.ai_output) if diagnosis.ai_output else {}
    decisions: Dict[str, Any] = (
        json.loads(diagnosis.doctor_decisions) if diagnosis.doctor_decisions else {}
    )
    total = (
        len(ai.get("differentials", []))
        + len(ai.get("workup", []))
        + len(ai.get("treatment", []))
    )
    rejected = sum(
        1 for cat in decisions.values() for d in cat.values() if d == "rejected"
    )
    agreement_score = (total - rejected) / total if total > 0 else 1.0

    diagnosis.status = DiagnosisStatus.confirmed
    diagnosis.agreement_score = agreement_score
    diagnosis.confirmed_at = _utcnow()
    return diagnosis
