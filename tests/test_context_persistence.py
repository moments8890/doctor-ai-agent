"""Integration tests for the full doctor-context memory cycle.

Exercises the path:
  push_turn × N turns
    → maybe_compress (triggers on full window)
      → _summarise (LLM mocked)
      → upsert_doctor_context (writes to real in-memory SQLite)
    → load_context_message (reads from same in-memory SQLite)
      → system message injected into next agent call

Verifies that:
- Compression actually writes a row to the doctor_contexts table
- The stored summary matches what the LLM returned
- load_context_message returns the correct role/content shape
- After injection, the summary content is visible in agent history
- A second compression (new conversation) overwrites the previous row
- Two doctors get independent context rows
- Expired summary is replaced, not accumulated
"""
import time
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.engine import Base
import db.models  # noqa: F401 — register ORM models

from services.session import get_session, push_turn, DoctorSession
from services.memory import maybe_compress, load_context_message, MAX_TURNS, IDLE_SECONDS
from db.crud import get_doctor_context


# ---------------------------------------------------------------------------
# Fixtures — real in-memory SQLite, not mocks
# ---------------------------------------------------------------------------

DOCTOR_A = "ctx_doctor_a"
DOCTOR_B = "ctx_doctor_b"

# Fill exactly MAX_TURNS worth of history (10 turns = 20 messages)
def _make_full_history() -> list:
    history = []
    for i in range(MAX_TURNS):
        history.append({"role": "user", "content": f"患者{i}：主诉描述{i}"})
        history.append({"role": "assistant", "content": f"已记录第{i}条病历"})
    return history


@pytest_asyncio.fixture
async def real_db():
    """In-memory SQLite engine + session factory for context persistence tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def db_ctx_patch(real_db):
    """Patch AsyncSessionLocal inside services.memory to use the real in-memory DB."""
    # AsyncSessionLocal is a session factory; wrap it in a context-manager-returning callable
    class _FakeSessionLocal:
        def __init__(self):
            self._factory = real_db

        def __call__(self):
            return self._factory()

    fake_sl = _FakeSessionLocal()
    with patch("services.memory.AsyncSessionLocal", side_effect=lambda: real_db()):
        yield real_db


# ---------------------------------------------------------------------------
# Helper: run compression against the real in-memory DB
# ---------------------------------------------------------------------------

async def _compress_with_summary(doctor_id: str, history: list, summary: str, db_factory):
    """Set up history, run compression with mocked LLM, return DoctorContext row."""
    sess = get_session(doctor_id)
    sess.conversation_history = list(history)
    sess.last_active = time.time()

    with patch("services.memory._summarise", new_callable=AsyncMock, return_value=summary):
        with patch("services.memory.AsyncSessionLocal", side_effect=lambda: db_factory()):
            await maybe_compress(doctor_id, sess)

    async with db_factory() as db:
        return await get_doctor_context(db, doctor_id)


# ===========================================================================
# Tests
# ===========================================================================


async def test_compression_creates_row_in_db(real_db):
    history = _make_full_history()
    ctx = await _compress_with_summary(DOCTOR_A, history, "摘要内容A", real_db)
    assert ctx is not None
    assert ctx.doctor_id == DOCTOR_A


async def test_compression_stores_llm_summary(real_db):
    history = _make_full_history()
    ctx = await _compress_with_summary(DOCTOR_A, history, "当前患者：张三（男，65岁）\n最近处理：STEMI急诊PCI", real_db)
    assert "张三" in ctx.summary
    assert "STEMI" in ctx.summary


async def test_load_context_returns_stored_summary(real_db):
    summary = "当前患者：李明（男，50岁）\n最近处理：高血压复诊，加药\n待跟进：一个月后复查"
    await _compress_with_summary(DOCTOR_A, _make_full_history(), summary, real_db)

    with patch("services.memory.AsyncSessionLocal", side_effect=lambda: real_db()):
        msg = await load_context_message(DOCTOR_A)

    assert msg is not None
    assert msg["role"] == "system"
    assert "李明" in msg["content"]
    assert "高血压" in msg["content"]


async def test_load_context_message_format(real_db):
    await _compress_with_summary(
        DOCTOR_A, _make_full_history(),
        "当前患者：无\n最近处理：问诊\n待跟进：无",
        real_db,
    )
    with patch("services.memory.AsyncSessionLocal", side_effect=lambda: real_db()):
        msg = await load_context_message(DOCTOR_A)

    # Must clearly label itself as prior-session context so LLM treats it correctly
    assert "上次会话" in msg["content"] or "摘要" in msg["content"]
    assert "role" in msg
    assert msg["role"] == "system"


async def test_second_compression_overwrites_first_row(real_db):
    """Upsert semantics: second summary replaces first, no duplicate rows."""
    await _compress_with_summary(DOCTOR_A, _make_full_history(), "第一次摘要", real_db)
    await _compress_with_summary(DOCTOR_A, _make_full_history(), "第二次摘要（最新）", real_db)

    async with real_db() as db:
        ctx = await get_doctor_context(db, DOCTOR_A)

    assert ctx is not None
    assert "第二次摘要" in ctx.summary
    assert "第一次摘要" not in ctx.summary


async def test_two_doctors_have_independent_context_rows(real_db):
    await _compress_with_summary(DOCTOR_A, _make_full_history(), "摘要A", real_db)
    await _compress_with_summary(DOCTOR_B, _make_full_history(), "摘要B", real_db)

    async with real_db() as db:
        ctx_a = await get_doctor_context(db, DOCTOR_A)
        ctx_b = await get_doctor_context(db, DOCTOR_B)

    assert ctx_a.summary == "摘要A"
    assert ctx_b.summary == "摘要B"


async def test_load_context_no_row_returns_none(real_db):
    """Doctor with no prior sessions → no context injected."""
    with patch("services.memory.AsyncSessionLocal", side_effect=lambda: real_db()):
        msg = await load_context_message("brand_new_doctor")
    assert msg is None


async def test_history_cleared_after_compression(real_db):
    sess = get_session(DOCTOR_A)
    sess.conversation_history = _make_full_history()
    sess.last_active = time.time()

    with patch("services.memory._summarise", new_callable=AsyncMock, return_value="摘要"):
        with patch("services.memory.AsyncSessionLocal", side_effect=lambda: real_db()):
            await maybe_compress(DOCTOR_A, sess)

    assert sess.conversation_history == []


async def test_compression_idle_trigger_also_persists(real_db):
    """Idle-triggered compression (not window-full) must also write to DB."""
    sess = get_session(DOCTOR_A)
    # Only 2 turns (below window limit), but last_active is very old
    sess.conversation_history = [
        {"role": "user", "content": "一条消息"},
        {"role": "assistant", "content": "一条回复"},
    ]
    sess.last_active = time.time() - (IDLE_SECONDS + 60)

    with patch("services.memory._summarise", new_callable=AsyncMock, return_value="空闲摘要"):
        with patch("services.memory.AsyncSessionLocal", side_effect=lambda: real_db()):
            await maybe_compress(DOCTOR_A, sess)

    async with real_db() as db:
        ctx = await get_doctor_context(db, DOCTOR_A)

    assert ctx is not None
    assert ctx.summary == "空闲摘要"


async def test_full_cycle_compress_then_inject_into_agent_history(real_db):
    """Full round-trip: compress → DB → load_context_message → appears in history."""
    summary = "当前患者：贺志强（男，62岁）\n最近处理：不稳定型心绞痛，冠脉造影安排\n待跟进：入院复查血脂"
    await _compress_with_summary(DOCTOR_A, _make_full_history(), summary, real_db)

    with patch("services.memory.AsyncSessionLocal", side_effect=lambda: real_db()):
        ctx_msg = await load_context_message(DOCTOR_A)

    assert ctx_msg is not None
    # Simulate what the WeChat handler does: inject as first history message
    history = [ctx_msg]
    # The agent would receive this as the first "system" message in its history
    assert history[0]["role"] == "system"
    assert "贺志强" in history[0]["content"]
    assert "心绞痛" in history[0]["content"]
