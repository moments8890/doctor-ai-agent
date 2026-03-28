"""Tests for knowledge category passthrough (Task 1 — Knowledge Foundation)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401  — register all models
from domain.knowledge.knowledge_crud import save_knowledge_item
from db.models.doctor import KnowledgeCategory


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
async def test_save_knowledge_item_respects_category(async_session):
    item = await save_knowledge_item(
        async_session, "doc_1", "术后头痛先排除再出血",
        source="doctor", confidence=1.0, category=KnowledgeCategory.diagnosis,
    )
    assert item is not None
    assert item.category == "diagnosis"


@pytest.mark.asyncio
async def test_save_knowledge_item_defaults_to_custom(async_session):
    item = await save_knowledge_item(
        async_session, "doc_1", "一般性知识条目",
        source="doctor", confidence=1.0,
    )
    assert item is not None
    assert item.category == "custom"
