"""Intake session persistence (ADR 0016)."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db.engine import AsyncSessionLocal
from db.models.intake_session import IntakeStatus
from utils.log import log


@dataclass
class IntakeSession:
    id: str
    doctor_id: str
    patient_id: Optional[int]
    mode: str = "patient"
    status: str = IntakeStatus.active
    template_id: str = "medical_general_v1"
    collected: Dict[str, str] = field(default_factory=dict)
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0


async def create_session(
    doctor_id: str,
    patient_id: Optional[int],
    mode: str = "patient",
    initial_fields: Optional[Dict[str, str]] = None,
    template_id: str = "medical_general_v1",
) -> IntakeSession:
    """Create a new intake session in the DB.

    Args:
        initial_fields: Pre-extracted fields (from OCR, voice/paste, etc.)
            to pre-populate the session. Doctor reviews and fills gaps
            via the intake flow.
    """
    from db.models.intake_session import IntakeSessionDB

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    collected = initial_fields or {}
    conversation: List[Dict[str, Any]] = []

    # Auto-fill department from doctor profile if not already set
    if "department" not in collected or not collected.get("department"):
        try:
            from db.models.doctor import Doctor
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                doctor = (await db.execute(
                    select(Doctor).where(Doctor.id == doctor_id)
                )).scalar_one_or_none()
                if doctor and doctor.department:
                    collected["department"] = doctor.department
        except Exception:
            pass  # Non-critical — doctor can fill it manually

    # If pre-populated, add a system message so the intake LLM knows
    if initial_fields:
        fields_summary = "、".join(
            f"{k}" for k, v in initial_fields.items() if v
        )
        conversation.append({
            "role": "system",
            "content": f"以下字段已从导入数据中预提取，请医生确认或修改：{fields_summary}",
        })

    async with AsyncSessionLocal() as db:
        db_row = IntakeSessionDB(
            id=session_id,
            doctor_id=doctor_id,
            patient_id=patient_id,
            status=IntakeStatus.active,
            mode=mode,
            template_id=template_id,
            collected=json.dumps(collected, ensure_ascii=False),
            conversation=json.dumps(conversation, ensure_ascii=False),
            turn_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(db_row)
        await db.commit()

    pre = f" pre-populated={len(collected)} fields" if collected else ""
    log(f"[intake] session created id={session_id} patient={patient_id} doctor={doctor_id} mode={mode}{pre}")
    return IntakeSession(
        id=session_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        mode=mode,
        template_id=template_id,
        collected=collected,
        conversation=conversation,
    )


async def load_session(session_id: str) -> Optional[IntakeSession]:
    """Load an intake session from DB. Returns None if not found."""
    from db.models.intake_session import IntakeSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(IntakeSessionDB).where(IntakeSessionDB.id == session_id)
        )).scalar_one_or_none()

        if row is None:
            return None

        return IntakeSession(
            id=row.id,
            doctor_id=row.doctor_id,
            patient_id=row.patient_id,
            mode=row.mode,
            status=row.status,
            template_id=row.template_id,
            collected=json.loads(row.collected or "{}"),
            conversation=json.loads(row.conversation or "[]"),
            turn_count=row.turn_count,
        )


async def save_session(session: IntakeSession) -> None:
    """Persist intake session state to DB."""
    from db.models.intake_session import IntakeSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(IntakeSessionDB).where(IntakeSessionDB.id == session.id)
        )).scalar_one_or_none()

        if row is None:
            log(f"[intake] save_session: session {session.id} not found", level="error")
            return

        row.status = session.status
        row.mode = session.mode
        row.template_id = session.template_id
        row.patient_id = session.patient_id
        row.collected = json.dumps(session.collected, ensure_ascii=False)
        row.conversation = json.dumps(session.conversation, ensure_ascii=False)
        row.turn_count = session.turn_count
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()


async def get_active_session(patient_id: int, doctor_id: str) -> Optional[IntakeSession]:
    """Find an active (active or reviewing) session for this patient+doctor."""
    from db.models.intake_session import IntakeSessionDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(IntakeSessionDB).where(
                IntakeSessionDB.patient_id == patient_id,
                IntakeSessionDB.doctor_id == doctor_id,
                IntakeSessionDB.status.in_([IntakeStatus.active, IntakeStatus.reviewing]),
            ).order_by(IntakeSessionDB.created_at.desc()).limit(1)
        )).scalar_one_or_none()

        if row is None:
            return None

        return IntakeSession(
            id=row.id,
            doctor_id=row.doctor_id,
            patient_id=row.patient_id,
            mode=row.mode,
            status=row.status,
            template_id=row.template_id,
            collected=json.loads(row.collected or "{}"),
            conversation=json.loads(row.conversation or "[]"),
            turn_count=row.turn_count,
        )
