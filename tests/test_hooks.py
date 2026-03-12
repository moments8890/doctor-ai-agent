"""Tests for services.hooks — lightweight hook mechanism."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.hooks import (
    HookStage,
    clear_hooks,
    emit,
    emit_background,
    list_hooks,
    register_hook,
    unregister_hook,
)


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Ensure hooks are cleared before and after every test."""
    clear_hooks()
    yield
    clear_hooks()


# ---------- register / unregister / list ----------


def test_register_and_list():
    cb = MagicMock()
    register_hook(HookStage.POST_CLASSIFY, cb)
    assert list_hooks(HookStage.POST_CLASSIFY) == {"post_classify": 1}


def test_register_multiple_stages():
    cb = MagicMock()
    register_hook(HookStage.POST_CLASSIFY, cb)
    register_hook(HookStage.POST_GATE, cb)
    info = list_hooks()
    assert info["post_classify"] == 1
    assert info["post_gate"] == 1
    assert info["post_extract"] == 0


def test_unregister():
    cb = MagicMock()
    register_hook(HookStage.POST_CLASSIFY, cb)
    assert unregister_hook(HookStage.POST_CLASSIFY, cb) is True
    assert list_hooks(HookStage.POST_CLASSIFY) == {"post_classify": 0}


def test_unregister_nonexistent():
    cb = MagicMock()
    assert unregister_hook(HookStage.POST_CLASSIFY, cb) is False


def test_clear_single_stage():
    cb = MagicMock()
    register_hook(HookStage.POST_CLASSIFY, cb)
    register_hook(HookStage.POST_GATE, cb)
    clear_hooks(HookStage.POST_CLASSIFY)
    assert list_hooks(HookStage.POST_CLASSIFY) == {"post_classify": 0}
    assert list_hooks(HookStage.POST_GATE) == {"post_gate": 1}


def test_clear_all():
    cb = MagicMock()
    for stage in HookStage:
        register_hook(stage, cb)
    clear_hooks()
    for stage in HookStage:
        assert list_hooks(stage) == {stage.value: 0}


# ---------- priority ordering ----------


@pytest.mark.asyncio
async def test_priority_ordering():
    order: list[int] = []

    def low(_ctx):
        order.append(200)

    def high(_ctx):
        order.append(10)

    def mid(_ctx):
        order.append(100)

    register_hook(HookStage.POST_CLASSIFY, low, priority=200)
    register_hook(HookStage.POST_CLASSIFY, high, priority=10)
    register_hook(HookStage.POST_CLASSIFY, mid, priority=100)

    await emit(HookStage.POST_CLASSIFY, {})
    assert order == [10, 100, 200]


# ---------- sync callback emit ----------


@pytest.mark.asyncio
async def test_emit_sync_callback():
    cb = MagicMock()
    register_hook(HookStage.POST_GATE, cb, priority=50)
    ctx = {"intent": "add_record", "doctor_id": "d1"}
    await emit(HookStage.POST_GATE, ctx)
    cb.assert_called_once_with(ctx)


# ---------- async callback emit ----------


@pytest.mark.asyncio
async def test_emit_async_callback():
    cb = AsyncMock()
    register_hook(HookStage.POST_EXTRACT, cb)
    ctx = {"entities": {"name": "张三"}}
    await emit(HookStage.POST_EXTRACT, ctx)
    cb.assert_awaited_once_with(ctx)


# ---------- mixed sync + async ----------


@pytest.mark.asyncio
async def test_emit_mixed_callbacks():
    sync_cb = MagicMock()
    async_cb = AsyncMock()
    register_hook(HookStage.PRE_REPLY, sync_cb, priority=10)
    register_hook(HookStage.PRE_REPLY, async_cb, priority=20)
    ctx = {"reply": "ok"}
    await emit(HookStage.PRE_REPLY, ctx)
    sync_cb.assert_called_once_with(ctx)
    async_cb.assert_awaited_once_with(ctx)


# ---------- error isolation ----------


@pytest.mark.asyncio
async def test_emit_error_isolation():
    """A failing callback must not prevent subsequent callbacks from running."""
    called = []

    def exploder(_ctx):
        raise RuntimeError("boom")

    def survivor(ctx):
        called.append(ctx["key"])

    register_hook(HookStage.POST_CLASSIFY, exploder, priority=1)
    register_hook(HookStage.POST_CLASSIFY, survivor, priority=2)

    await emit(HookStage.POST_CLASSIFY, {"key": "alive"})
    assert called == ["alive"]


@pytest.mark.asyncio
async def test_emit_async_error_isolation():
    """Async callback error must not prevent subsequent callbacks."""
    called = []

    async def exploder(_ctx):
        raise ValueError("async boom")

    async def survivor(ctx):
        called.append(ctx["key"])

    register_hook(HookStage.POST_GATE, exploder, priority=1)
    register_hook(HookStage.POST_GATE, survivor, priority=2)

    await emit(HookStage.POST_GATE, {"key": "ok"})
    assert called == ["ok"]


# ---------- emit on empty stage ----------


@pytest.mark.asyncio
async def test_emit_no_hooks():
    """Emitting on a stage with no hooks should be a no-op."""
    await emit(HookStage.POST_BIND, {"data": 1})  # should not raise


# ---------- emit_background ----------


@pytest.mark.asyncio
async def test_emit_background():
    cb = AsyncMock()
    register_hook(HookStage.PRE_REPLY, cb)
    await emit_background(HookStage.PRE_REPLY, {"reply": "hi"})
    # Give the background task a moment to complete.
    await asyncio.sleep(0.05)
    cb.assert_awaited_once_with({"reply": "hi"})


@pytest.mark.asyncio
async def test_emit_background_no_hooks():
    """Background emit on empty stage is a no-op."""
    await emit_background(HookStage.POST_PLAN, {})


# ---------- HookStage enum ----------


def test_hook_stage_values():
    assert HookStage.POST_CLASSIFY.value == "post_classify"
    assert HookStage.PRE_REPLY.value == "pre_reply"
    assert len(HookStage) == 6
