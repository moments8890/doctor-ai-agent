"""Tests for knowledge title/summary fields (Task 2 — Knowledge Foundation)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401  — register all models
from domain.knowledge.knowledge_crud import extract_title_from_text, save_knowledge_item


# ── Fixtures ──────────────────────────────────────────────────────

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


# ── extract_title_from_text ───────────────────────────────────────

def test_extract_title_first_line():
    text = "术后头痛红旗\n先排除再出血，再评估颅压"
    assert extract_title_from_text(text) == "术后头痛红旗"


def test_extract_title_truncates_long():
    text = "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的标题"
    result = extract_title_from_text(text)
    assert len(result) <= 21  # 20 + "…"
    assert result.endswith("…")


def test_extract_title_splits_on_colon_before_period():
    """Colon is a stronger delimiter — split on ： before 。"""
    text = "蛛网膜下腔出血（SAH）：突发剧烈头痛，伴恶心呕吐。Fisher分级。"
    assert extract_title_from_text(text) == "蛛网膜下腔出血（SAH）"


def test_extract_title_splits_on_period():
    text = "术后头痛红旗。先排除再出血"
    assert extract_title_from_text(text) == "术后头痛红旗"


def test_extract_title_empty():
    assert extract_title_from_text("") == ""


# ── save_knowledge_item with title ────────────────────────────────

@pytest.mark.asyncio
async def test_save_with_auto_title(async_session):
    item = await save_knowledge_item(
        async_session, "doc_1", "术后头痛红旗\n先排除再出血，再评估颅压",
    )
    assert item is not None
    assert item.title == "术后头痛红旗"


@pytest.mark.asyncio
async def test_save_with_explicit_title(async_session):
    item = await save_knowledge_item(
        async_session, "doc_1", "一些内容",
        title="自定义标题",
    )
    assert item is not None
    assert item.title == "自定义标题"


@pytest.mark.asyncio
async def test_save_with_summary(async_session):
    item = await save_knowledge_item(
        async_session, "doc_1", "术后复查注意事项",
        summary="术后复查的关键要点总结",
    )
    assert item is not None
    assert item.summary == "术后复查的关键要点总结"


@pytest.mark.asyncio
async def test_save_without_summary_defaults_none(async_session):
    item = await save_knowledge_item(
        async_session, "doc_1", "简单知识条目",
    )
    assert item is not None
    assert item.summary is None
