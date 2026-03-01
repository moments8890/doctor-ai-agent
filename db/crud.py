from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Patient, MedicalRecordDB
from models.medical_record import MedicalRecord


async def create_patient(
    session: AsyncSession,
    doctor_id: str,
    name: str,
    gender: str | None,
    age: int | None,
) -> Patient:
    patient = Patient(doctor_id=doctor_id, name=name, gender=gender, age=age)
    session.add(patient)
    await session.commit()
    return patient


async def find_patient_by_name(
    session: AsyncSession,
    doctor_id: str,
    name: str,
) -> Patient | None:
    result = await session.execute(
        select(Patient).where(Patient.doctor_id == doctor_id, Patient.name == name).limit(1)
    )
    return result.scalar_one_or_none()


async def save_record(
    session: AsyncSession,
    doctor_id: str,
    record: MedicalRecord,
    patient_id: int | None,
) -> MedicalRecordDB:
    db_record = MedicalRecordDB(
        doctor_id=doctor_id,
        patient_id=patient_id,
        chief_complaint=record.chief_complaint,
        history_of_present_illness=record.history_of_present_illness,
        past_medical_history=record.past_medical_history,
        physical_examination=record.physical_examination,
        auxiliary_examinations=record.auxiliary_examinations,
        diagnosis=record.diagnosis,
        treatment_plan=record.treatment_plan,
        follow_up_plan=record.follow_up_plan,
    )
    session.add(db_record)
    await session.commit()
    return db_record


async def get_records_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    limit: int = 5,
) -> list[MedicalRecordDB]:
    result = await session.execute(
        select(MedicalRecordDB)
        .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id == patient_id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_all_patients(
    session: AsyncSession,
    doctor_id: str,
) -> list[Patient]:
    result = await session.execute(
        select(Patient)
        .where(Patient.doctor_id == doctor_id)
        .order_by(Patient.created_at.desc())
    )
    return list(result.scalars().all())


async def get_all_records_for_doctor(
    session: AsyncSession,
    doctor_id: str,
    limit: int = 10,
) -> list[MedicalRecordDB]:
    result = await session.execute(
        select(MedicalRecordDB)
        .options(joinedload(MedicalRecordDB.patient))
        .where(MedicalRecordDB.doctor_id == doctor_id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())
