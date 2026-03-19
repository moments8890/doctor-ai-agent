"""Chat archive: persist and retrieve conversation turns."""
from __future__ import annotations

from typing import List, Optional

from db.engine import AsyncSessionLocal
from db.models.doctor import ChatArchive
from sqlalchemy import select


async def get_recent_turns(doctor_id: str, limit: int = 20) -> List[dict]:
    """Read recent turns from chat_archive for conversation context."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(ChatArchive)
                .where(ChatArchive.doctor_id == doctor_id)
                .order_by(ChatArchive.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


async def archive_turns(
    doctor_id: str,
    user_text: str,
    assistant_reply: str,
    patient_id: Optional[int] = None,
) -> None:
    """Append user + assistant turns to chat_archive."""
    from db.crud import append_chat_archive
    turns = [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_reply},
    ]
    async with AsyncSessionLocal() as db:
        await append_chat_archive(db, doctor_id, turns, patient_id=patient_id)
        await db.commit()
