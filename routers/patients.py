from fastapi import APIRouter
from db.engine import AsyncSessionLocal
from db.models import Patient, MedicalRecordDB
from db.crud import get_records_for_patient
from sqlalchemy import select

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.post("")
async def create_patient_api(doctor_id: str, name: str, gender: str | None = None, age: int | None = None):
    from db.crud import create_patient
    async with AsyncSessionLocal() as session:
        patient = await create_patient(session, doctor_id, name, gender, age)
        return {"id": patient.id, "name": patient.name, "gender": patient.gender, "age": patient.age}


@router.get("/{doctor_id}")
async def list_patients(doctor_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Patient).where(Patient.doctor_id == doctor_id).order_by(Patient.created_at.desc())
        )
        patients = result.scalars().all()
        return [
            {"id": p.id, "name": p.name, "gender": p.gender, "age": p.age, "created_at": p.created_at}
            for p in patients
        ]


@router.get("/{doctor_id}/{patient_id}/records")
async def list_patient_records(doctor_id: str, patient_id: int):
    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(session, doctor_id, patient_id)
        return [
            {
                "id": r.id,
                "chief_complaint": r.chief_complaint,
                "diagnosis": r.diagnosis,
                "treatment_plan": r.treatment_plan,
                "created_at": r.created_at,
            }
            for r in records
        ]
