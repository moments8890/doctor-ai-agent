"""Action hint dispatch — bypass ReAct agent for known intents."""
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("ROUTING_LLM", "deepseek")

from agent.actions import Action


@pytest.mark.asyncio
async def test_query_patient_empty_lists_all():
    """query_patient with label text → list all patients."""
    mock_patients = [
        {"id": 1, "name": "张三", "gender": "男", "year_of_birth": 1980},
        {"id": 2, "name": "李四", "gender": "女", "year_of_birth": 1990},
    ]
    with patch("agent.handle_turn._fetch_patients", new_callable=AsyncMock, return_value=mock_patients):
        from agent.handle_turn import _dispatch_action_hint
        reply = await _dispatch_action_hint(Action.query_patient, "查询患者", "dr_test", agent=None)

    assert "张三" in reply
    assert "李四" in reply


@pytest.mark.asyncio
async def test_query_patient_with_name_filters():
    """query_patient with name text → filter by substring."""
    mock_patients = [
        {"id": 1, "name": "张三", "gender": "男", "year_of_birth": 1980},
        {"id": 2, "name": "李四", "gender": "女", "year_of_birth": 1990},
    ]
    with patch("agent.handle_turn._fetch_patients", new_callable=AsyncMock, return_value=mock_patients):
        from agent.handle_turn import _dispatch_action_hint
        reply = await _dispatch_action_hint(Action.query_patient, "张三", "dr_test", agent=None)

    assert "张三" in reply
    assert "李四" not in reply


@pytest.mark.asyncio
async def test_daily_summary_calls_helpers():
    """daily_summary → calls _fetch_tasks + _fetch_recent_records."""
    with patch("agent.handle_turn._fetch_tasks", new_callable=AsyncMock, return_value=[]) as mock_tasks, \
         patch("agent.handle_turn._fetch_recent_records", new_callable=AsyncMock, return_value=[]) as mock_records:
        from agent.handle_turn import _dispatch_action_hint
        reply = await _dispatch_action_hint(Action.daily_summary, "今日摘要", "dr_test", agent=None)

    mock_tasks.assert_called_once_with("dr_test")
    mock_records.assert_called_once()
    assert isinstance(reply, str)


@pytest.mark.asyncio
async def test_create_record_returns_redirect_message():
    """create_record → returns redirect message to use interview mode."""
    from agent.handle_turn import _dispatch_action_hint
    reply = await _dispatch_action_hint(Action.create_record, "张三，男，45岁", "dr_test", agent=None)
    assert reply is not None
    assert "新增病历" in reply


@pytest.mark.asyncio
async def test_diagnosis_returns_none():
    """diagnosis (Phase 2) → returns None, falls through to normal agent."""
    from agent.handle_turn import _dispatch_action_hint
    reply = await _dispatch_action_hint(Action.diagnosis, "test", "dr_test", agent=None)
    assert reply is None


@pytest.mark.asyncio
async def test_handle_turn_uses_dispatch_when_hint_present():
    """handle_turn with action_hint skips agent, uses dispatch."""
    with patch("agent.handle_turn.get_or_create_agent", new_callable=AsyncMock) as mock_get_agent, \
         patch("agent.handle_turn.set_current_identity"), \
         patch("agent.handle_turn._try_fast_path", new_callable=AsyncMock, return_value=None), \
         patch("agent.handle_turn._dispatch_action_hint", new_callable=AsyncMock, return_value="患者列表...") as mock_dispatch, \
         patch("agent.handle_turn.archive_turns", new_callable=AsyncMock):
        mock_agent = MagicMock()
        mock_agent._add_turn = MagicMock()
        mock_get_agent.return_value = mock_agent

        from agent.handle_turn import handle_turn
        reply = await handle_turn("查询患者", "doctor", "dr_test", action_hint=Action.query_patient)

    assert reply == "患者列表..."
    mock_dispatch.assert_called_once()
    mock_agent.handle.assert_not_called()
