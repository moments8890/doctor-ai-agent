"""End-to-end test of the Plan-and-Act pipeline.

These tests exercise the full handle_turn -> route -> dispatch -> handler ->
response chain using mocks at the LLM call and DB query boundaries.
They do NOT require a running server or Ollama.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

_SRC = Path(__file__).parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("ROUTING_LLM", "deepseek")

from agent.types import IntentType, RoutingResult


# ---------------------------------------------------------------------------
# Override integration conftest's autouse fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def require_server():
    return

@pytest.fixture(scope="session", autouse=True)
def require_ollama():
    return

@pytest.fixture(autouse=True)
def clean_integration_db():
    yield


# ---------------------------------------------------------------------------
# Tests — handle_turn now returns HandlerResult
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_turn_query_record():
    """Doctor asks for patient records — routing → handler → compose → reply."""
    with patch("agent.router.structured_call", new_callable=AsyncMock) as mock_route, \
         patch("agent.handlers.query_record.resolve", new_callable=AsyncMock) as mock_resolve, \
         patch("agent.handlers.query_record._fetch_records", new_callable=AsyncMock) as mock_fetch, \
         patch("agent.handlers.query_record._compose_summary", new_callable=AsyncMock) as mock_compose:

        mock_route.return_value = RoutingResult(
            intent=IntentType.query_record, patient_name="张三"
        )
        mock_resolve.return_value = {"doctor_id": "test_doc", "patient_id": 1, "patient_name": "张三"}
        mock_fetch.return_value = [{"content": "头痛", "created_at": "2026-03-20"}]
        mock_compose.return_value = "张三最近就诊：头痛（3月20日）"

        from agent.handle_turn import handle_turn
        result = await handle_turn("查张三的病历", "doctor", "test_doc")

        assert "张三" in result.reply
        assert "头痛" in result.reply


@pytest.mark.asyncio
async def test_full_turn_with_deferred():
    """Doctor sends multi-intent — first handled, deferred acknowledged."""
    with patch("agent.router.structured_call", new_callable=AsyncMock) as mock_route, \
         patch("agent.handlers.query_record.resolve", new_callable=AsyncMock) as mock_resolve, \
         patch("agent.handlers.query_record._fetch_records", new_callable=AsyncMock) as mock_fetch, \
         patch("agent.handlers.query_record._compose_summary", new_callable=AsyncMock) as mock_compose:

        mock_route.return_value = RoutingResult(
            intent=IntentType.query_record, patient_name="张三", deferred="建个随访任务"
        )
        mock_resolve.return_value = {"doctor_id": "test_doc2", "patient_id": 1, "patient_name": "张三"}
        mock_fetch.return_value = [{"content": "头痛"}]
        mock_compose.return_value = "张三病历摘要"

        from agent.handle_turn import handle_turn
        result = await handle_turn("查张三病历然后建个随访", "doctor", "test_doc2")

        assert "随访" in result.reply


@pytest.mark.asyncio
async def test_full_turn_create_task():
    """Doctor creates a task — routing → handler → DB save → reply."""
    with patch("agent.router.structured_call", new_callable=AsyncMock) as mock_route, \
         patch("agent.handlers.create_task._resolve_and_save_task", new_callable=AsyncMock) as mock_save:

        mock_route.return_value = RoutingResult(
            intent=IntentType.create_task, patient_name="张三",
            params={"title": "复查血常规"},
        )
        mock_save.return_value = {"status": "ok", "task_id": 99, "title": "复查血常规"}

        from agent.handle_turn import handle_turn
        result = await handle_turn("给张三建个复查血常规的任务", "doctor", "test_doc3")

        assert "复查血常规" in result.reply
        assert "#99" in result.reply


@pytest.mark.asyncio
async def test_full_turn_general_fallback():
    """Chitchat — routing → general handler → reply."""
    with patch("agent.router.structured_call", new_callable=AsyncMock) as mock_route:
        mock_route.return_value = RoutingResult(intent=IntentType.general)

        from agent.handle_turn import handle_turn
        result = await handle_turn("今天天气怎么样", "doctor", "test_doc4")

        assert result.reply


@pytest.mark.asyncio
async def test_create_record_returns_session_id():
    """create_record handler returns session_id in data for frontend."""
    with patch("agent.router.structured_call", new_callable=AsyncMock) as mock_route, \
         patch("agent.handlers.create_record.resolve", new_callable=AsyncMock) as mock_resolve, \
         patch("agent.handlers.create_record.create_session", new_callable=AsyncMock) as mock_session, \
         patch("agent.handlers.create_record.interview_turn", new_callable=AsyncMock) as mock_turn:

        from unittest.mock import MagicMock
        mock_route.return_value = RoutingResult(
            intent=IntentType.create_record, patient_name="张三"
        )
        mock_resolve.return_value = {"doctor_id": "test_doc5", "patient_id": 1, "patient_name": "张三"}
        mock_interview = MagicMock()
        mock_interview.id = "sess-abc-123"
        mock_session.return_value = mock_interview
        mock_response = MagicMock()
        mock_response.reply = "收到，已记录。"
        mock_response.progress = {"filled": 2, "total": 14}
        mock_turn.return_value = mock_response

        from agent.handle_turn import handle_turn
        result = await handle_turn("创建患者张三，男45岁，头痛三天", "doctor", "test_doc5")

        assert result.reply
        assert result.data is not None
        assert result.data.get("session_id") == "sess-abc-123"
