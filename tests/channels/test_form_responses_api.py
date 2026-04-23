"""Form response GET endpoints — unit-level tests."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from db.models.form_response import FormResponseDB
from db.models.patient import Patient


async def _seed():
    """Create doctor + patient + one form response.

    Returns (doctor_id, patient_id, response_id).
    """
    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.flush()
        patient = Patient(doctor_id=doc_id, name="测试患者")
        db.add(patient)
        await db.commit()
        pid = patient.id

    async with AsyncSessionLocal() as db:
        row = FormResponseDB(
            doctor_id=doc_id,
            patient_id=pid,
            template_id="form_satisfaction_v1",
            payload={"overall_rating": "满意"},
        )
        db.add(row)
        await db.commit()
        rid = row.id

    return doc_id, pid, rid


@pytest.mark.asyncio
async def test_get_form_response_returns_payload():
    from channels.web.form_responses import get_form_response

    doc_id, pid, rid = await _seed()

    with patch(
        "channels.web.form_responses._resolve",
        new=AsyncMock(return_value=doc_id),
    ):
        async with AsyncSessionLocal() as db:
            body = await get_form_response(
                response_id=rid,
                authorization=None,
                x_doctor_id=doc_id,
                db=db,
            )

    assert body["id"] == rid
    assert body["template_id"] == "form_satisfaction_v1"
    assert body["payload"]["overall_rating"] == "满意"


@pytest.mark.asyncio
async def test_get_form_response_404_for_missing():
    from channels.web.form_responses import get_form_response

    async with AsyncSessionLocal() as db:
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    with patch(
        "channels.web.form_responses._resolve",
        new=AsyncMock(return_value=doc_id),
    ):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as excinfo:
                await get_form_response(
                    response_id=99999999,
                    authorization=None,
                    x_doctor_id=doc_id,
                    db=db,
                )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_get_form_response_403_for_other_doctor():
    from channels.web.form_responses import get_form_response

    doc_id, _, rid = await _seed()

    other_doc = f"doc_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=other_doc))
        await db.commit()

    with patch(
        "channels.web.form_responses._resolve",
        new=AsyncMock(return_value=other_doc),
    ):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as excinfo:
                await get_form_response(
                    response_id=rid,
                    authorization=None,
                    x_doctor_id=other_doc,
                    db=db,
                )
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_list_form_responses_returns_rows():
    from channels.web.form_responses import list_form_responses

    doc_id, pid, rid = await _seed()

    with patch(
        "channels.web.form_responses._resolve",
        new=AsyncMock(return_value=doc_id),
    ):
        async with AsyncSessionLocal() as db:
            body = await list_form_responses(
                patient_id=pid,
                template_id=None,
                authorization=None,
                x_doctor_id=doc_id,
                db=db,
            )

    assert isinstance(body, list)
    assert len(body) >= 1
    assert body[0]["template_id"] == "form_satisfaction_v1"


@pytest.mark.asyncio
async def test_list_form_responses_filters_by_template_id():
    from channels.web.form_responses import list_form_responses

    doc_id, pid, _ = await _seed()

    with patch(
        "channels.web.form_responses._resolve",
        new=AsyncMock(return_value=doc_id),
    ):
        async with AsyncSessionLocal() as db:
            body = await list_form_responses(
                patient_id=pid,
                template_id="nonexistent_v1",
                authorization=None,
                x_doctor_id=doc_id,
                db=db,
            )
    assert body == []
