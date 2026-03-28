"""Tests for knowledge usage tracking (Task 4 — Knowledge Foundation)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401  — register all models
from domain.knowledge.knowledge_crud import save_knowledge_item
from domain.knowledge.usage_tracking import (
    get_knowledge_stats,
    get_recent_activity,
    log_citations,
)


@pytest_asyncio.fixture
async def async_session():
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_log_citations_stores_records(async_session):
    # First create a KB item to reference
    item = await save_knowledge_item(async_session, "doc_1", "test rule")

    count = await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[item.id],
        usage_context="diagnosis",
        patient_id="pat_1",
        record_id=10,
    )
    assert count == 1

    stats = await get_knowledge_stats(async_session, "doc_1")
    assert len(stats) >= 1
    assert stats[0]["knowledge_item_id"] == item.id
    assert stats[0]["total_count"] >= 1


@pytest.mark.asyncio
async def test_log_citations_empty_list(async_session):
    count = await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[],
        usage_context="diagnosis",
    )
    assert count == 0


@pytest.mark.asyncio
async def test_get_recent_activity(async_session):
    item = await save_knowledge_item(async_session, "doc_1", "another rule")

    await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[item.id],
        usage_context="followup",
        patient_id="pat_2",
    )
    activity = await get_recent_activity(async_session, "doc_1", limit=10)
    assert len(activity) >= 1
    assert activity[0]["usage_context"] == "followup"
    assert activity[0]["patient_id"] == "pat_2"
    assert activity[0]["knowledge_item_id"] == item.id


@pytest.mark.asyncio
async def test_log_citations_increments_reference_count(async_session):
    """Verify that logging citations increments the KB item's reference_count."""
    item = await save_knowledge_item(async_session, "doc_1", "ref count rule")
    assert item.reference_count == 0

    await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[item.id],
        usage_context="chat",
    )
    await async_session.refresh(item)
    assert item.reference_count == 1

    # Log again — should increment to 2
    await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[item.id],
        usage_context="diagnosis",
    )
    await async_session.refresh(item)
    assert item.reference_count == 2


@pytest.mark.asyncio
async def test_log_citations_multiple_ids(async_session):
    """Logging multiple KB IDs in one call creates one entry per ID."""
    item1 = await save_knowledge_item(async_session, "doc_1", "rule alpha")
    item2 = await save_knowledge_item(async_session, "doc_1", "rule beta")

    count = await log_citations(
        session=async_session,
        doctor_id="doc_1",
        cited_kb_ids=[item1.id, item2.id],
        usage_context="interview",
    )
    assert count == 2

    activity = await get_recent_activity(async_session, "doc_1", limit=10)
    assert len(activity) == 2

    stats = await get_knowledge_stats(async_session, "doc_1")
    assert len(stats) == 2
