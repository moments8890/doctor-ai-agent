"""Tests for the teaching loop: edit detection, logging, and rule creation (Task 5)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.engine import Base
import db.models  # noqa: F401  — register all models
from domain.knowledge.teaching import (
    create_rule_from_edit,
    log_doctor_edit,
    should_prompt_teaching,
)


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


# ── should_prompt_teaching ────────────────────────────────────────


def test_ignores_whitespace_only_change():
    assert should_prompt_teaching("hello world", "hello  world") is False
    assert should_prompt_teaching("  hello\n", "hello") is False


def test_ignores_minor_edit():
    """Small diff (<10 chars changed) + high similarity (>80%) => not worth prompting."""
    original = "患者头痛，建议CT检查排除颅内出血"
    # Change only 2 characters — very minor
    edited = "患者头痛，建议CT检查排除颅内出血。"
    assert should_prompt_teaching(original, edited) is False


def test_triggers_on_significant_edit():
    original = "患者头痛，建议观察"
    edited = "患者头痛伴呕吐，需紧急CT检查排除颅内出血，同时监测生命体征"
    assert should_prompt_teaching(original, edited) is True


def test_triggers_on_completely_different_text():
    original = "建议口服止痛药"
    edited = "需要进行腰椎穿刺检查脑脊液压力，排除脑膜炎可能"
    assert should_prompt_teaching(original, edited) is True


def test_ignores_empty_strings():
    assert should_prompt_teaching("", "") is False
    assert should_prompt_teaching("   ", "  ") is False


# ── log_doctor_edit ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_doctor_edit_creates_record(async_session):
    edit_id = await log_doctor_edit(
        async_session,
        doctor_id="doc_test",
        entity_type="diagnosis",
        entity_id=42,
        original_text="original content",
        edited_text="edited content",
        field_name="content",
    )
    await async_session.commit()

    assert isinstance(edit_id, int)
    assert edit_id > 0

    # Verify record exists
    from sqlalchemy import select
    from db.models.doctor_edit import DoctorEdit

    row = (
        await async_session.execute(
            select(DoctorEdit).where(DoctorEdit.id == edit_id)
        )
    ).scalar_one_or_none()

    assert row is not None
    assert row.doctor_id == "doc_test"
    assert row.entity_type == "diagnosis"
    assert row.entity_id == 42
    assert row.original_text == "original content"
    assert row.edited_text == "edited content"
    assert row.field_name == "content"
    assert row.rule_created is False


@pytest.mark.asyncio
async def test_log_doctor_edit_without_field_name(async_session):
    edit_id = await log_doctor_edit(
        async_session,
        doctor_id="doc_test",
        entity_type="draft_reply",
        entity_id=99,
        original_text="some original",
        edited_text="some edited",
    )
    await async_session.commit()

    assert isinstance(edit_id, int)

    from sqlalchemy import select
    from db.models.doctor_edit import DoctorEdit

    row = (
        await async_session.execute(
            select(DoctorEdit).where(DoctorEdit.id == edit_id)
        )
    ).scalar_one_or_none()

    assert row is not None
    assert row.field_name is None


# ── create_rule_from_edit ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_rule_from_edit_saves_knowledge(async_session):
    # First create an edit
    edit_id = await log_doctor_edit(
        async_session,
        doctor_id="doc_teach",
        entity_type="diagnosis",
        entity_id=10,
        original_text="原始诊断",
        edited_text="修改后的诊断内容，包含更详细的信息",
    )
    await async_session.commit()

    # Create rule from that edit
    rule = await create_rule_from_edit(async_session, doctor_id="doc_teach", edit_id=edit_id)
    await async_session.commit()

    assert rule is not None
    assert rule.category == "custom"

    # Verify the edit record was updated
    from sqlalchemy import select
    from db.models.doctor_edit import DoctorEdit

    edit_row = (
        await async_session.execute(
            select(DoctorEdit).where(DoctorEdit.id == edit_id)
        )
    ).scalar_one_or_none()

    assert edit_row is not None
    assert edit_row.rule_created is True
    assert edit_row.rule_id == rule.id


@pytest.mark.asyncio
async def test_create_rule_from_edit_returns_none_for_missing(async_session):
    result = await create_rule_from_edit(async_session, doctor_id="doc_x", edit_id=99999)
    assert result is None


@pytest.mark.asyncio
async def test_create_rule_from_edit_returns_none_for_wrong_doctor(async_session):
    edit_id = await log_doctor_edit(
        async_session,
        doctor_id="doc_a",
        entity_type="diagnosis",
        entity_id=5,
        original_text="original",
        edited_text="edited",
    )
    await async_session.commit()

    # Try with a different doctor_id
    result = await create_rule_from_edit(async_session, doctor_id="doc_b", edit_id=edit_id)
    assert result is None
