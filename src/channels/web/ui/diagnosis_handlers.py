"""Diagnosis review endpoints: trigger, fetch suggestions, decide, add custom, finalize.

Provides the API surface for the doctor review workflow where AI-generated
diagnostic suggestions are reviewed, accepted/rejected, or supplemented
with custom entries before the record is finalized.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from channels.web.ui._utils import _resolve_ui_doctor_id
from db.crud.suggestions import (
    create_suggestion,
    get_suggestion_by_id,
    get_suggestions_for_record,
    update_decision,
)
from db.engine import AsyncSessionLocal
from db.models.ai_suggestion import AISuggestion, SuggestionDecision, SuggestionSection
from db.models.records import MedicalRecordDB, RecordStatus
from utils.log import log, safe_create_task

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Request / Response Models ─────────────────────────────────────────────


class DiagnoseRequest(BaseModel):
    doctor_id: str


class DecideRequest(BaseModel):
    decision: str  # "confirmed" | "rejected" | "edited"
    reason: Optional[str] = None
    edited_text: Optional[str] = None


class AddSuggestionRequest(BaseModel):
    doctor_id: str
    section: str  # "differential" | "workup" | "treatment"
    content: str
    detail: Optional[str] = None


class FinalizeRequest(BaseModel):
    doctor_id: str


# ── Helpers ───────────────────────────────────────────────────────────────


def _suggestion_to_dict(s: AISuggestion) -> dict:
    return {
        "id": s.id,
        "record_id": s.record_id,
        "section": s.section,
        "content": s.content,
        "detail": s.detail,
        "confidence": s.confidence,
        "urgency": s.urgency,
        "intervention": s.intervention,
        "decision": s.decision,
        "edited_text": s.edited_text,
        "reason": s.reason,
        "is_custom": s.is_custom,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "decided_at": s.decided_at.isoformat() if s.decided_at else None,
    }


async def _get_record_or_404(
    record_id: int,
    doctor_id: str,
) -> MedicalRecordDB:
    """Load a record scoped to the doctor, or raise 404."""
    async with AsyncSessionLocal() as db:
        rec = (
            await db.execute(
                select(MedicalRecordDB)
                .where(
                    MedicalRecordDB.id == record_id,
                    MedicalRecordDB.doctor_id == doctor_id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec


# ── 1. POST /records/{record_id}/diagnose — trigger diagnosis ────────────


@router.post("/api/doctor/records/{record_id}/diagnose", status_code=202, include_in_schema=True)
async def trigger_diagnosis(
    record_id: int,
    body: DiagnoseRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Trigger AI diagnosis in the background; returns 202 immediately."""
    resolved = _resolve_ui_doctor_id(body.doctor_id, authorization)
    await _get_record_or_404(record_id, resolved)

    # Update record status to pending_review
    async with AsyncSessionLocal() as db:
        rec = (
            await db.execute(
                select(MedicalRecordDB)
                .where(MedicalRecordDB.id == record_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if rec is not None:
            rec.status = RecordStatus.pending_review.value
            await db.commit()

    # Fire-and-forget background diagnosis
    from domain.diagnosis import run_diagnosis

    safe_create_task(
        run_diagnosis(doctor_id=resolved, record_id=record_id),
        name=f"diagnosis-{record_id}",
    )

    return {"status": "running", "record_id": record_id}


# ── 2. GET /records/{record_id}/suggestions — fetch suggestions ──────────


@router.get("/api/doctor/records/{record_id}/suggestions", include_in_schema=True)
async def get_suggestions(
    record_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Return all AI suggestions for a given record."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    await _get_record_or_404(record_id, resolved)

    async with AsyncSessionLocal() as db:
        rows = await get_suggestions_for_record(db, record_id)
        suggestions = [_suggestion_to_dict(r) for r in rows]

    return {"status": "pending_review", "suggestions": suggestions}


# ── 3. POST /suggestions/{suggestion_id}/decide — update decision ────────


@router.post("/api/doctor/suggestions/{suggestion_id}/decide", include_in_schema=True)
async def decide_suggestion(
    suggestion_id: int,
    body: DecideRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Accept, reject, or edit an individual AI suggestion."""
    # Validate decision value
    try:
        decision_enum = SuggestionDecision(body.decision)
    except ValueError:
        allowed = [d.value for d in SuggestionDecision if d != SuggestionDecision.custom]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision: '{body.decision}'. Allowed: {allowed}",
        )

    if decision_enum == SuggestionDecision.custom:
        raise HTTPException(
            status_code=422,
            detail="Use the add-custom endpoint to create custom suggestions",
        )

    if decision_enum == SuggestionDecision.edited and not body.edited_text:
        raise HTTPException(
            status_code=422,
            detail="edited_text is required when decision is 'edited'",
        )

    async with AsyncSessionLocal() as db:
        row = await get_suggestion_by_id(db, suggestion_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Suggestion not found")

        updated = await update_decision(
            db,
            suggestion_id,
            decision=decision_enum,
            edited_text=body.edited_text,
            reason=body.reason,
        )

    if updated is None:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    return {"status": "ok", "id": updated.id, "decision": updated.decision}


# ── 4. POST /records/{record_id}/suggestions — add custom suggestion ─────


@router.post("/api/doctor/records/{record_id}/suggestions", include_in_schema=True)
async def add_custom_suggestion(
    record_id: int,
    body: AddSuggestionRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Add a doctor-authored custom suggestion to the record."""
    resolved = _resolve_ui_doctor_id(body.doctor_id, authorization)
    await _get_record_or_404(record_id, resolved)

    # Validate section
    try:
        section_enum = SuggestionSection(body.section)
    except ValueError:
        allowed = [s.value for s in SuggestionSection]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid section: '{body.section}'. Allowed: {allowed}",
        )

    async with AsyncSessionLocal() as db:
        row = await create_suggestion(
            db,
            record_id=record_id,
            doctor_id=resolved,
            section=section_enum,
            content=body.content,
            detail=body.detail,
            is_custom=True,
        )

    return {"status": "ok", "id": row.id}


# ── 5. POST /records/{record_id}/review/finalize — finalize record ───────


@router.post("/api/doctor/records/{record_id}/review/finalize", include_in_schema=True)
async def finalize_review(
    record_id: int,
    body: FinalizeRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Mark the record as completed after the doctor finishes review.

    Writes confirmed/edited/custom suggestions back to the medical record
    fields (diagnosis, treatment_plan, orders_followup) so they appear in
    the patient-facing record view.
    """
    resolved = _resolve_ui_doctor_id(body.doctor_id, authorization)
    await _get_record_or_404(record_id, resolved)

    async with AsyncSessionLocal() as db:
        rec = (
            await db.execute(
                select(MedicalRecordDB)
                .where(
                    MedicalRecordDB.id == record_id,
                    MedicalRecordDB.doctor_id == resolved,
                )
                .limit(1)
            )
        ).scalar_one_or_none()

        if rec is None:
            raise HTTPException(status_code=404, detail="Record not found")

        # Collect confirmed/edited/custom suggestions to write back
        rows = await get_suggestions_for_record(db, record_id)

        accepted = [
            r for r in rows
            if r.decision in (
                SuggestionDecision.confirmed.value,
                SuggestionDecision.edited.value,
                SuggestionDecision.custom.value,
            )
        ]

        # Build diagnosis text from confirmed differentials
        diag_items = [r for r in accepted if r.section == SuggestionSection.differential.value]
        if diag_items:
            diag_lines = []
            for i, r in enumerate(diag_items, 1):
                label = r.edited_text if r.decision == SuggestionDecision.edited.value else r.content
                detail = r.detail or ""
                conf = f"（{r.confidence}）" if r.confidence else ""
                diag_lines.append(f"{i}. {label}{conf}\n{detail}" if detail else f"{i}. {label}{conf}")
            rec.diagnosis = "\n".join(diag_lines)

        # Build treatment plan from confirmed treatments
        tx_items = [r for r in accepted if r.section == SuggestionSection.treatment.value]
        if tx_items:
            tx_lines = []
            for i, r in enumerate(tx_items, 1):
                label = r.edited_text if r.decision == SuggestionDecision.edited.value else r.content
                detail = r.detail or ""
                interv = f"[{r.intervention}]" if r.intervention else ""
                tx_lines.append(f"{i}. {label} {interv}\n{detail}" if detail else f"{i}. {label} {interv}")
            rec.treatment_plan = "\n".join(tx_lines)

        # Build orders/followup from confirmed workup
        wu_items = [r for r in accepted if r.section == SuggestionSection.workup.value]
        if wu_items:
            wu_lines = []
            for i, r in enumerate(wu_items, 1):
                label = r.edited_text if r.decision == SuggestionDecision.edited.value else r.content
                detail = r.detail or ""
                urg = f"[{r.urgency}]" if r.urgency else ""
                wu_lines.append(f"{i}. {label} {urg}\n{detail}" if detail else f"{i}. {label} {urg}")
            rec.orders_followup = "\n".join(wu_lines)

        rec.status = RecordStatus.completed.value
        n_accepted = len(accepted)
        await db.commit()

    log(f"[diagnosis] record {record_id} finalized by {resolved} — wrote {n_accepted} accepted items to record")
    return {"status": "completed", "record_id": record_id}
