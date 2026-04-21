"""Integration tests for POST /records/{id}/review/finalize.

Phase 1c additions (inline-suggestions plan):
- `implicit_reject=True` marks untouched rows as rejected instead of 422.
- `edited_record` overrides the suggestion-rebuild writeback per field.

These tests drive the endpoint in-process with httpx ASGITransport so the
full handler (request model, dependency injection, commit path) is
exercised — the backward-compat guarantee lives in this test file.
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
from db.models.ai_suggestion import AISuggestion, SuggestionDecision, SuggestionSection
from db.models.doctor import Doctor
from db.models.records import MedicalRecordDB, RecordStatus
from channels.web.doctor_dashboard.diagnosis_handlers import router as _diag_router


TEST_DOCTOR_ID = "doc_finalize_test"


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
    app.include_router(_diag_router)
    app.dependency_overrides[get_db] = _override_get_db

    os.environ.setdefault("ENVIRONMENT", "development")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def _seed_record_with_suggestions(
    db_session,
    *,
    diagnoses: list[tuple[str, str | None]] | None = None,
    treatments: list[tuple[str, str | None]] | None = None,
    workup: list[tuple[str, str | None]] | None = None,
    undecided: list[tuple[str, str]] | None = None,  # (section, content)
) -> int:
    """Seed a doctor + record + suggestions. Returns the record_id.

    `diagnoses` / `treatments` / `workup` tuples are (content, decision).
    decision=None means undecided. `undecided` lets callers add more
    undecided rows without having to specify section-typed tuples.
    """
    existing = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == TEST_DOCTOR_ID)
    )).scalar_one_or_none()
    if existing is None:
        db_session.add(Doctor(doctor_id=TEST_DOCTOR_ID, name="Finalize Test Doc"))
        await db_session.flush()

    rec = MedicalRecordDB(
        doctor_id=TEST_DOCTOR_ID,
        record_type="visit",
        status=RecordStatus.pending_review.value,
        content="chief complaint stub",
    )
    db_session.add(rec)
    await db_session.flush()

    def _add(section: str, items: list[tuple[str, str | None]] | None):
        if not items:
            return
        for content, decision in items:
            db_session.add(AISuggestion(
                record_id=rec.id,
                doctor_id=TEST_DOCTOR_ID,
                section=section,
                content=content,
                decision=decision,
            ))

    _add(SuggestionSection.differential.value, diagnoses)
    _add(SuggestionSection.treatment.value, treatments)
    _add(SuggestionSection.workup.value, workup)

    if undecided:
        for section, content in undecided:
            db_session.add(AISuggestion(
                record_id=rec.id,
                doctor_id=TEST_DOCTOR_ID,
                section=section,
                content=content,
                decision=None,
            ))

    await db_session.commit()
    return rec.id


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_call_preserves_422_on_undecided(async_client, db_session):
    """Backward compat: no new params + undecided rows → 422 as before."""
    record_id = await _seed_record_with_suggestions(
        db_session,
        diagnoses=[("头痛考虑偏头痛", SuggestionDecision.confirmed.value)],
        undecided=[(SuggestionSection.treatment.value, "布洛芬 400mg")],
    )

    resp = await async_client.post(
        f"/api/doctor/records/{record_id}/review/finalize",
        json={"doctor_id": TEST_DOCTOR_ID},
    )
    assert resp.status_code == 422, resp.text
    assert "未处理" in resp.json()["detail"]

    # Record should NOT have been finalized
    rec = (await db_session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id)
    )).scalar_one()
    assert rec.status == RecordStatus.pending_review.value

    # Undecided row stays at decision=None (no writeback side-effect)
    sug = (await db_session.execute(
        select(AISuggestion).where(
            AISuggestion.record_id == record_id,
            AISuggestion.section == SuggestionSection.treatment.value,
        )
    )).scalar_one()
    assert sug.decision is None


@pytest.mark.asyncio
async def test_implicit_reject_marks_untouched_as_rejected(async_client, db_session):
    """implicit_reject=True flips decision=NULL rows to rejected and finalizes."""
    record_id = await _seed_record_with_suggestions(
        db_session,
        diagnoses=[("头痛考虑偏头痛", SuggestionDecision.confirmed.value)],
        treatments=[("布洛芬 400mg", SuggestionDecision.confirmed.value)],
        undecided=[
            (SuggestionSection.workup.value, "头颅 MRI"),
            (SuggestionSection.differential.value, "紧张性头痛（备选）"),
        ],
    )

    resp = await async_client.post(
        f"/api/doctor/records/{record_id}/review/finalize",
        json={"doctor_id": TEST_DOCTOR_ID, "implicit_reject": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"

    # Record finalized
    rec = (await db_session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id)
    )).scalar_one()
    assert rec.status == RecordStatus.completed.value

    # Untouched rows now rejected, with decided_at populated
    all_rows = (await db_session.execute(
        select(AISuggestion).where(AISuggestion.record_id == record_id)
    )).scalars().all()
    rejected = [r for r in all_rows if r.decision == SuggestionDecision.rejected.value]
    assert len(rejected) == 2
    for r in rejected:
        assert r.decided_at is not None

    # Writeback uses only confirmed — rejected MRI is NOT in orders_followup
    assert rec.orders_followup is None or "MRI" not in (rec.orders_followup or "")
    # Confirmed diagnosis only
    assert rec.diagnosis is not None and "偏头痛" in rec.diagnosis
    assert "紧张性头痛" not in rec.diagnosis
    # Confirmed treatment only
    assert rec.treatment_plan is not None and "布洛芬" in rec.treatment_plan


@pytest.mark.asyncio
async def test_edited_record_overrides_diagnosis(async_client, db_session):
    """edited_record['diagnosis'] wins over the suggestion-rebuild writeback."""
    record_id = await _seed_record_with_suggestions(
        db_session,
        diagnoses=[("头痛考虑偏头痛", SuggestionDecision.confirmed.value)],
    )

    resp = await async_client.post(
        f"/api/doctor/records/{record_id}/review/finalize",
        json={
            "doctor_id": TEST_DOCTOR_ID,
            "edited_record": {"diagnosis": "后循环缺血（PCI），伴发作性眩晕"},
        },
    )
    assert resp.status_code == 200, resp.text

    rec = (await db_session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id)
    )).scalar_one()
    # Direct edit takes precedence — no AI rebuild text
    assert rec.diagnosis == "后循环缺血（PCI），伴发作性眩晕"
    assert "偏头痛" not in rec.diagnosis


@pytest.mark.asyncio
async def test_edited_record_empty_string_clears_field(async_client, db_session):
    """Empty string in edited_record is still honored (intentional clear)."""
    record_id = await _seed_record_with_suggestions(
        db_session,
        diagnoses=[("头痛考虑偏头痛", SuggestionDecision.confirmed.value)],
        treatments=[("布洛芬 400mg", SuggestionDecision.confirmed.value)],
    )

    resp = await async_client.post(
        f"/api/doctor/records/{record_id}/review/finalize",
        json={
            "doctor_id": TEST_DOCTOR_ID,
            "edited_record": {"treatment_plan": ""},
        },
    )
    assert resp.status_code == 200, resp.text

    rec = (await db_session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id)
    )).scalar_one()
    assert rec.treatment_plan == ""
    # Diagnosis still uses rebuild (field not in edited_record)
    assert rec.diagnosis is not None and "偏头痛" in rec.diagnosis


@pytest.mark.asyncio
async def test_both_params_combined(async_client, db_session):
    """implicit_reject + edited_record work together."""
    record_id = await _seed_record_with_suggestions(
        db_session,
        treatments=[("布洛芬 400mg", SuggestionDecision.confirmed.value)],
        undecided=[(SuggestionSection.differential.value, "紧张性头痛")],
    )

    resp = await async_client.post(
        f"/api/doctor/records/{record_id}/review/finalize",
        json={
            "doctor_id": TEST_DOCTOR_ID,
            "implicit_reject": True,
            "edited_record": {
                "diagnosis": "后循环缺血",
                "orders_followup": "头颅 MRI + TCD",
            },
        },
    )
    assert resp.status_code == 200, resp.text

    rec = (await db_session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id)
    )).scalar_one()
    # Direct edits take precedence for both fields
    assert rec.diagnosis == "后循环缺血"
    assert rec.orders_followup == "头颅 MRI + TCD"
    # Treatment falls back to rebuild
    assert rec.treatment_plan is not None and "布洛芬" in rec.treatment_plan

    # Untouched differential row was rejected
    undecided_row = (await db_session.execute(
        select(AISuggestion).where(
            AISuggestion.record_id == record_id,
            AISuggestion.section == SuggestionSection.differential.value,
        )
    )).scalar_one()
    assert undecided_row.decision == SuggestionDecision.rejected.value


@pytest.mark.asyncio
async def test_edited_record_unknown_field_ignored(async_client, db_session):
    """Unknown keys in edited_record are silently ignored, not a 422."""
    record_id = await _seed_record_with_suggestions(
        db_session,
        diagnoses=[("头痛考虑偏头痛", SuggestionDecision.confirmed.value)],
    )

    resp = await async_client.post(
        f"/api/doctor/records/{record_id}/review/finalize",
        json={
            "doctor_id": TEST_DOCTOR_ID,
            "edited_record": {
                "chief_complaint": "突发头痛 2 小时",  # not a Phase 1c allowed key
                "totally_made_up_field": "ignored",
            },
        },
    )
    assert resp.status_code == 200, resp.text

    rec = (await db_session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id)
    )).scalar_one()
    # chief_complaint NOT written (not a Phase 1c allowed key → ignored silently).
    # Seed didn't set it, so it remains None — the key point is that the
    # "突发头痛 2 小时" value from edited_record was NOT written.
    assert rec.chief_complaint != "突发头痛 2 小时"
    # Diagnosis still uses suggestion-rebuild (diagnosis key not in edits)
    assert rec.diagnosis is not None and "偏头痛" in rec.diagnosis
