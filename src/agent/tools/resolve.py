from __future__ import annotations

from typing import Any, Dict, Optional


async def _find_patient(doctor_id: str, patient_name: str) -> Optional[Any]:
    """Look up patient by name for a given doctor. Returns Patient or None."""
    from db.crud.patient import find_patient_by_name
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await find_patient_by_name(session, doctor_id, patient_name)


async def _create_patient(
    doctor_id: str, patient_name: str,
    gender: Optional[str] = None, age: Optional[int] = None,
) -> Any:
    """Auto-create a patient and return the Patient row."""
    from db.crud.patient import create_patient
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        patient, _access_code = await create_patient(
            session, doctor_id, patient_name, gender=gender, age=age,
        )
        return patient


async def resolve(
    patient_name: Optional[str],
    doctor_id: str,
    *,
    auto_create: bool = False,
    gender: Optional[str] = None,
    age: Optional[int] = None,
) -> Dict[str, Any]:
    """Resolve patient_name to a validated binding.

    Names are the LLM-facing interface; IDs are used internally for CRUD.
    Returns {"doctor_id", "patient_id", "patient_name"} on success,
    or {"status", "message"} on failure.

    When auto_create=True, creates the patient if not found (used by
    create_record and update_record so doctors don't have to manually
    create patients before writing records).
    """
    if not patient_name:
        return {"status": "missing", "message": "请指定患者姓名"}

    patient = await _find_patient(doctor_id, patient_name)

    if patient is None and auto_create:
        patient = await _create_patient(
            doctor_id, patient_name, gender=gender, age=age,
        )

    if patient is None:
        return {"status": "not_found", "message": f"未找到患者{patient_name}"}

    return {
        "doctor_id": doctor_id,
        "patient_id": patient.id,
        "patient_name": patient.name,
    }
