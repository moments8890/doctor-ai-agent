"""Interview session persistence (ADR 0016)."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.engine import AsyncSessionLocal
from db.models.interview_session import InterviewStatus
from utils.log import log


@dataclass
class InterviewSession:
    id: str
    doctor_id: str
    patient_id: Optional[int]
    mode: str = "patient"
    status: str = InterviewStatus.interviewing
    collected: Dict[str, str] = field(default_factory=dict)
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0


async def create_session(
    doctor_id: str,
    patient_id: Optional[int],
    mode: str = "patient",
    initial_fields: Optional[Dict[str, str]] = None,
) -> InterviewSession:
    """Create a new interview session in the DB.

    Args:
        initial_fields: Pre-extracted fields (from OCR, voice/paste, etc.)
            to pre-populate the session. Doctor reviews and fills gaps
            via the interview flow.
    """
    from db.models.interview_session import InterviewSessionDB

    session_id = str(uuid.uuid4())
    now = datetime.utcnow()

    collected = initial_fields or {}
    conversation: List[Dict[str, Any]] = []

    # If pre-populated, add a system message so the interview LLM knows
    if initial_fields:
        fields_summary = "、".join(
            f"{k}" for k, v in initial_fields.items() if v
        )
        conversation.append({
            "role": "system",
            "content": f"以下字段已从导入数据中预提取，请医生确认或修改：{fields_summary}",
        })

    async with AsyncSessionLocal() as db:
        db_row = InterviewSessionDB(
            id=session_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            status=InterviewStatus.interviewing,
            mode=mode,
            collected=json.dumps(collected, ensure_ascii=False),
            conversation=json.dumps(conversation, ensure_ascii=False),
            turn_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(db_row)
        await db.commit()

    pre = f" pre-populated={len(collected)} fields" if collected else ""
    log(f"[interview] session created id={session_id} patient={patient_id} doctor={doctor_id} mode={mode}{pre}")
    return InterviewSession(
        id=session_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        mode=mode,
        collected=collected,
        conversation=conversation,
    )


async def load_session(session_id: str) -> Optional[InterviewSession]:
    """Load an interview session from DB. Returns None if not found."""
    from db.models.interview_session import InterviewSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(InterviewSessionDB).where(InterviewSessionDB.id == session_id)
        )).scalar_one_or_none()

        if row is None:
            return None

        return InterviewSession(
            id=row.id,
            doctor_id=row.doctor_id,
            patient_id=row.patient_id,
            mode=row.mode,
            status=row.status,
            collected=json.loads(row.collected or "{}"),
            conversation=json.loads(row.conversation or "[]"),
            turn_count=row.turn_count,
        )


async def save_session(session: InterviewSession) -> None:
    """Persist interview session state to DB."""
    from db.models.interview_session import InterviewSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(InterviewSessionDB).where(InterviewSessionDB.id == session.id)
        )).scalar_one_or_none()

        if row is None:
            log(f"[interview] save_session: session {session.id} not found", level="error")
            return

        row.status = session.status
        row.mode = session.mode
        row.patient_id = session.patient_id
        row.collected = json.dumps(session.collected, ensure_ascii=False)
        row.conversation = json.dumps(session.conversation, ensure_ascii=False)
        row.turn_count = session.turn_count
        row.updated_at = datetime.utcnow()
        await db.commit()


async def get_active_session(patient_id: int, doctor_id: str) -> Optional[InterviewSession]:
    """Find an active (interviewing or reviewing) session for this patient+doctor."""
    from db.models.interview_session import InterviewSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(InterviewSessionDB).where(
                InterviewSessionDB.patient_id == patient_id,
                InterviewSessionDB.doctor_id == doctor_id,
                InterviewSessionDB.status.in_([InterviewStatus.interviewing, InterviewStatus.reviewing]),
            ).order_by(InterviewSessionDB.created_at.desc()).limit(1)
        )).scalar_one_or_none()

        if row is None:
            return None

        return InterviewSession(
            id=row.id,
            doctor_id=row.doctor_id,
            patient_id=row.patient_id,
            mode=row.mode,
            status=row.status,
            collected=json.loads(row.collected or "{}"),
            conversation=json.loads(row.conversation or "[]"),
            turn_count=row.turn_count,
        )
