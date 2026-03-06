"""Concurrency regression tests for per-doctor asyncio session locking.

Verifies that concurrent background tasks for the same doctor serialise
correctly and do not corrupt session state or create duplicate records.
"""
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from services.session import get_session, set_pending_create
from services.intent import Intent, IntentResult


DOCTOR = "openid_concurrency_test"


def _intent(intent: Intent, reply: str = "ok") -> IntentResult:
    return IntentResult(intent=intent, chat_reply=reply)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_send_mock():
    """Return an AsyncMock for _send_customer_service_msg that is a no-op."""
    return AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Test 1: Two concurrent _handle_intent_bg calls produce exactly 2 turns
# ---------------------------------------------------------------------------


async def test_concurrent_intent_bg_no_history_corruption():
    """Two concurrent _handle_intent_bg tasks must each add exactly one turn.

    Without the lock, both tasks could read the same (empty) history,
    call the LLM concurrently, and then both push their turn — but because
    push_turn appends directly the list invariably ends up with 4 entries
    (2 user + 2 assistant). That is fine for correctness but the real risk is
    that a slow LLM could lose a turn when the history snapshot is stale.

    With the lock the tasks serialise: task-2 waits for task-1 to finish
    push_turn before it starts, so it always sees the updated history.
    """
    import routers.wechat as wechat

    call_order: list[int] = []

    async def slow_handle_intent(text: str, doctor_id: str, history=None):
        # Simulate LLM latency; yields so the event loop can schedule task 2
        await asyncio.sleep(0.01)
        call_order.append(len(history))
        return f"reply-{text}"

    with (
        patch("routers.wechat._handle_intent", new=slow_handle_intent),
        patch("routers.wechat._send_customer_service_msg", new=_make_send_mock()),
        patch("routers.wechat.maybe_compress", new=AsyncMock()),
        patch("routers.wechat.load_context_message", new=AsyncMock(return_value=None)),
        patch("routers.wechat.hydrate_session_state", new=AsyncMock()),
    ):
        t1 = asyncio.create_task(wechat._handle_intent_bg("msg1", DOCTOR))
        t2 = asyncio.create_task(wechat._handle_intent_bg("msg2", DOCTOR))
        await asyncio.gather(t1, t2)

    sess = get_session(DOCTOR)
    history = sess.conversation_history

    # Exactly 4 entries: 2 user + 2 assistant
    assert len(history) == 4, f"expected 4 history entries, got {len(history)}: {history}"

    # Because tasks serialised, task-2's _handle_intent saw task-1's turn in history
    # call_order[0] = history length seen by first task (0 = fresh session)
    # call_order[1] = history length seen by second task (2 = after first push)
    assert call_order[0] == 0, f"first task should see empty history, got {call_order[0]}"
    assert call_order[1] == 2, f"second task should see 2-entry history, got {call_order[1]}"


# ---------------------------------------------------------------------------
# Test 2: Concurrent pending-create tasks don't create duplicate patients
# ---------------------------------------------------------------------------


async def test_concurrent_pending_create_no_duplicate(session_factory):
    """Only one of two racing pending-create handlers should win the pending state."""
    import routers.wechat as wechat

    # Pre-set pending create state
    set_pending_create(DOCTOR, "张三")

    created_names: list[str] = []

    async def fake_create_patient(session, doctor_id, name, gender, age):
        created_names.append(name)
        return type("FakePatient", (), {"id": 1, "name": name})()

    with (
        patch("routers.wechat.AsyncSessionLocal", session_factory),
        patch("routers.wechat._send_customer_service_msg", new=_make_send_mock()),
        patch("routers.wechat.maybe_compress", new=AsyncMock()),
        patch("routers.wechat.load_context_message", new=AsyncMock(return_value=None)),
        patch("routers.wechat.hydrate_session_state", new=AsyncMock()),
        patch("routers.wechat._handle_intent", new=AsyncMock(return_value="intent reply")),
        patch("routers.wechat.create_patient", new=AsyncMock(side_effect=fake_create_patient)),
        patch("routers.wechat.find_patient_by_name", new=AsyncMock(return_value=None)),
    ):
        # Two concurrent tasks both responding to the pending-create prompt
        t1 = asyncio.create_task(wechat._handle_intent_bg("男，30岁", DOCTOR))
        t2 = asyncio.create_task(wechat._handle_intent_bg("男，30岁", DOCTOR))
        await asyncio.gather(t1, t2)

    # With per-doctor lock, the second task runs after the first has already
    # cleared pending_create_name, so it falls through to _handle_intent.
    # The first task calls create_patient once; the second does NOT.
    assert len(created_names) <= 1, (
        f"Expected at most 1 patient created, got {len(created_names)}: {created_names}"
    )
