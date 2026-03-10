"""Tests for services/memory.py — LLM and DB are mocked.

Verifies that:
- maybe_compress is a no-op when history is short or empty
- maybe_compress fires when the rolling window is full (≥ MAX_TURNS*2 messages)
- maybe_compress fires when the doctor has been idle for ≥ IDLE_SECONDS
- After compression the in-memory history is always cleared (even on LLM failure)
- The LLM summary is persisted to DB via upsert_doctor_context
- load_context_message returns None when no DB context exists
- load_context_message returns a properly formatted system message when context exists
- Two doctors' contexts are stored and loaded independently
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import services.ai.memory as memory_mod
from services.ai.memory import maybe_compress, load_context_message, MAX_TURNS, IDLE_SECONDS
from services.session import get_session, push_turn


DOCTOR_A = "mem_doctor_a"
DOCTOR_B = "mem_doctor_b"

# 1 turn = 2 messages (user + assistant)
FULL_HISTORY = [
    {"role": ("user" if i % 2 == 0 else "assistant"), "content": f"msg {i}"}
    for i in range(MAX_TURNS * 2)   # exactly 20 messages → window full
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_summarise():
    """Patch the internal _summarise coroutine so no real LLM is called."""
    with patch("services.ai.memory._summarise", new_callable=AsyncMock, return_value="摘要内容") as m:
        yield m


@pytest.fixture
def mock_upsert():
    """Patch upsert_doctor_context so no real DB write happens."""
    with patch("services.ai.memory.upsert_doctor_context", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture
def mock_db_session():
    """Patch AsyncSessionLocal and clear_conversation_turns so memory ops don't open a real DB."""
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=MagicMock())
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)
    with patch("services.ai.memory.AsyncSessionLocal", return_value=ctx_mgr), \
         patch("services.ai.memory.clear_conversation_turns", new_callable=AsyncMock):
        yield ctx_mgr


# ---------------------------------------------------------------------------
# maybe_compress — no-op cases
# ---------------------------------------------------------------------------


async def test_compress_no_op_when_history_empty(mock_summarise, mock_upsert):
    sess = get_session(DOCTOR_A)
    sess.conversation_history = []
    await maybe_compress(DOCTOR_A, sess)
    mock_summarise.assert_not_called()


async def test_compress_no_op_when_history_is_short(mock_summarise, mock_upsert):
    """History with fewer than MAX_TURNS*2 messages and no idle → no compress."""
    sess = get_session(DOCTOR_A)
    sess.conversation_history = FULL_HISTORY[:4]  # only 2 turns
    sess.last_active = time.time()
    await maybe_compress(DOCTOR_A, sess)
    mock_summarise.assert_not_called()


# ---------------------------------------------------------------------------
# maybe_compress — triggers on full window
# ---------------------------------------------------------------------------


async def test_compress_fires_when_window_is_full(mock_summarise, mock_upsert, mock_db_session):
    sess = get_session(DOCTOR_A)
    sess.conversation_history = list(FULL_HISTORY)
    sess.last_active = time.time()
    await maybe_compress(DOCTOR_A, sess)
    mock_summarise.assert_called_once()


async def test_compress_clears_history_after_full_window(mock_summarise, mock_upsert, mock_db_session):
    sess = get_session(DOCTOR_A)
    sess.conversation_history = list(FULL_HISTORY)
    sess.last_active = time.time()
    await maybe_compress(DOCTOR_A, sess)
    assert sess.conversation_history == []


async def test_compress_persists_summary_to_db(mock_summarise, mock_upsert, mock_db_session):
    sess = get_session(DOCTOR_A)
    sess.conversation_history = list(FULL_HISTORY)
    sess.last_active = time.time()
    await maybe_compress(DOCTOR_A, sess)
    mock_upsert.assert_called_once()
    # Second positional arg is doctor_id, third is summary
    call_args = mock_upsert.call_args
    assert call_args.args[1] == DOCTOR_A
    assert call_args.args[2] == "摘要内容"


# ---------------------------------------------------------------------------
# maybe_compress — triggers on idle timeout
# ---------------------------------------------------------------------------


async def test_compress_fires_when_idle(mock_summarise, mock_upsert, mock_db_session):
    sess = get_session(DOCTOR_A)
    sess.conversation_history = [{"role": "user", "content": "一条消息"},
                                  {"role": "assistant", "content": "回复"}]
    sess.last_active = time.time() - (IDLE_SECONDS + 60)  # 1 minute past idle threshold
    await maybe_compress(DOCTOR_A, sess)
    mock_summarise.assert_called_once()


async def test_compress_clears_history_when_idle(mock_summarise, mock_upsert, mock_db_session):
    sess = get_session(DOCTOR_A)
    sess.conversation_history = [{"role": "user", "content": "一条消息"},
                                  {"role": "assistant", "content": "回复"}]
    sess.last_active = time.time() - (IDLE_SECONDS + 60)
    await maybe_compress(DOCTOR_A, sess)
    assert sess.conversation_history == []


# ---------------------------------------------------------------------------
# maybe_compress — keeps history when compression fails (safe fallback)
# ---------------------------------------------------------------------------


async def test_compress_keeps_history_when_llm_fails(mock_upsert):
    with patch("services.ai.memory._summarise", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
        sess = get_session(DOCTOR_A)
        sess.conversation_history = list(FULL_HISTORY)
        sess.last_active = time.time()
        await maybe_compress(DOCTOR_A, sess)
    # History must be preserved on failure so the context is not lost
    assert sess.conversation_history == list(FULL_HISTORY)


# ---------------------------------------------------------------------------
# load_context_message
# ---------------------------------------------------------------------------


async def test_load_context_returns_none_when_no_db_row():
    with patch("services.ai.memory.get_doctor_context", new_callable=AsyncMock, return_value=None):
        with patch("services.ai.memory.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await load_context_message(DOCTOR_A)
    assert result is None


async def test_load_context_returns_none_when_summary_empty():
    ctx = MagicMock()
    ctx.summary = ""
    with patch("services.ai.memory.get_doctor_context", new_callable=AsyncMock, return_value=ctx):
        with patch("services.ai.memory.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await load_context_message(DOCTOR_A)
    assert result is None


async def test_load_context_returns_system_message_when_context_exists():
    ctx = MagicMock()
    ctx.summary = "当前患者：张三（男，65岁）\n最近处理：STEMI急诊PCI\n待跟进：复查肌钙蛋白"
    with patch("services.ai.memory.get_doctor_context", new_callable=AsyncMock, return_value=ctx):
        with patch("services.ai.memory.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await load_context_message(DOCTOR_A)
    assert result is not None
    assert result["role"] == "system"
    assert "张三" in result["content"]
    assert "STEMI" in result["content"]


async def test_load_context_message_format_contains_context_header():
    ctx = MagicMock()
    ctx.summary = "当前患者：李明\n最近处理：头痛\n待跟进：无"
    with patch("services.ai.memory.get_doctor_context", new_callable=AsyncMock, return_value=ctx):
        with patch("services.ai.memory.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await load_context_message(DOCTOR_A)
    # The injection must clearly label itself as prior-session context
    assert "上次会话" in result["content"] or "摘要" in result["content"]


# ---------------------------------------------------------------------------
# Doctor isolation — two doctors' contexts don't bleed into each other
# ---------------------------------------------------------------------------


async def test_two_doctors_compress_independently(mock_upsert, mock_db_session):
    """Filling doctor_a's window must not affect doctor_b's session."""
    with patch("services.ai.memory._summarise", new_callable=AsyncMock, return_value="摘要A"):
        sess_a = get_session(DOCTOR_A)
        sess_a.conversation_history = list(FULL_HISTORY)
        sess_a.last_active = time.time()
        await maybe_compress(DOCTOR_A, sess_a)

    sess_b = get_session(DOCTOR_B)
    # Doctor B's history was never set — should still be empty
    assert sess_b.conversation_history == []


async def test_load_context_returns_correct_doctor_summary():
    """load_context_message queries with the right doctor_id."""
    ctx_a = MagicMock()
    ctx_a.summary = "摘要属于医生A"

    async def fake_get_doctor_context(db, doctor_id):
        if doctor_id == DOCTOR_A:
            return ctx_a
        return None

    with patch("services.ai.memory.get_doctor_context", side_effect=fake_get_doctor_context):
        with patch("services.ai.memory.AsyncSessionLocal") as mock_sl:
            mock_sl.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_sl.return_value.__aexit__ = AsyncMock(return_value=False)
            result_a = await load_context_message(DOCTOR_A)
            result_b = await load_context_message(DOCTOR_B)

    assert result_a is not None
    assert "医生A" in result_a["content"]
    assert result_b is None
