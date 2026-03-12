"""Tests for services.knowledge.knowledge_cache — shared knowledge-context caching."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.knowledge.knowledge_cache import (
    KB_CONTEXT_CACHE,
    KB_CONTEXT_TTL,
    get_kb_lock,
    invalidate_knowledge_cache,
    load_cached_knowledge_context,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure each test starts with a clean cache."""
    KB_CONTEXT_CACHE.clear()
    yield
    KB_CONTEXT_CACHE.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOCTOR = "doc_cache_test"
_QUERY = "胸痛患者处理流程"
_CTX = "【医生知识库（仅作背景约束）】\n1. 高危胸痛需先排除ACS"


def _mock_session_ctx():
    """Return a mock AsyncSessionLocal context manager."""
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_calls_underlying():
    """On first call (cache miss), the underlying load function is invoked."""
    ctx_mgr, session = _mock_session_ctx()
    with patch(
        "services.knowledge.knowledge_cache.AsyncSessionLocal",
        return_value=ctx_mgr,
    ), patch(
        "services.knowledge.knowledge_cache.load_knowledge_context_for_prompt",
        new_callable=AsyncMock,
        return_value=_CTX,
    ) as mock_load:
        result = await load_cached_knowledge_context(_DOCTOR, _QUERY)

    assert result == _CTX
    mock_load.assert_awaited_once_with(session, _DOCTOR, _QUERY)
    # Verify value is now cached
    assert _DOCTOR in KB_CONTEXT_CACHE
    cached_ctx, _expiry = KB_CONTEXT_CACHE[_DOCTOR]
    assert cached_ctx == _CTX


@pytest.mark.asyncio
async def test_cache_hit_within_ttl():
    """Within TTL, the cached value is returned without calling the DB."""
    # Pre-populate cache with a future expiry
    KB_CONTEXT_CACHE[_DOCTOR] = (_CTX, time.perf_counter() + 9999)

    with patch(
        "services.knowledge.knowledge_cache.load_knowledge_context_for_prompt",
        new_callable=AsyncMock,
    ) as mock_load:
        result = await load_cached_knowledge_context(_DOCTOR, _QUERY)

    assert result == _CTX
    mock_load.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_expired_refetches():
    """After TTL expires, the function re-fetches from the DB."""
    # Pre-populate with an already-expired entry
    KB_CONTEXT_CACHE[_DOCTOR] = ("old context", time.perf_counter() - 1)

    new_ctx = "【医生知识库（仅作背景约束）】\n1. 更新后的知识"
    ctx_mgr, session = _mock_session_ctx()
    with patch(
        "services.knowledge.knowledge_cache.AsyncSessionLocal",
        return_value=ctx_mgr,
    ), patch(
        "services.knowledge.knowledge_cache.load_knowledge_context_for_prompt",
        new_callable=AsyncMock,
        return_value=new_ctx,
    ) as mock_load:
        result = await load_cached_knowledge_context(_DOCTOR, _QUERY)

    assert result == new_ctx
    mock_load.assert_awaited_once()
    cached_ctx, _expiry = KB_CONTEXT_CACHE[_DOCTOR]
    assert cached_ctx == new_ctx


@pytest.mark.asyncio
async def test_error_returns_empty_string():
    """When the underlying function raises, return '' gracefully."""
    ctx_mgr, _session = _mock_session_ctx()
    with patch(
        "services.knowledge.knowledge_cache.AsyncSessionLocal",
        return_value=ctx_mgr,
    ), patch(
        "services.knowledge.knowledge_cache.load_knowledge_context_for_prompt",
        new_callable=AsyncMock,
        side_effect=RuntimeError("DB connection lost"),
    ) as mock_load:
        result = await load_cached_knowledge_context(_DOCTOR, _QUERY)

    assert result == ""
    mock_load.assert_awaited_once()


def test_invalidate_clears_entry():
    """invalidate_knowledge_cache removes the cached entry for a doctor."""
    KB_CONTEXT_CACHE[_DOCTOR] = (_CTX, time.perf_counter() + 9999)
    KB_CONTEXT_CACHE["other_doc"] = ("other", time.perf_counter() + 9999)

    invalidate_knowledge_cache(_DOCTOR)

    assert _DOCTOR not in KB_CONTEXT_CACHE
    # Other doctor's cache is untouched
    assert "other_doc" in KB_CONTEXT_CACHE


def test_invalidate_nonexistent_is_noop():
    """Invalidating a doctor not in cache does not raise."""
    invalidate_knowledge_cache("nonexistent_doctor")  # should not raise


def test_get_kb_lock_returns_same_lock():
    """get_kb_lock returns the same asyncio.Lock for the same doctor_id."""
    lock1 = get_kb_lock("doc_a")
    lock2 = get_kb_lock("doc_a")
    lock3 = get_kb_lock("doc_b")
    assert lock1 is lock2
    assert lock1 is not lock3
