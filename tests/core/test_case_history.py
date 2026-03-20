"""P1 Case History integration tests — real DB, mocked embeddings."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import pytest_asyncio

from db.models import Doctor, Patient, MedicalRecordDB
from db.models.case_history import CaseHistory
from db.crud.case_history import (
    create_case, confirm_case, match_cases, list_cases, SEED_DOCTOR_ID,
)


def _fake_embed(text):
    """Deterministic fake embedding: hash text to a 1024-d vector."""
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    vec = [float(b) / 255.0 for b in h] * 32  # 32 * 32 = 1024
    # Normalize
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


@pytest.fixture(autouse=True)
def mock_embed():
    with patch("db.crud.case_history.embed", side_effect=_fake_embed):
        with patch("db.crud.case_history.get_model_name", return_value="test-model"):
            yield


async def _seed_doctor(session, doctor_id="test_doctor"):
    session.add(Doctor(doctor_id=doctor_id, name="Dr. Test", specialty="神经外科"))
    await session.flush()
    return doctor_id


@pytest.mark.asyncio
async def test_create_and_list_case(session_factory):
    async with session_factory() as session:
        did = await _seed_doctor(session)
        case = await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="头痛反复发作2周",
            present_illness="前额持续性胀痛",
        )
        await session.commit()
        assert case.confidence_status == "preliminary"
        assert case.embedding is not None

    async with session_factory() as session:
        cases = await list_cases(session, "test_doctor")
        assert len(cases) == 1
        assert cases[0].chief_complaint == "头痛反复发作2周"


@pytest.mark.asyncio
async def test_confirm_case_reembeds(session_factory):
    async with session_factory() as session:
        did = await _seed_doctor(session)
        case = await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="头痛反复发作2周",
        )
        await session.commit()
        old_embedding = case.embedding

    async with session_factory() as session:
        confirmed = await confirm_case(
            session, case.id, "test_doctor",
            final_diagnosis="脑膜瘤",
            treatment="手术切除",
        )
        await session.commit()
        assert confirmed.confidence_status == "confirmed"
        assert confirmed.final_diagnosis == "脑膜瘤"
        assert confirmed.embedding != old_embedding  # re-embedded with diagnosis


@pytest.mark.asyncio
async def test_match_cases_returns_confirmed_only(session_factory):
    async with session_factory() as session:
        did = await _seed_doctor(session)
        # Create + confirm one case
        c1 = await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="头痛伴恶心呕吐",
        )
        await session.flush()
        await confirm_case(session, c1.id, did, final_diagnosis="脑膜瘤")
        # Create preliminary case (should NOT match)
        await create_case(
            session, doctor_id=did, record_id=None, patient_id=None,
            chief_complaint="腰痛伴左下肢放射痛",
        )
        await session.commit()

    async with session_factory() as session:
        matches = await match_cases(session, did, "头痛2周")
        # Only confirmed case should appear
        assert len(matches) >= 1
        assert all(m["final_diagnosis"] is not None for m in matches)


@pytest.mark.asyncio
async def test_match_includes_seed_cases(session_factory):
    async with session_factory() as session:
        await _seed_doctor(session, "test_doctor")
        await _seed_doctor(session, SEED_DOCTOR_ID)
        # Create seed case
        seed = await create_case(
            session, doctor_id=SEED_DOCTOR_ID, record_id=None, patient_id=None,
            chief_complaint="突发剧烈头痛",
        )
        await session.flush()
        await confirm_case(session, seed.id, SEED_DOCTOR_ID, final_diagnosis="SAH")
        await session.commit()

    async with session_factory() as session:
        matches = await match_cases(session, "test_doctor", "突发头痛")
        assert len(matches) >= 1
        assert any(m["is_seed"] for m in matches)


@pytest.mark.asyncio
async def test_data_isolation(session_factory):
    async with session_factory() as session:
        await _seed_doctor(session, "doctor_a")
        await _seed_doctor(session, "doctor_b")
        c = await create_case(
            session, doctor_id="doctor_a", record_id=None, patient_id=None,
            chief_complaint="头痛",
        )
        await session.flush()
        await confirm_case(session, c.id, "doctor_a", final_diagnosis="偏头痛")
        await session.commit()

    async with session_factory() as session:
        # Doctor B should not see doctor A's cases (only seeds)
        cases_b = await list_cases(session, "doctor_b")
        assert len(cases_b) == 0
