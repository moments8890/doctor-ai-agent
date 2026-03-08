"""Tests for services/wechat/patient_pipeline.py."""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.wechat.patient_pipeline import (
    has_emergency_keyword,
    handle_patient_message,
    _EMERGENCY_REPLY,
    _NON_TEXT_REPLY,
)


# ---------------------------------------------------------------------------
# has_emergency_keyword
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "我胸痛很厉害",
    "昏迷了叫救命",
    "大出血快急救",
    "呼吸困难",
    "意识丧失",
])
def test_emergency_keywords_detected(text):
    assert has_emergency_keyword(text)


@pytest.mark.parametrize("text", [
    "我最近有点头疼",
    "血压高怎么办",
    "感冒发烧要去医院吗",
    "",
])
def test_non_emergency_text(text):
    assert not has_emergency_keyword(text)


# ---------------------------------------------------------------------------
# handle_patient_message — emergency path (no LLM needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emergency_message_returns_emergency_reply():
    reply = await handle_patient_message("我胸痛得厉害", "test_open_id")
    assert "120" in reply
    assert reply == _EMERGENCY_REPLY


# ---------------------------------------------------------------------------
# handle_patient_message — LLM unavailable fallback (test env)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_when_llm_unavailable(monkeypatch):
    """In PYTEST_CURRENT_TEST env, _get_llm_client raises → fallback reply."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    reply = await handle_patient_message("感冒了怎么办", "test_open_id")
    assert reply  # returns a safe static message
    assert "120" in reply or "医院" in reply


# ---------------------------------------------------------------------------
# handle_patient_message — LLM success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_reply_returned():
    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "建议多休息，多喝水。"
    mock_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[mock_choice])
    )

    with patch(
        "services.wechat.patient_pipeline._get_llm_client",
        return_value=(mock_client, "test-model"),
    ):
        reply = await handle_patient_message("感冒发烧怎么办", "open_id")

    assert reply == "建议多休息，多喝水。"


@pytest.mark.asyncio
async def test_llm_exception_returns_fallback():
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("timeout"))

    with patch(
        "services.wechat.patient_pipeline._get_llm_client",
        return_value=(mock_client, "test-model"),
    ):
        reply = await handle_patient_message("感冒发烧怎么办", "open_id")

    assert reply  # safe fallback
    assert "120" in reply or "医院" in reply


@pytest.mark.asyncio
async def test_empty_llm_response_returns_default():
    mock_client = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = ""
    mock_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[mock_choice])
    )

    with patch(
        "services.wechat.patient_pipeline._get_llm_client",
        return_value=(mock_client, "test-model"),
    ):
        reply = await handle_patient_message("你好", "open_id")

    assert reply  # default message returned instead of empty string
