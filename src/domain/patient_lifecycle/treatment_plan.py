"""Derive a patient-visible treatment plan from a confirmed diagnosis.

This is a **read view** over `diagnosis_results` — no new table.  When a doctor
confirms a diagnosis (via the review workflow), the approved workup/treatment
items become the patient-visible treatment plan.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.diagnosis_result import DiagnosisResult
from db.models.doctor import Doctor
from db.models.records import MedicalRecordDB
from utils.log import log


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approved_indices(decisions: Dict[str, Any], category: str) -> set:
    """Return the set of integer indices the doctor confirmed for *category*."""
    cat = decisions.get(category, {})
    if not isinstance(cat, dict):
        return set()
    return {
        int(idx)
        for idx, decision in cat.items()
        if decision == "confirmed"
    }


def _filter_approved(items: List[Dict[str, Any]], approved: set) -> List[Dict[str, Any]]:
    """Return only items whose position index is in *approved*."""
    return [item for i, item in enumerate(items) if i in approved]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def derive_treatment_plan(
    patient_id: int,
    db_session: AsyncSession,
) -> Optional[Dict[str, Any]]:
    """Build a treatment-plan dict from the latest confirmed diagnosis.

    Returns ``None`` if no confirmed diagnosis exists for *patient_id*.
    """
    # Find the most recent confirmed diagnosis for this patient by joining
    # through medical_records to resolve patient_id.
    stmt = (
        select(DiagnosisResult, MedicalRecordDB.patient_id)
        .join(MedicalRecordDB, DiagnosisResult.record_id == MedicalRecordDB.id)
        .where(
            MedicalRecordDB.patient_id == patient_id,
            DiagnosisResult.status == "confirmed",
        )
        .order_by(DiagnosisResult.confirmed_at.desc())
        .limit(1)
    )
    row = (await db_session.execute(stmt)).first()
    if row is None:
        return None

    diag: DiagnosisResult = row[0]

    # Parse stored JSON columns ------------------------------------------------
    try:
        ai_output: Dict[str, Any] = json.loads(diag.ai_output) if diag.ai_output else {}
    except (json.JSONDecodeError, TypeError):
        log(f"[treatment_plan] bad ai_output JSON on diagnosis id={diag.id}", level="warning")
        ai_output = {}

    try:
        decisions: Dict[str, Any] = json.loads(diag.doctor_decisions) if diag.doctor_decisions else {}
    except (json.JSONDecodeError, TypeError):
        log(f"[treatment_plan] bad doctor_decisions JSON on diagnosis id={diag.id}", level="warning")
        decisions = {}

    try:
        red_flags: List[str] = json.loads(diag.red_flags) if diag.red_flags else []
    except (json.JSONDecodeError, TypeError):
        red_flags = []

    # Filter to doctor-approved items only ------------------------------------
    approved_diff = _approved_indices(decisions, "differentials")
    approved_workup = _approved_indices(decisions, "workup")
    approved_treatment = _approved_indices(decisions, "treatment")

    differentials = _filter_approved(ai_output.get("differentials", []), approved_diff)
    workup_items = _filter_approved(ai_output.get("workup", []), approved_workup)
    treatment_items = _filter_approved(ai_output.get("treatment", []), approved_treatment)

    # Resolve primary diagnosis name (first confirmed differential) -----------
    diagnosis_name = differentials[0]["condition"] if differentials else ""

    # Resolve doctor name -----------------------------------------------------
    doctor_row = (await db_session.execute(
        select(Doctor.name).where(Doctor.doctor_id == diag.doctor_id)
    )).scalar_one_or_none()
    doctor_name = doctor_row or diag.doctor_id

    return {
        "diagnosis_id": diag.id,
        "diagnosis_name": diagnosis_name,
        "confirmed_at": diag.confirmed_at.isoformat() if diag.confirmed_at else None,
        "doctor_name": doctor_name,
        "workup_items": workup_items,
        "treatment_items": treatment_items,
        "red_flags": red_flags,
        "differentials": differentials,
    }
