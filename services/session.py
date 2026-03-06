from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from services.interview import InterviewState
from db.engine import AsyncSessionLocal
from db.crud import (
    get_doctor_session_state,
    upsert_doctor_session_state,
    get_patient_for_doctor,
    get_recent_conversation_turns,
    append_conversation_turns,
)
from utils.log import log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

_sessions: dict[str, "DoctorSession"] = {}

_locks: Dict[str, asyncio.Lock] = {}
_loaded_from_db: set[str] = set()
_persist_tasks: Dict[str, asyncio.Task] = {}
_persist_turn_tasks: Dict[str, asyncio.Task] = {}
_pending_turns: Dict[str, List[dict]] = {}


def get_session_lock(doctor_id: str) -> asyncio.Lock:
    """Return the per-doctor asyncio lock, creating it on first access."""
    if doctor_id not in _locks:
        _locks[doctor_id] = asyncio.Lock()
    return _locks[doctor_id]

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
    updated_at: datetime = field(default_factory=_utcnow)


def get_session(doctor_id: str) -> DoctorSession:
    if doctor_id not in _sessions:
        _sessions[doctor_id] = DoctorSession()
    return _sessions[doctor_id]


async def hydrate_session_state(doctor_id: str) -> DoctorSession:
    """Load persistent session state once per doctor into in-memory session."""
    if doctor_id in _loaded_from_db:
        return get_session(doctor_id)

    async with get_session_lock(doctor_id):
        if doctor_id in _loaded_from_db:
            return get_session(doctor_id)

        sess = get_session(doctor_id)
        try:
            async with AsyncSessionLocal() as db:
                state = await get_doctor_session_state(db, doctor_id)
                if state is not None:
                    sess.pending_create_name = state.pending_create_name
                    sess.current_patient_id = state.current_patient_id
                    if state.current_patient_id is not None:
                        patient = await get_patient_for_doctor(db, doctor_id, state.current_patient_id)
                        sess.current_patient_name = patient.name if patient is not None else None
                    else:
                        sess.current_patient_name = None

                # Recover recent conversation turns so another instance can continue context.
                turns = await get_recent_conversation_turns(db, doctor_id, limit=MAX_TURNS * 2)
                if turns:
                    sess.conversation_history = [
                        {"role": turn.role, "content": turn.content}
                        for turn in turns
                    ]
        except Exception as e:
            log(f"[Session] hydrate FAILED: {e}")
        _loaded_from_db.add(doctor_id)
        return sess


async def persist_session_state(doctor_id: str) -> None:
    """Persist minimal session context so deployment restarts can restore it."""
    sess = get_session(doctor_id)
    try:
        async with AsyncSessionLocal() as db:
            await upsert_doctor_session_state(
                db,
                doctor_id=doctor_id,
                current_patient_id=sess.current_patient_id,
                pending_create_name=sess.pending_create_name,
            )
    except Exception as e:
        log(f"[Session] persist FAILED: {e}")


async def _flush_pending_turns(doctor_id: str) -> None:
    while True:
        batch = _pending_turns.get(doctor_id, [])
        if not batch:
            return
        _pending_turns[doctor_id] = []
        try:
            async with AsyncSessionLocal() as db:
                await append_conversation_turns(db, doctor_id, batch, max_turns=MAX_TURNS)
        except Exception as e:
            log(f"[Session] persist turns FAILED: {e}")
            return


def _schedule_persist(doctor_id: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Called in sync contexts (e.g. unit tests), skip async persistence.
        return

    existing = _persist_tasks.get(doctor_id)
    if existing is not None and not existing.done():
        return
    _persist_tasks[doctor_id] = loop.create_task(persist_session_state(doctor_id))


def _schedule_turn_persist(doctor_id: str, turns: List[dict]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    queue = _pending_turns.setdefault(doctor_id, [])
    queue.extend(turns)

    existing = _persist_turn_tasks.get(doctor_id)
    if existing is not None and not existing.done():
        return
    _persist_turn_tasks[doctor_id] = loop.create_task(_flush_pending_turns(doctor_id))


def push_turn(doctor_id: str, user_text: str, assistant_reply: str) -> None:
    """Append one user+assistant exchange to the rolling window and refresh timestamp."""
    sess = get_session(doctor_id)
    user_turn = {"role": "user", "content": user_text}
    assistant_turn = {"role": "assistant", "content": assistant_reply}
    sess.conversation_history.append(user_turn)
    sess.conversation_history.append(assistant_turn)
    sess.last_active = time.time()
    sess.updated_at = _utcnow()
    _schedule_turn_persist(doctor_id, [user_turn, assistant_turn])


def set_current_patient(doctor_id: str, patient_id: int, name: str, persist: bool = True) -> None:
    session = get_session(doctor_id)
    session.current_patient_id = patient_id
    session.current_patient_name = name
    session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def clear_current_patient(doctor_id: str, persist: bool = True) -> None:
    session = get_session(doctor_id)
    session.current_patient_id = None
    session.current_patient_name = None
    session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def set_pending_create(doctor_id: str, name: str, persist: bool = True) -> None:
    session = get_session(doctor_id)
    session.pending_create_name = name
    session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def clear_pending_create(doctor_id: str, persist: bool = True) -> None:
    session = get_session(doctor_id)
    session.pending_create_name = None
    session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)
