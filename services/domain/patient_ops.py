"""共享患者解析：find-or-create 及人口统计信息修正，渠道特定逻辑由调用方处理。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.patient import create_patient, find_patient_by_name
from db.models.patient import Patient
from utils.log import log


async def resolve_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_name: str,
    gender: Optional[str] = None,
    age: Optional[int] = None,
) -> tuple[Patient, bool]:
    """Find an existing patient by name, or create a new one.

    If the patient already exists, demographic corrections are applied in-place
    (gender and year_of_birth) when the new values differ from stored ones.

    Args:
        session: Active async DB session.
        doctor_id: Owning doctor.
        patient_name: Display name to look up or create.
        gender: Optional gender ("男" | "女") from current turn.
        age: Optional age integer from current turn.

    Returns:
        (patient, was_created): The Patient row and whether it was newly created.

    Raises:
        InvalidMedicalRecordError: If the name fails validation during creation.
    """
    patient = await find_patient_by_name(session, doctor_id, patient_name)

    if patient is None:
        patient = await create_patient(session, doctor_id, patient_name, gender, age)
        log(f"[domain] auto-created patient [{patient.name}] id={patient.id} doctor={doctor_id}")
        return patient, True

    # Apply demographic corrections when the current turn provides updated info.
    updated = False
    if gender in ("男", "女") and gender != patient.gender:
        patient.gender = gender
        updated = True
    if age is not None:
        from db.repositories.patients import _year_of_birth
        new_yob = _year_of_birth(age)
        if new_yob and new_yob != patient.year_of_birth:
            patient.year_of_birth = new_yob
            updated = True
    if updated:
        await session.commit()
        log(f"[domain] updated demographics [{patient.name}] id={patient.id} doctor={doctor_id}")

    return patient, False
