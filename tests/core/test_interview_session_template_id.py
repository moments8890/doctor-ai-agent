"""Template id threading: Doctor.preferred_template_id + InterviewSession CRUD."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db.models.doctor import Doctor


@pytest.mark.asyncio
async def test_doctor_preferred_template_id_defaults_to_null(db_session):
    d = Doctor(doctor_id="test_pref_null", name="Test Doctor")
    db_session.add(d)
    await db_session.commit()

    row = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == "test_pref_null")
    )).scalar_one()
    assert row.preferred_template_id is None


@pytest.mark.asyncio
async def test_doctor_preferred_template_id_can_be_set(db_session):
    d = Doctor(
        doctor_id="test_pref_set",
        name="Test Doctor",
        preferred_template_id="medical_general_v1",
    )
    db_session.add(d)
    await db_session.commit()

    row = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == "test_pref_set")
    )).scalar_one()
    assert row.preferred_template_id == "medical_general_v1"
