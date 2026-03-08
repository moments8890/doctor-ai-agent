"""
医生会话内存管理：DoctorSession 数据类，支持 DB 持久化和跨节点恢复。
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from services.patient.interview import InterviewState
from db.engine import AsyncSessionLocal
from db.crud import (
    get_doctor_session_state,
    upsert_doctor_session_state,
    get_patient_for_doctor,
    get_recent_conversation_turns,
    append_conversation_turns,
)
from sqlalchemy import select
from utils.log import log


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

_sessions: dict[str, "DoctorSession"] = {}

_locks: Dict[str, asyncio.Lock] = {}
_loaded_from_db: set[str] = set()
_persist_tasks: Dict[str, asyncio.Task] = {}
_persist_turn_tasks: Dict[str, asyncio.Task] = {}
_pending_turns: Dict[str, List[dict]] = {}
_registry_lock = threading.RLock()


def get_session_lock(doctor_id: str) -> asyncio.Lock:
    """Return the per-doctor asyncio lock, creating it on first access."""
    with _registry_lock:
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
    pending_record_id: Optional[str] = None     # UUID of draft PendingRecord awaiting confirmation
    interview: Optional[InterviewState] = None  # active guided intake interview
    specialty: Optional[str] = None             # doctor's specialty, injected into agent prompt
    conversation_history: List[dict] = field(default_factory=list)  # rolling window
    last_active: float = field(default_factory=time.time)
    updated_at: datetime = field(default_factory=_utcnow)


def get_session(doctor_id: str) -> DoctorSession:
    with _registry_lock:
        if doctor_id not in _sessions:
            _sessions[doctor_id] = DoctorSession()
        return _sessions[doctor_id]


async def hydrate_session_state(doctor_id: str) -> DoctorSession:
    """Load persistent session state once per doctor into in-memory session."""
    with _registry_lock:
        already_loaded = doctor_id in _loaded_from_db
    if already_loaded:
        return get_session(doctor_id)

    async with get_session_lock(doctor_id):
        if doctor_id in _loaded_from_db:
            return get_session(doctor_id)

        sess = get_session(doctor_id)
        try:
            async with AsyncSessionLocal() as db:
                from db.models.doctor import Doctor as DoctorModel
                doctor_row = (
                    await db.execute(select(DoctorModel).where(DoctorModel.doctor_id == doctor_id).limit(1))
                ).scalar_one_or_none()
                if doctor_row is not None:
                    sess.specialty = doctor_row.specialty or None

                state = await get_doctor_session_state(db, doctor_id)
                if state is not None:
                    sess.pending_create_name = state.pending_create_name
                    sess.pending_record_id = getattr(state, "pending_record_id", None)
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
        with _registry_lock:
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
                pending_record_id=sess.pending_record_id,
            )
    except Exception as e:
        log(f"[Session] persist FAILED: {e}")


async def _flush_pending_turns(doctor_id: str) -> None:
    while True:
        with _registry_lock:
            batch = list(_pending_turns.get(doctor_id, []))
        if not batch:
            return
        with _registry_lock:
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

    with _registry_lock:
        existing = _persist_tasks.get(doctor_id)
        if existing is not None and not existing.done():
            return
        _persist_tasks[doctor_id] = loop.create_task(persist_session_state(doctor_id))


def _schedule_turn_persist(doctor_id: str, turns: List[dict]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    with _registry_lock:
        queue = _pending_turns.setdefault(doctor_id, [])
        queue.extend(turns)

        existing = _persist_turn_tasks.get(doctor_id)
        if existing is not None and not existing.done():
            return
        _persist_turn_tasks[doctor_id] = loop.create_task(_flush_pending_turns(doctor_id))


def push_turn(doctor_id: str, user_text: str, assistant_reply: str) -> None:
    """Append one user+assistant exchange to the rolling window and refresh timestamp."""
    user_turn = {"role": "user", "content": user_text}
    assistant_turn = {"role": "assistant", "content": assistant_reply}
    with _registry_lock:
        sess = get_session(doctor_id)
        sess.conversation_history.append(user_turn)
        sess.conversation_history.append(assistant_turn)
        sess.last_active = time.time()
        sess.updated_at = _utcnow()
    _schedule_turn_persist(doctor_id, [user_turn, assistant_turn])


async def flush_turns(doctor_id: str) -> None:
    """Flush any pending turns to DB immediately (call after push_turn in async context).

    This ensures turns reach the DB before control returns to the caller, preventing
    data loss on process restarts. Safe to call even if no turns are pending.
    """
    await _flush_pending_turns(doctor_id)


def set_current_patient(doctor_id: str, patient_id: int, name: str, persist: bool = True) -> None:
    with _registry_lock:
        session = get_session(doctor_id)
        session.current_patient_id = patient_id
        session.current_patient_name = name
        session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def clear_current_patient(doctor_id: str, persist: bool = True) -> None:
    with _registry_lock:
        session = get_session(doctor_id)
        session.current_patient_id = None
        session.current_patient_name = None
        session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def set_pending_create(doctor_id: str, name: str, persist: bool = True) -> None:
    with _registry_lock:
        session = get_session(doctor_id)
        session.pending_create_name = name
        session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def clear_pending_create(doctor_id: str, persist: bool = True) -> None:
    with _registry_lock:
        session = get_session(doctor_id)
        session.pending_create_name = None
        session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def set_pending_record_id(doctor_id: str, record_id: str, persist: bool = True) -> None:
    with _registry_lock:
        session = get_session(doctor_id)
        session.pending_record_id = record_id
        session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)


def clear_pending_record_id(doctor_id: str, persist: bool = True) -> None:
    with _registry_lock:
        session = get_session(doctor_id)
        session.pending_record_id = None
        session.updated_at = _utcnow()
    if persist:
        _schedule_persist(doctor_id)



def prune_inactive_sessions(max_idle_seconds: int = 3600) -> Dict[str, int]:
    """Best-effort in-memory cache eviction for idle doctor sessions.

    Keeps active/locked sessions, and clears stale task references so maps do not
    grow unbounded in long-running processes.
    """
    with _registry_lock:
        now = time.time()
        idle_threshold = max(60, int(max_idle_seconds))

        evicted = 0
        for doctor_id, session in list(_sessions.items()):
            lock = _locks.get(doctor_id)
            if lock is not None and lock.locked():
                continue
            if (now - float(session.last_active)) < idle_threshold:
                continue
            _sessions.pop(doctor_id, None)
            _loaded_from_db.discard(doctor_id)
            _pending_turns.pop(doctor_id, None)
            evicted += 1

        stale_persist = 0
        for doctor_id, task in list(_persist_tasks.items()):
            if task.done():
                _persist_tasks.pop(doctor_id, None)
                stale_persist += 1

        stale_turn_persist = 0
        for doctor_id, task in list(_persist_turn_tasks.items()):
            if task.done():
                _persist_turn_tasks.pop(doctor_id, None)
                stale_turn_persist += 1

        stale_locks = 0
        for doctor_id, lock in list(_locks.items()):
            if doctor_id in _sessions:
                continue
            if lock.locked():
                continue
            _locks.pop(doctor_id, None)
            stale_locks += 1

    return {
        "evicted_sessions": evicted,
        "cleared_persist_tasks": stale_persist,
        "cleared_turn_persist_tasks": stale_turn_persist,
        "cleared_locks": stale_locks,
    }


def reset_session_state_for_tests() -> None:
    """Test helper to clear all in-memory session registries safely."""
    with _registry_lock:
        for task in list(_persist_tasks.values()):
            task.cancel()
        for task in list(_persist_turn_tasks.values()):
            task.cancel()
        _sessions.clear()
        _locks.clear()
        _loaded_from_db.clear()
        _persist_tasks.clear()
        _persist_turn_tasks.clear()
        _pending_turns.clear()
