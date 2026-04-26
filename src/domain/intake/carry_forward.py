"""Carry-forward bootstrap for patient intake.

When an intake_session is created for a patient who has prior confirmed
medical_records, we pre-populate `collected` with the 5 stable history fields
(past_history, allergy_history, family_history, personal_history,
marital_reproductive). Visit-fresh fields (chief_complaint, present_illness)
NEVER carry forward.

Provenance is tracked in `_carry_forward_meta`, an underscore-prefixed key
stored in `intake_sessions.collected` (engine convention for non-clinical
metadata). Each entry has the form:

    {
        "source_record_id": int,
        "source_date": ISO-8601 string,
        "confirmed_by_patient": False,
    }

`confirmed_by_patient` flips to True via IntakeEngine.update_field (the
patient corrects a value) or IntakeEngine.bulk_confirm_carry_forward (the
"全部仍然准确" chip).

On confirm, the engine writes carry_forward_meta and fields_updated_this_visit
onto the new medical_records row so the doctor can see provenance at review.
"""
from __future__ import annotations

from typing import Tuple

from sqlalchemy import select


# Stable history fields that carry forward across visits. Visit-fresh fields
# (chief_complaint, present_illness) are deliberately excluded — those are
# always "what brings you in today" and must come from this visit.
CARRY_FORWARD_FIELDS: tuple[str, ...] = (
    "past_history",
    "allergy_history",
    "family_history",
    "personal_history",
    "marital_reproductive",
)


async def bootstrap_carry_forward(
    patient_id: int | None,
    doctor_id: str,
) -> Tuple[dict, dict]:
    """Look up the patient's most recent record and extract stable fields.

    Returns ``(collected_seed, carry_forward_meta)``:

    - ``collected_seed`` — a dict of ``{field: value}`` for any
      CARRY_FORWARD_FIELDS that have a non-empty value on the latest record.
    - ``carry_forward_meta`` — a dict of
      ``{field: {source_record_id, source_date, confirmed_by_patient}}``
      with one entry per seeded field. ``confirmed_by_patient`` is False
      so the engine knows the LLM may not overwrite these silently.

    Returns ``({}, {})`` if patient_id is None or no qualifying prior record
    exists.
    """
    if patient_id is None:
        return {}, {}

    # Lazy imports to avoid circular dependencies at module load time.
    from db.engine import AsyncSessionLocal
    from db.models.records import MedicalRecordDB, RecordStatus

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == doctor_id,
                MedicalRecordDB.status.in_([
                    RecordStatus.pending_review.value,
                    RecordStatus.completed.value,
                ]),
            ).order_by(MedicalRecordDB.created_at.desc()).limit(1)
        )).scalar_one_or_none()

    if row is None:
        return {}, {}

    source_date = (
        row.created_at.isoformat() if row.created_at is not None else ""
    )

    collected_seed: dict = {}
    carry_forward_meta: dict = {}
    for field_name in CARRY_FORWARD_FIELDS:
        value = getattr(row, field_name, None)
        if not value:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        collected_seed[field_name] = value
        carry_forward_meta[field_name] = {
            "source_record_id": row.id,
            "source_date": source_date,
            "confirmed_by_patient": False,
        }

    return collected_seed, carry_forward_meta
