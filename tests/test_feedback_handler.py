"""Integration tests for POST /api/doctor/feedback + GET digest.

Phase F1/F3 of docs/specs/2026-04-21-ai-feedback-capture-plan.md — explicit
flag capture plus doctor-facing weekly digest. Reworked per Codex: feedback
is now 3 nullable columns on ``ai_suggestions`` (feedback_tag, feedback_note,
feedback_created_at), not a separate table. Tests assert the columns get
populated on the target row, and that the digest aggregates match.

Covers: happy path, enum validation (reason_tag), silent truncation of
reason_text beyond 1000 chars, 404 for unknown suggestion_id, empty digest,
and a seeded-digest happy path.
"""
from __future__ import annotations

import os
from datetime import datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import db.models  # noqa: F401 — register all ORM models before create_all
from db.engine import Base, get_db
from db.models.ai_suggestion import AISuggestion, SuggestionSection
from db.models.doctor import Doctor
from db.models.patient import Patient
from db.models.records import MedicalRecordDB, RecordStatus
from channels.web.doctor_dashboard.feedback_handlers import router as _feedback_router


TEST_DOCTOR_ID = "doc_feedback_test"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(_engine):
    Session = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_feedback_router)
    app.dependency_overrides[get_db] = _override_get_db

    os.environ.setdefault("ENVIRONMENT", "development")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _seed_record_and_suggestion(db_session) -> tuple[int, int]:
    """Create a doctor + record + one suggestion. Returns (record_id, suggestion_id)."""
    existing = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == TEST_DOCTOR_ID)
    )).scalar_one_or_none()
    if existing is None:
        db_session.add(Doctor(doctor_id=TEST_DOCTOR_ID, name="Feedback Test Doc"))
        await db_session.flush()

    rec = MedicalRecordDB(
        doctor_id=TEST_DOCTOR_ID,
        record_type="visit",
        status=RecordStatus.pending_review.value,
        content="chief complaint stub",
    )
    db_session.add(rec)
    await db_session.flush()

    sug = AISuggestion(
        record_id=rec.id,
        doctor_id=TEST_DOCTOR_ID,
        section=SuggestionSection.differential.value,
        content="不稳定型心绞痛（UA）",
        detail="胸闷活动后加重 + 既往 PCI 史",
    )
    db_session.add(sug)
    await db_session.commit()
    return rec.id, sug.id


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_updates_suggestion_columns(async_client, db_session):
    """POST with valid fields updates feedback_tag/note/created_at on the row."""
    record_id, suggestion_id = await _seed_record_and_suggestion(db_session)

    resp = await async_client.post(
        "/api/doctor/feedback",
        json={
            "suggestion_id": suggestion_id,
            "record_id": record_id,
            "doctor_id": TEST_DOCTOR_ID,
            "reason_tag": "insufficient_evidence",
            "reason_text": "病人同时有胸壁压痛，首先考虑非心源性胸痛",
            "doctor_action": "pending",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # id in response is the SUGGESTION id now (not a row in a separate table)
    assert body["id"] == suggestion_id
    assert body["created_at"] is not None

    # Suggestion row has feedback columns populated
    row = (await db_session.execute(
        select(AISuggestion).where(AISuggestion.id == suggestion_id)
    )).scalar_one()
    assert row.feedback_tag == "insufficient_evidence"
    assert row.feedback_note == "病人同时有胸壁压痛，首先考虑非心源性胸痛"
    assert row.feedback_created_at is not None


@pytest.mark.asyncio
async def test_invalid_reason_tag_rejected(async_client, db_session):
    """reason_tag outside FeedbackReasonTag enum → 422, row unchanged."""
    record_id, suggestion_id = await _seed_record_and_suggestion(db_session)

    resp = await async_client.post(
        "/api/doctor/feedback",
        json={
            "suggestion_id": suggestion_id,
            "record_id": record_id,
            "doctor_id": TEST_DOCTOR_ID,
            "reason_tag": "totally_made_up_reason",
        },
    )
    assert resp.status_code == 422, resp.text
    assert "reason_tag" in resp.json()["detail"]

    # Row untouched
    row = (await db_session.execute(
        select(AISuggestion).where(AISuggestion.id == suggestion_id)
    )).scalar_one()
    assert row.feedback_tag is None
    assert row.feedback_note is None
    assert row.feedback_created_at is None


@pytest.mark.asyncio
async def test_reason_text_over_1000_chars_is_truncated(async_client, db_session):
    """reason_text beyond 1000 chars is silently truncated (no 422)."""
    record_id, suggestion_id = await _seed_record_and_suggestion(db_session)

    long_text = "x" * 1500  # well over cap
    resp = await async_client.post(
        "/api/doctor/feedback",
        json={
            "suggestion_id": suggestion_id,
            "record_id": record_id,
            "doctor_id": TEST_DOCTOR_ID,
            "reason_tag": "other",
            "reason_text": long_text,
        },
    )
    assert resp.status_code == 200, resp.text

    row = (await db_session.execute(
        select(AISuggestion).where(AISuggestion.id == suggestion_id)
    )).scalar_one()
    assert row.feedback_note is not None
    assert len(row.feedback_note) == 1000
    assert row.feedback_note == "x" * 1000


@pytest.mark.asyncio
async def test_unknown_suggestion_id_returns_404(async_client, db_session):
    """suggestion_id that doesn't exist → 404."""
    # Seed a doctor so rate_limit / resolve doesn't trip on something else.
    await _seed_record_and_suggestion(db_session)

    resp = await async_client.post(
        "/api/doctor/feedback",
        json={
            "suggestion_id": 99_999_999,
            "record_id": 1,
            "doctor_id": TEST_DOCTOR_ID,
            "reason_tag": "wrong_diagnosis",
        },
    )
    assert resp.status_code == 404, resp.text
    assert "99999999" in resp.json()["detail"] or "not found" in resp.json()["detail"]


# ── F3 · digest tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_digest_empty(async_client, db_session):
    """Fresh doctor with no AI suggestions → all zeroes + empty recent list."""
    # Seed the doctor row so _resolve_ui_doctor_id doesn't blow up, but emit
    # no suggestions.
    existing = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == TEST_DOCTOR_ID)
    )).scalar_one_or_none()
    if existing is None:
        db_session.add(Doctor(doctor_id=TEST_DOCTOR_ID, name="Feedback Test Doc"))
        await db_session.commit()

    resp = await async_client.get(
        f"/api/doctor/feedback/digest?doctor_id={TEST_DOCTOR_ID}&days=7"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days"] == 7
    assert body["total_shown"] == 0
    assert body["total_accepted"] == 0
    assert body["total_flagged"] == 0
    # All three sections present, all zero — frontend relies on this shape.
    assert body["by_section"] == {
        "differential": 0,
        "workup": 0,
        "treatment": 0,
    }
    assert body["recent"] == []


@pytest.mark.asyncio
async def test_digest_happy_path(async_client, db_session):
    """Seed 3 suggestions + 1 flag; digest aggregates match + recent[0] matches."""
    # Seed doctor + a named patient + a record so we can assert patient_name
    # flows through the LEFT JOIN.
    existing = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == TEST_DOCTOR_ID)
    )).scalar_one_or_none()
    if existing is None:
        db_session.add(Doctor(doctor_id=TEST_DOCTOR_ID, name="Feedback Test Doc"))
        await db_session.flush()

    patient = Patient(doctor_id=TEST_DOCTOR_ID, name="陈梅")
    db_session.add(patient)
    await db_session.flush()

    rec = MedicalRecordDB(
        doctor_id=TEST_DOCTOR_ID,
        patient_id=patient.id,
        record_type="visit",
        status=RecordStatus.pending_review.value,
        content="chief complaint stub",
    )
    db_session.add(rec)
    await db_session.flush()

    # Three suggestions: one confirmed (accepted), one edited (accepted),
    # one pending (unresolved). We'll flag the workup one.
    s_diff = AISuggestion(
        record_id=rec.id,
        doctor_id=TEST_DOCTOR_ID,
        section=SuggestionSection.differential.value,
        content="不稳定型心绞痛",
        decision="confirmed",
    )
    s_workup = AISuggestion(
        record_id=rec.id,
        doctor_id=TEST_DOCTOR_ID,
        section=SuggestionSection.workup.value,
        content="头颅 CT",
        decision="edited",
    )
    s_tx = AISuggestion(
        record_id=rec.id,
        doctor_id=TEST_DOCTOR_ID,
        section=SuggestionSection.treatment.value,
        content="双抗强化",
        decision=None,
    )
    db_session.add_all([s_diff, s_workup, s_tx])
    await db_session.commit()

    # Flag s_workup via the real POST endpoint so we exercise the full path
    # and get feedback_created_at set server-side.
    flag_resp = await async_client.post(
        "/api/doctor/feedback",
        json={
            "suggestion_id": s_workup.id,
            "record_id": rec.id,
            "doctor_id": TEST_DOCTOR_ID,
            "reason_tag": "insufficient_evidence",
            "reason_text": "患者无神经系统症状，CT 优先级低",
        },
    )
    assert flag_resp.status_code == 200, flag_resp.text

    resp = await async_client.get(
        f"/api/doctor/feedback/digest?doctor_id={TEST_DOCTOR_ID}&days=7"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_shown"] == 3
    assert body["total_accepted"] == 2  # confirmed + edited
    assert body["total_flagged"] == 1
    assert body["by_section"]["workup"] == 1
    assert body["by_section"]["differential"] == 0
    assert body["by_section"]["treatment"] == 0

    assert len(body["recent"]) == 1
    first = body["recent"][0]
    assert first["id"] == s_workup.id
    assert first["section"] == "workup"
    assert first["content"] == "头颅 CT"
    assert first["feedback_tag"] == "insufficient_evidence"
    assert first["feedback_note"] == "患者无神经系统症状，CT 优先级低"
    assert first["feedback_created_at"] is not None
    assert first["patient_name"] == "陈梅"
