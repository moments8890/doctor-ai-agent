"""
P3 Review Queue integration tests — real DB, no LLM.

Tests the full review workflow: create → list → detail → edit → confirm.
Uses in-memory SQLite via session_factory fixture from conftest.
"""
from __future__ import annotations

import json
from typing import Dict

import pytest
import pytest_asyncio

from db.models import Doctor, Patient, MedicalRecordDB, MedicalRecordVersion
from db.models.interview_session import InterviewSessionDB
from db.models.review_queue import ReviewQueue
from db.crud.review import (
    create_review,
    list_reviews,
    get_review_detail,
    confirm_review,
    update_review_field,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_doctor(session, doctor_id: str = "test_doctor") -> str:
    """Create a doctor row and return the doctor_id."""
    session.add(Doctor(doctor_id=doctor_id, name="Dr. Test", specialty="神经外科"))
    await session.flush()
    return doctor_id


async def _seed_patient(session, doctor_id: str, name: str = "王明华") -> int:
    """Create a patient row and return the id."""
    p = Patient(doctor_id=doctor_id, name=name, gender="male", year_of_birth=1974)
    session.add(p)
    await session.flush()
    return p.id


async def _seed_record(
    session,
    doctor_id: str,
    patient_id: int,
    structured: Dict[str, str] = None,
) -> int:
    """Create a medical_records row and return the id."""
    if structured is None:
        structured = {
            "chief_complaint": "头痛反复发作2周，伴恶心呕吐",
            "present_illness": "患者2周前无明显诱因出现头痛",
            "past_history": "高血压病史5年",
        }
    rec = MedicalRecordDB(
        doctor_id=doctor_id,
        patient_id=patient_id,
        record_type="interview_summary",
        content="主诉：头痛反复发作2周\n现病史：患者2周前无明显诱因出现头痛",
        structured=json.dumps(structured, ensure_ascii=False),
        tags=json.dumps(["头痛", "恶心"], ensure_ascii=False),
    )
    session.add(rec)
    await session.flush()
    return rec.id


async def _seed_interview(session, doctor_id: str, patient_id: int) -> str:
    """Create an interview_sessions row with conversation data."""
    interview = InterviewSessionDB(
        id="intv_test_001",
        doctor_id=doctor_id,
        patient_id=patient_id,
        status="completed",
        collected=json.dumps({"chief_complaint": "头痛反复发作2周"}, ensure_ascii=False),
        conversation=json.dumps([
            {"role": "assistant", "content": "您好，请问您今天来就诊的主要不适是什么？"},
            {"role": "user", "content": "我头痛有两个星期了，还恶心想吐。"},
            {"role": "assistant", "content": "头痛的位置主要在哪里？"},
            {"role": "user", "content": "前额，持续性的胀痛。"},
        ], ensure_ascii=False),
        turn_count=2,
    )
    session.add(interview)
    await session.flush()
    return interview.id


async def _seed_full(session, doctor_id: str = "test_doctor"):
    """Seed a complete review scenario: doctor + patient + record + interview + review queue."""
    did = await _seed_doctor(session, doctor_id)
    pid = await _seed_patient(session, did)
    rid = await _seed_record(session, did, pid)
    await _seed_interview(session, did, pid)
    review = await create_review(session, record_id=rid, doctor_id=did, patient_id=pid)
    await session.commit()
    return {"doctor_id": did, "patient_id": pid, "record_id": rid, "review_id": review.id}


# ── Test 1: Full Happy Path ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_review_happy_path(session_factory):
    """Interview → review queue → list → detail → confirm → reviewed list."""
    async with session_factory() as session:
        ids = await _seed_full(session)

    # List pending reviews
    async with session_factory() as session:
        items = await list_reviews(session, ids["doctor_id"], status="pending_review")
        assert len(items) == 1
        item = items[0]
        assert item["patient_name"] == "王明华"
        assert "头痛" in item["chief_complaint"]
        assert item["status"] == "pending_review"
        assert item["record_id"] == ids["record_id"]

    # Get review detail
    async with session_factory() as session:
        detail = await get_review_detail(session, ids["review_id"], ids["doctor_id"])
        assert detail is not None
        assert detail["record"]["structured"]["chief_complaint"] == "头痛反复发作2周，伴恶心呕吐"
        assert detail["patient"]["name"] == "王明华"
        assert detail["patient"]["gender"] == "male"
        assert detail["patient"]["year_of_birth"] == 1974
        assert len(detail["conversation"]) == 4
        assert detail["conversation"][0]["role"] == "assistant"
        assert detail["status"] == "pending_review"

    # Confirm review
    async with session_factory() as session:
        rq = await confirm_review(session, ids["review_id"], ids["doctor_id"])
        assert rq is not None
        assert rq.status == "reviewed"
        assert rq.reviewed_at is not None
        await session.commit()

    # Verify it appears in reviewed list
    async with session_factory() as session:
        reviewed = await list_reviews(session, ids["doctor_id"], status="reviewed")
        assert len(reviewed) == 1
        assert reviewed[0]["status"] == "reviewed"

    # Verify it's gone from pending
    async with session_factory() as session:
        pending = await list_reviews(session, ids["doctor_id"], status="pending_review")
        assert len(pending) == 0


# ── Test 2: Inline Edit + Audit Trail ────────────────────────────────────────

@pytest.mark.asyncio
async def test_inline_edit_and_audit_trail(session_factory):
    """Edit a structured field → verify update + MedicalRecordVersion created."""
    async with session_factory() as session:
        ids = await _seed_full(session)

    # Edit chief_complaint
    async with session_factory() as session:
        result = await update_review_field(
            session, ids["review_id"], ids["doctor_id"],
            field="chief_complaint", value="头痛3天",
        )
        assert result is not None
        assert result["structured"]["chief_complaint"] == "头痛3天"
        await session.commit()

    # Verify the record was updated
    async with session_factory() as session:
        detail = await get_review_detail(session, ids["review_id"], ids["doctor_id"])
        assert detail["record"]["structured"]["chief_complaint"] == "头痛3天"

    # Verify audit trail (MedicalRecordVersion with old_structured)
    async with session_factory() as session:
        from sqlalchemy import select
        versions = (await session.execute(
            select(MedicalRecordVersion)
            .where(MedicalRecordVersion.record_id == ids["record_id"])
        )).scalars().all()
        assert len(versions) == 1
        v = versions[0]
        assert v.old_structured is not None
        old = json.loads(v.old_structured)
        assert old["chief_complaint"] == "头痛反复发作2周，伴恶心呕吐"
        assert v.doctor_id == ids["doctor_id"]

    # Invalid field → returns None (caller raises 422)
    async with session_factory() as session:
        result = await update_review_field(
            session, ids["review_id"], ids["doctor_id"],
            field="invalid_field", value="x",
        )
        assert result is None


# ── Test 3: Edge Cases + Data Isolation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_edge_cases_and_data_isolation(session_factory):
    """Data isolation between doctors, double-confirm, nonexistent ID."""
    async with session_factory() as session:
        # Seed doctor A with a review
        ids_a = await _seed_full(session, doctor_id="doctor_a")
        # Seed doctor B (no reviews)
        await _seed_doctor(session, "doctor_b")
        await session.commit()

    # Doctor B cannot see doctor A's reviews
    async with session_factory() as session:
        items_b = await list_reviews(session, "doctor_b", status="pending_review")
        assert len(items_b) == 0

    # Doctor B cannot access doctor A's review detail
    async with session_factory() as session:
        detail = await get_review_detail(session, ids_a["review_id"], "doctor_b")
        assert detail is None

    # Doctor B cannot confirm doctor A's review
    async with session_factory() as session:
        rq = await confirm_review(session, ids_a["review_id"], "doctor_b")
        assert rq is None

    # Doctor A confirms successfully
    async with session_factory() as session:
        rq = await confirm_review(session, ids_a["review_id"], "doctor_a")
        assert rq is not None
        assert rq.status == "reviewed"
        await session.commit()

    # Double-confirm returns None
    async with session_factory() as session:
        rq = await confirm_review(session, ids_a["review_id"], "doctor_a")
        assert rq is None

    # Nonexistent queue ID returns None
    async with session_factory() as session:
        detail = await get_review_detail(session, 99999, "doctor_a")
        assert detail is None

    # Nonexistent queue ID for confirm returns None
    async with session_factory() as session:
        rq = await confirm_review(session, 99999, "doctor_a")
        assert rq is None
