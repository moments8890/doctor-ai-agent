"""Integration tests for POST /api/doctor/feedback.

Phase F1 of docs/specs/2026-04-21-ai-feedback-capture-plan.md — explicit
flag capture. Reworked per Codex: feedback is now 3 nullable columns on
``ai_suggestions`` (feedback_tag, feedback_note, feedback_created_at), not
a separate table. Tests assert the columns get populated on the target row.

Covers: happy path, enum validation (reason_tag), silent truncation of
reason_text beyond 1000 chars, and 404 for unknown suggestion_id.
"""
from __future__ import annotations

import os

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
