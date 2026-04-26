"""Shared writers for intake templates.

Form templates all persist to the form_responses table — share one writer
across any template with kind="form". Medical templates have their own
writer (MedicalRecordWriter) with specialty-specific column mapping.
"""
from __future__ import annotations

from fastapi import HTTPException

from db.engine import AsyncSessionLocal
from db.crud.doctor import _ensure_doctor_exists
from db.models.form_response import FormResponseDB
from domain.intake.protocols import PersistRef, SessionState


class FormResponseWriter:
    """Persists to form_responses. Reusable across any kind="form" template."""

    async def persist(
        self, session: SessionState, collected: dict[str, str],
    ) -> PersistRef:
        if session.patient_id is None:
            raise HTTPException(
                status_code=422,
                detail="无法提交表单：缺少 patient_id（表单模板要求已认证患者）",
            )

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, session.doctor_id)
            row = FormResponseDB(
                doctor_id=session.doctor_id,
                patient_id=session.patient_id,
                template_id=session.template_id,
                session_id=session.id,
                payload=dict(collected),
                # status defaults to "draft" via server_default
            )
            db.add(row)
            await db.commit()
            row_id = row.id

        return PersistRef(kind="form_response", id=row_id)
