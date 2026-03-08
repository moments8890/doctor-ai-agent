"""
Tests for services/intent.py — LLM call is mocked.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.ai.intent import detect_intent, Intent, IntentResult


def _make_completion(json_dict: dict):
    """Build a minimal fake OpenAI completion response."""
    msg = MagicMock()
    msg.content = json.dumps(json_dict, ensure_ascii=False)
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture
def mock_llm(monkeypatch):
    """Force LLM path and patch AsyncOpenAI so no real HTTP call is made."""
    monkeypatch.setenv("INTENT_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-tests")
    mock_client = AsyncMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create

    with patch("services.ai.intent.AsyncOpenAI", return_value=mock_client):
        yield mock_create


# ---------------------------------------------------------------------------
# Intent routing
# ---------------------------------------------------------------------------


async def test_detect_create_patient(mock_llm):
    mock_llm.return_value = _make_completion(
        {"intent": "create_patient", "patient_name": "李明", "gender": "男", "age": 45}
    )
    result = await detect_intent("帮我建个新患者，李明，45岁男性")
    assert result.intent == Intent.create_patient
    assert result.patient_name == "李明"
    assert result.gender == "男"
    assert result.age == 45


async def test_detect_add_record(mock_llm):
    mock_llm.return_value = _make_completion(
        {"intent": "add_record", "patient_name": "李明", "gender": None, "age": None}
    )
    result = await detect_intent("李明今天头痛，诊断为紧张性头痛，给予布洛芬治疗")
    assert result.intent == Intent.add_record
    assert result.patient_name == "李明"


async def test_detect_query_records(mock_llm):
    mock_llm.return_value = _make_completion(
        {"intent": "query_records", "patient_name": "张三", "gender": None, "age": None}
    )
    result = await detect_intent("查一下张三的历史记录")
    assert result.intent == Intent.query_records
    assert result.patient_name == "张三"


async def test_detect_unknown(mock_llm):
    mock_llm.return_value = _make_completion(
        {"intent": "unknown", "patient_name": None, "gender": None, "age": None}
    )
    result = await detect_intent("今天天气真好")
    assert result.intent == Intent.unknown


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------


async def test_detect_patient_name_is_none_when_absent(mock_llm):
    mock_llm.return_value = _make_completion(
        {"intent": "add_record", "patient_name": None, "gender": None, "age": None}
    )
    result = await detect_intent("患者头痛两天")
    assert result.patient_name is None


async def test_detect_age_can_be_none(mock_llm):
    mock_llm.return_value = _make_completion(
        {"intent": "create_patient", "patient_name": "王五", "gender": "女", "age": None}
    )
    result = await detect_intent("新患者王五，女性")
    assert result.age is None


# ---------------------------------------------------------------------------
# LLM call parameters
# ---------------------------------------------------------------------------


async def test_detect_intent_uses_correct_llm_params(mock_llm):
    mock_llm.return_value = _make_completion(
        {"intent": "unknown", "patient_name": None, "gender": None, "age": None}
    )
    await detect_intent("test message")
    call_kwargs = mock_llm.call_args.kwargs
    assert call_kwargs["max_tokens"] == 200
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["response_format"] == {"type": "json_object"}
