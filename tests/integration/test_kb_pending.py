"""Integration: factual edit → KbPendingItem → accept → DoctorKnowledgeItem.

Runs in-process using an ASGITransport client so that unittest.mock.patch
can intercept the LLM calls.  Does NOT require a running external server.

The ``require_server``, ``require_ollama``, ``presweep_inttest_rows``, and
``clean_integration_db`` fixtures from the integration conftest are overridden
below so that these tests can run standalone.
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import httpx
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import db.models  # noqa: F401 — register all ORM models before create_all
from db.engine import Base, get_db
from db.models.doctor import Doctor, DoctorKnowledgeItem
from db.models.kb_pending import KbPendingItem
from channels.web.doctor_dashboard.kb_pending_handlers import router as _kb_router
from domain.knowledge.persona_learning import process_edit_for_learning


# ---------------------------------------------------------------------------
# Override session-scoped integration guards — in-process tests only
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def require_server():  # noqa: F811
    """No-op override: in-process tests don't need the dev server."""
    return


@pytest.fixture(autouse=True)
def require_ollama():  # noqa: F811
    """No-op override: LLM is mocked."""
    return


@pytest.fixture(autouse=True)
def presweep_inttest_rows():  # noqa: F811
    """No-op override: no live DB to sweep."""
    return


@pytest.fixture(autouse=True)
def clean_integration_db():  # noqa: F811
    """No-op override: in-memory DB, nothing to clean."""
    return


# ---------------------------------------------------------------------------
# Shared in-memory engine — module-scoped so tables are created once
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def _test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


# ---------------------------------------------------------------------------
# Per-test session fixture (function-scoped for isolation)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session(_test_engine):
    """Single async session; each test gets its own transaction that is
    rolled back on teardown via SAVEPOINT / nested-begin semantics."""
    _Session = async_sessionmaker(_test_engine, expire_on_commit=False)
    async with _Session() as session:
        yield session


# ---------------------------------------------------------------------------
# HTTP client wired to the in-process app
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def async_client(_test_engine):
    """httpx AsyncClient wired to a minimal in-process FastAPI app."""
    _Session = async_sessionmaker(_test_engine, expire_on_commit=False)

    async def _override_get_db():
        async with _Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_kb_router)
    app.dependency_overrides[get_db] = _override_get_db

    # Allow doctor_id query-param auth in non-production env
    os.environ.setdefault("ENVIRONMENT", "development")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# Test doctor
# ---------------------------------------------------------------------------

TEST_DOCTOR_ID = "TEST_FACT_DOC"


@pytest_asyncio.fixture(autouse=True)
async def ensure_test_doctor(db_session):
    """Insert the test doctor if it doesn't exist yet (idempotent)."""
    existing = (await db_session.execute(
        select(Doctor).where(Doctor.doctor_id == TEST_DOCTOR_ID)
    )).scalar_one_or_none()
    if existing is None:
        db_session.add(Doctor(doctor_id=TEST_DOCTOR_ID, name="Test Doctor"))
        await db_session.commit()


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------

def _patch_llm(payload: dict):
    """Context manager pair: patch get_prompt_sync + llm_call with fixed payload."""
    from domain.knowledge import persona_classifier as pc
    return (
        patch.object(pc, "get_prompt_sync", return_value="{original} {edited}"),
        patch("agent.llm.llm_call", new=AsyncMock(return_value=json.dumps(payload))),
    )


# ---------------------------------------------------------------------------
# Tests: process_edit_for_learning (unit-style, no HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_factual_edit_creates_kb_pending(db_session):
    payload = {
        "type": "factual",
        "persona_field": None,
        "summary": "修正药名模式",
        "confidence": "high",
        "kb_category": "medication",
        "proposed_kb_rule": "硝苯地平而非氨氯地平用于该类高血压患者",
    }
    p1, p2 = _patch_llm(payload)
    with p1, p2:
        await process_edit_for_learning(
            db_session, TEST_DOCTOR_ID,
            "原 use 氨氯地平", "edited use 硝苯地平", edit_id=1,
        )
    await db_session.commit()

    rows = (await db_session.execute(
        select(KbPendingItem).where(KbPendingItem.doctor_id == TEST_DOCTOR_ID)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].category == "medication"
    assert "硝苯地平" in rows[0].proposed_rule


@pytest.mark.asyncio
async def test_duplicate_factual_edit_skipped(db_session):
    payload = {
        "type": "factual",
        "persona_field": None,
        "summary": "同一修正模式",
        "confidence": "high",
        "kb_category": "medication",
        "proposed_kb_rule": "硝苯地平而非氨氯地平 这是去重规则",
    }
    p1, p2 = _patch_llm(payload)
    with p1, p2:
        await process_edit_for_learning(db_session, TEST_DOCTOR_ID, "a", "b", edit_id=10)
        await process_edit_for_learning(db_session, TEST_DOCTOR_ID, "c", "d", edit_id=11)
    await db_session.commit()

    cnt = (await db_session.execute(
        select(func.count()).select_from(KbPendingItem).where(
            KbPendingItem.doctor_id == TEST_DOCTOR_ID,
            KbPendingItem.proposed_rule.contains("去重规则"),
        )
    )).scalar()
    assert cnt == 1


@pytest.mark.asyncio
async def test_style_edit_does_not_create_kb_pending(db_session):
    payload = {
        "type": "style",
        "persona_field": "closing",
        "summary": "删除祝福语",
        "confidence": "high",
        "kb_category": None,
        "proposed_kb_rule": "",
    }
    before = (await db_session.execute(
        select(func.count()).select_from(KbPendingItem).where(
            KbPendingItem.doctor_id == TEST_DOCTOR_ID
        )
    )).scalar()

    p1, p2 = _patch_llm(payload)
    with p1, p2:
        await process_edit_for_learning(db_session, TEST_DOCTOR_ID, "a ending 祝好", "a", edit_id=20)
    await db_session.commit()

    after = (await db_session.execute(
        select(func.count()).select_from(KbPendingItem).where(
            KbPendingItem.doctor_id == TEST_DOCTOR_ID
        )
    )).scalar()
    assert after == before  # no new rows


@pytest.mark.asyncio
async def test_context_specific_edit_does_not_create_kb_pending(db_session):
    payload = {
        "type": "context_specific",
        "persona_field": None,
        "summary": "针对特定患者",
        "confidence": "high",
        "kb_category": None,
        "proposed_kb_rule": "",
    }
    before = (await db_session.execute(
        select(func.count()).select_from(KbPendingItem).where(
            KbPendingItem.doctor_id == TEST_DOCTOR_ID
        )
    )).scalar()

    p1, p2 = _patch_llm(payload)
    with p1, p2:
        await process_edit_for_learning(db_session, TEST_DOCTOR_ID, "a", "a 个性化", edit_id=30)
    await db_session.commit()

    after = (await db_session.execute(
        select(func.count()).select_from(KbPendingItem).where(
            KbPendingItem.doctor_id == TEST_DOCTOR_ID
        )
    )).scalar()
    assert after == before  # no new rows


# ---------------------------------------------------------------------------
# Tests: HTTP endpoints (accept / reject)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accept_endpoint_writes_kb(db_session, async_client):
    """Create a pending row, POST accept, verify DoctorKnowledgeItem is created."""
    pending = KbPendingItem(
        doctor_id=TEST_DOCTOR_ID,
        category="medication",
        proposed_rule="硝苯地平 用于该类患者",
        summary="药名修正",
        evidence_summary="evidence here",
        confidence="high",
        pattern_hash="abc123_accept_test",
    )
    db_session.add(pending)
    await db_session.commit()
    await db_session.refresh(pending)
    pending_id = pending.id

    resp = await async_client.post(
        f"/api/manage/kb/pending/{pending_id}/accept",
        params={"doctor_id": TEST_DOCTOR_ID},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ok"
    assert "knowledge_item_id" in data

    # Verify DoctorKnowledgeItem was written
    kb = (await db_session.execute(
        select(DoctorKnowledgeItem).where(DoctorKnowledgeItem.id == data["knowledge_item_id"])
    )).scalar_one()
    assert kb.doctor_id == TEST_DOCTOR_ID
    assert kb.category == "medication"
    assert kb.seed_source == "edit_fact"

    # Verify pending row updated
    await db_session.refresh(pending)
    assert pending.status == "accepted"
    assert pending.accepted_knowledge_item_id == kb.id


@pytest.mark.asyncio
async def test_reject_endpoint_sets_status(db_session, async_client):
    """Create a pending row, POST reject, verify status is 'rejected'."""
    pending = KbPendingItem(
        doctor_id=TEST_DOCTOR_ID,
        category="diagnosis",
        proposed_rule="排查颅内出血 用于头痛患者",
        summary="诊断修正",
        evidence_summary="evidence",
        confidence="medium",
        pattern_hash="def456_reject_test",
    )
    db_session.add(pending)
    await db_session.commit()
    await db_session.refresh(pending)
    pending_id = pending.id

    resp = await async_client.post(
        f"/api/manage/kb/pending/{pending_id}/reject",
        params={"doctor_id": TEST_DOCTOR_ID},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"

    await db_session.refresh(pending)
    assert pending.status == "rejected"
