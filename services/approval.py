from __future__ import annotations

import json
from typing import Optional

from db.crud import (
    create_patient as db_create_patient,
    find_patient_by_name,
    get_approval_item,
    save_record,
    update_approval_item,
)
from db.engine import AsyncSessionLocal
from db.models import ApprovalItem
from models.medical_record import MedicalRecord
from utils.log import log


async def commit_approval(
    approval_id: int,
    doctor_id: str,
    edited_data: Optional[dict] = None,
    reviewer_note: Optional[str] = None,
) -> ApprovalItem:
    """Approve a pending ApprovalItem: resolve patient, save record, cascade.

    Raises ValueError if the item is not found or is not pending.
    """
    async with AsyncSessionLocal() as db:
        item = await get_approval_item(db, approval_id, doctor_id)
        if item is None:
            raise ValueError(f"ApprovalItem {approval_id} not found for doctor {doctor_id}")
        if item.status != "pending":
            raise ValueError(
                f"ApprovalItem {approval_id} cannot be approved: status is '{item.status}'"
            )

        payload = edited_data if edited_data is not None else json.loads(item.suggested_data)

        record_fields = payload.get("record", {})
        record = MedicalRecord(**{k: record_fields.get(k) for k in MedicalRecord.model_fields})

        patient_name: Optional[str] = payload.get("patient_name")
        gender: Optional[str] = payload.get("gender")
        age: Optional[int] = payload.get("age")
        existing_patient_id: Optional[int] = payload.get("existing_patient_id")

        patient_id: Optional[int] = existing_patient_id
        if patient_id is None and patient_name:
            existing = await find_patient_by_name(db, doctor_id, patient_name)
            if existing:
                patient_id = existing.id
            else:
                new_patient = await db_create_patient(
                    db, doctor_id, patient_name, gender, age
                )
                patient_id = new_patient.id

        db_record = await save_record(db, doctor_id, record, patient_id)

        updated = await update_approval_item(
            db,
            approval_id,
            doctor_id,
            status="approved",
            patient_id=patient_id,
            record_id=db_record.id,
            reviewer_note=reviewer_note,
        )

    log(
        f"[Approval] approved #{approval_id} patient={patient_name} "
        f"record_id={db_record.id} doctor={doctor_id}"
    )
    return updated  # type: ignore[return-value]


async def reject_approval(
    approval_id: int,
    doctor_id: str,
    reviewer_note: Optional[str] = None,
) -> ApprovalItem:
    """Reject a pending ApprovalItem. No DB write occurs.

    Raises ValueError if the item is not found or is not pending.
    """
    async with AsyncSessionLocal() as db:
        item = await get_approval_item(db, approval_id, doctor_id)
        if item is None:
            raise ValueError(f"ApprovalItem {approval_id} not found for doctor {doctor_id}")
        if item.status != "pending":
            raise ValueError(
                f"ApprovalItem {approval_id} cannot be rejected: status is '{item.status}'"
            )

        updated = await update_approval_item(
            db,
            approval_id,
            doctor_id,
            status="rejected",
            reviewer_note=reviewer_note,
        )

    log(f"[Approval] rejected #{approval_id} doctor={doctor_id}")
    return updated  # type: ignore[return-value]
