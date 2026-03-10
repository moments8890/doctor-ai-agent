"""会话清理测试：验证空闲会话驱逐、锁定会话保护、异步任务引用清理及过时锁回收的逻辑。"""

from __future__ import annotations

import asyncio
import time

import pytest

import services.session as sess_mod
from services.session import get_session, get_session_lock, prune_inactive_sessions


def test_prune_inactive_sessions_evicts_idle_entries() -> None:
    idle = get_session("doc_idle")
    idle.last_active = time.time() - 7200
    sess_mod._loaded_from_db["doc_idle"] = time.monotonic()
    sess_mod._pending_turns["doc_idle"] = [{"role": "user", "content": "x"}]

    active = get_session("doc_active")
    active.last_active = time.time()

    summary = prune_inactive_sessions(max_idle_seconds=3600)

    assert summary["evicted_sessions"] == 1
    assert "doc_idle" not in sess_mod._sessions
    assert "doc_idle" not in sess_mod._loaded_from_db
    assert "doc_idle" not in sess_mod._pending_turns
    assert "doc_active" in sess_mod._sessions


@pytest.mark.asyncio
async def test_prune_inactive_sessions_preserves_locked_session() -> None:
    locked = get_session("doc_locked")
    locked.last_active = time.time() - 7200
    lock = get_session_lock("doc_locked")
    await lock.acquire()
    try:
        summary = prune_inactive_sessions(max_idle_seconds=3600)
    finally:
        lock.release()

    assert summary["evicted_sessions"] == 0
    assert "doc_locked" in sess_mod._sessions


@pytest.mark.asyncio
async def test_prune_inactive_sessions_clears_done_task_refs_and_stale_locks() -> None:
    # create done async tasks in both maps
    done_a = asyncio.create_task(asyncio.sleep(0))
    done_b = asyncio.create_task(asyncio.sleep(0))
    await done_a
    await done_b
    sess_mod._persist_tasks["doc_done_a"] = done_a
    sess_mod._persist_turn_tasks["doc_done_b"] = done_b

    # stale lock: no backing session
    sess_mod._locks["doc_stale_lock"] = asyncio.Lock()

    summary = prune_inactive_sessions(max_idle_seconds=3600)

    assert summary["cleared_persist_tasks"] == 1
    assert summary["cleared_turn_persist_tasks"] == 1
    assert summary["cleared_locks"] >= 1
    assert "doc_done_a" not in sess_mod._persist_tasks
    assert "doc_done_b" not in sess_mod._persist_turn_tasks
    assert "doc_stale_lock" not in sess_mod._locks


@pytest.mark.asyncio
async def test_prune_inactive_sessions_keeps_locked_stale_lock() -> None:
    # no backing session, but lock is currently held by a worker
    lock = asyncio.Lock()
    await lock.acquire()
    sess_mod._locks["doc_stale_locked"] = lock
    try:
        summary = prune_inactive_sessions(max_idle_seconds=3600)
        assert summary["cleared_locks"] == 0
        assert "doc_stale_locked" in sess_mod._locks
    finally:
        lock.release()
