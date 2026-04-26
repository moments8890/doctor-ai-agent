"""Tests for the doctor-side patient-attach-code endpoint.

Covers: returns code+qr_url for an existing doctor, returns same code
across repeated calls (permanent), lazy backfills a missing code, and
404s an unknown doctor.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from db.models.doctor import Doctor
from channels.web.doctor_dashboard.attach_code_handlers import (
    get_patient_attach_code,
)


@pytest.mark.asyncio
async def test_returns_code_and_qr_url(db_session):
    db_session.add(Doctor(doctor_id="doc_x", name="Dr X", patient_attach_code="AB2C"))
    await db_session.flush()
    result = await get_patient_attach_code(
        doctor_id="doc_x", authorization=None, db=db_session,
    )
    assert result["code"] == "AB2C"
    assert result["qr_url"].endswith("/patient/register?code=AB2C")


@pytest.mark.asyncio
async def test_returns_same_code_on_repeated_calls(db_session):
    db_session.add(Doctor(doctor_id="doc_y", name="Dr Y", patient_attach_code="XY3Z"))
    await db_session.flush()
    a = await get_patient_attach_code(doctor_id="doc_y", authorization=None, db=db_session)
    b = await get_patient_attach_code(doctor_id="doc_y", authorization=None, db=db_session)
    assert a["code"] == b["code"] == "XY3Z"


@pytest.mark.asyncio
async def test_lazy_backfill_when_code_missing(db_session):
    db_session.add(Doctor(doctor_id="doc_z", name="Dr Z", patient_attach_code=None))
    await db_session.flush()
    result = await get_patient_attach_code(doctor_id="doc_z", authorization=None, db=db_session)
    assert result["code"] is not None
    assert len(result["code"]) == 4


@pytest.mark.asyncio
async def test_unknown_doctor_returns_404(db_session):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await get_patient_attach_code(
            doctor_id="ghost", authorization=None, db=db_session,
        )
    assert exc.value.status_code == 404
