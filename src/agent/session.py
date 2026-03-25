"""Session management — DB-backed with in-memory cache.

Conversation history is durably stored in ``doctor_chat_log``.  An in-memory
cache avoids a DB round-trip on every turn for the hot path.

On cache miss (e.g. after server restart) history is restored from DB.

Performance note: writes are currently synchronous (awaited INSERT).
This could be made async (fire-and-forget) or batched if DB write latency
becomes a bottleneck — the in-memory cache already serves reads.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from db.engine import AsyncSessionLocal
from db.models.doctor_chat_log import DoctorChatLog
from sqlalchemy import select

MAX_HISTORY_TURNS = 50  # keep last 50 turns (100 messages)

# ---------------------------------------------------------------------------
# Session ID management — one session per doctor until explicitly cleared
# or timed-out (timeout logic to be added later).
# ---------------------------------------------------------------------------
_session_ids: Dict[str, str] = {}  # identity → session_id


def _get_or_create_session_id(identity: str) -> str:
    if identity not in _session_ids:
        _session_ids[identity] = uuid.uuid4().hex
    return _session_ids[identity]


def get_session_id(identity: str) -> Optional[str]:
    """Return the current session_id for the identity, or None."""
    return _session_ids.get(identity)


# ---------------------------------------------------------------------------
# In-memory cache — warm cache over doctor_chat_log
# ---------------------------------------------------------------------------
_cache: Dict[str, List[Dict[str, str]]] = {}


async def get_session_history(identity: str) -> List[Dict[str, str]]:
    """Return chat history for the given identity.

    Reads from in-memory cache first.  On cache miss, restores from
    ``doctor_chat_log`` (last session for this doctor).
    """
    if identity in _cache:
        return list(_cache[identity])

    # Cache miss — restore from DB
    history = await _load_from_db(identity)
    _cache[identity] = history
    return list(history)


async def append_to_history(
    identity: str,
    user_text: str,
    assistant_reply: str,
    *,
    patient_id: Optional[int] = None,
) -> None:
    """Append a turn (user + assistant) to both cache and DB.

    Writes are synchronous (awaited) for durability.  If write latency
    becomes a concern, this can be changed to fire-and-forget via
    ``asyncio.create_task()`` or batched with a periodic flush — the
    in-memory cache already serves reads so the caller would not block.
    """
    session_id = _get_or_create_session_id(identity)

    # Update in-memory cache
    if identity not in _cache:
        _cache[identity] = []
    cache = _cache[identity]
    cache.append({"role": "user", "content": user_text})
    cache.append({"role": "assistant", "content": assistant_reply})
    max_messages = MAX_HISTORY_TURNS * 2
    if len(cache) > max_messages:
        _cache[identity] = cache[-max_messages:]

    # Persist to doctor_chat_log (sync for now — see docstring)
    await _write_to_db(identity, session_id, user_text, assistant_reply, patient_id)


def clear_session(identity: str) -> None:
    """Clear session history (new conversation).

    Drops the in-memory cache and session_id.  DB rows are retained
    as permanent history.
    """
    _cache.pop(identity, None)
    _session_ids.pop(identity, None)


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------

async def _load_from_db(identity: str, limit: int = MAX_HISTORY_TURNS * 2) -> List[Dict[str, str]]:
    """Load the most recent session's messages from doctor_chat_log.

    Finds the latest session_id for this doctor, then loads messages
    from that session only.  This ensures "clear conversation" (which
    creates a new session_id) does not reload old context after restart.
    """
    async with AsyncSessionLocal() as db:
        # Find the latest session_id for this doctor
        latest_session = (
            await db.execute(
                select(DoctorChatLog.session_id)
                .where(DoctorChatLog.doctor_id == identity)
                .order_by(DoctorChatLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if not latest_session:
            return []

        # Restore that session_id so new messages continue in the same session
        _session_ids[identity] = latest_session

        # Load messages from that session
        rows = (
            await db.execute(
                select(DoctorChatLog)
                .where(
                    DoctorChatLog.doctor_id == identity,
                    DoctorChatLog.session_id == latest_session,
                )
                .order_by(DoctorChatLog.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


async def _write_to_db(
    identity: str,
    session_id: str,
    user_text: str,
    assistant_reply: str,
    patient_id: Optional[int] = None,
) -> None:
    """Insert user + assistant messages into doctor_chat_log."""
    async with AsyncSessionLocal() as db:
        db.add(DoctorChatLog(
            doctor_id=identity,
            session_id=session_id,
            patient_id=patient_id,
            role="user",
            content=user_text,
        ))
        db.add(DoctorChatLog(
            doctor_id=identity,
            session_id=session_id,
            patient_id=patient_id,
            role="assistant",
            content=assistant_reply,
        ))
        await db.commit()
