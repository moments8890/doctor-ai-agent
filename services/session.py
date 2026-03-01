from dataclasses import dataclass, field
from datetime import datetime

_sessions: dict[str, "DoctorSession"] = {}


@dataclass
class DoctorSession:
    current_patient_id: int | None = None
    current_patient_name: str | None = None
    pending_create_name: str | None = None   # waiting for gender/age to create a new patient
    updated_at: datetime = field(default_factory=datetime.utcnow)


def get_session(doctor_id: str) -> DoctorSession:
    if doctor_id not in _sessions:
        _sessions[doctor_id] = DoctorSession()
    return _sessions[doctor_id]


def set_current_patient(doctor_id: str, patient_id: int, name: str) -> None:
    session = get_session(doctor_id)
    session.current_patient_id = patient_id
    session.current_patient_name = name
    session.updated_at = datetime.utcnow()


def clear_current_patient(doctor_id: str) -> None:
    session = get_session(doctor_id)
    session.current_patient_id = None
    session.current_patient_name = None
    session.updated_at = datetime.utcnow()


def set_pending_create(doctor_id: str, name: str) -> None:
    session = get_session(doctor_id)
    session.pending_create_name = name
    session.updated_at = datetime.utcnow()


def clear_pending_create(doctor_id: str) -> None:
    session = get_session(doctor_id)
    session.pending_create_name = None
    session.updated_at = datetime.utcnow()
