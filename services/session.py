from __future__ import annotations
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from services.interview import InterviewState

_sessions: dict[str, "DoctorSession"] = {}

# Rolling window: compress + flush when this many turns accumulate
MAX_TURNS = 10


@dataclass
class DoctorSession:
    current_patient_id: Optional[int] = None
    current_patient_name: Optional[str] = None
    pending_create_name: Optional[str] = None   # waiting for gender/age to create a new patient
    interview: Optional[InterviewState] = None  # active guided intake interview
    conversation_history: List[dict] = field(default_factory=list)  # rolling window
    last_active: float = field(default_factory=time.time)
    updated_at: datetime = field(default_factory=datetime.utcnow)


def get_session(doctor_id: str) -> DoctorSession:
    if doctor_id not in _sessions:
        _sessions[doctor_id] = DoctorSession()
    return _sessions[doctor_id]


def push_turn(doctor_id: str, user_text: str, assistant_reply: str) -> None:
    """Append one user+assistant exchange to the rolling window and refresh timestamp."""
    sess = get_session(doctor_id)
    sess.conversation_history.append({"role": "user", "content": user_text})
    sess.conversation_history.append({"role": "assistant", "content": assistant_reply})
    sess.last_active = time.time()
    sess.updated_at = datetime.utcnow()


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
