"""Tests for services.ai.multi_intent — multi-intent message detection and splitting."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ai.multi_intent import (
    _might_be_multi_intent,
    _parse_segments,
    _resolve_provider,
    split_multi_intent,
)


# ---------- _might_be_multi_intent pre-check ----------


def test_might_be_multi_intent_xian_zai():
    """'先...再...' pattern with 4+ chars in each part triggers detection."""
    # Must be >= 20 chars (_MIN_LEN) with 4+ chars between 先 and 再, and 4+ after 再
    assert _might_be_multi_intent("先帮我记录张三头痛两天的病历再查询李四的历史病历") is True


def test_might_be_multi_intent_lingwai():
    """'...。另外...' pattern triggers detection."""
    # Must be >= 20 chars (_MIN_LEN)
    assert _might_be_multi_intent("帮我记录张三头痛两天。另外帮我查一下李四的病历") is True


def test_might_be_multi_intent_ranhou():
    """'...。然后...' with action verb triggers detection."""
    assert _might_be_multi_intent("先把张三的病历记一下。然后查询李四历史记录") is True


def test_might_be_multi_intent_short_text_rejected():
    """Short text should not trigger multi-intent."""
    assert _might_be_multi_intent("先查再记") is False


def test_might_be_multi_intent_single_intent():
    """Normal single intent should not trigger."""
    assert _might_be_multi_intent("记录张三头痛两天的病历") is False


# ---------- _parse_segments ----------


def test_parse_segments_valid_array():
    raw = '["记录张三头痛", "查询李四病历"]'
    result = _parse_segments(raw)
    assert result == ["记录张三头痛", "查询李四病历"]


def test_parse_segments_returns_none_for_single_element():
    raw = '["只有一个意图"]'
    result = _parse_segments(raw)
    assert result is None


def test_parse_segments_returns_none_for_no_json():
    raw = "这不是JSON"
    result = _parse_segments(raw)
    assert result is None


def test_parse_segments_filters_short_strings():
    raw = '["ab", "记录张三头痛", "查询李四病历"]'
    result = _parse_segments(raw)
    assert result == ["记录张三头痛", "查询李四病历"]


def test_parse_segments_handles_surrounding_text():
    raw = 'Sure, here are the segments:\n["记录张三头痛两天", "查询李四历史病历"]\nDone.'
    result = _parse_segments(raw)
    assert result == ["记录张三头痛两天", "查询李四历史病历"]


# ---------- _resolve_provider (two-arg signature) ----------


def test_resolve_provider_returns_dict_with_model_key(monkeypatch):
    """_resolve_provider applies env overrides to a provider config dict."""
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model")
    base = {"model": "default-model", "base_url": "http://localhost:11434/v1"}
    result = _resolve_provider("ollama", base)
    assert isinstance(result, dict)
    assert result["model"] == "custom-model"
    assert result["base_url"] == "http://localhost:11434/v1"


def test_resolve_provider_unknown_passes_through():
    """_resolve_provider for unknown provider returns a copy unchanged."""
    base = {"model": "some-model", "base_url": "http://example.com"}
    result = _resolve_provider("nonexistent_provider", base)
    assert result == base
    assert result is not base  # should be a copy


# ---------- split_multi_intent ----------


_LONG_MULTI = "先帮我记录张三头痛两天的病历再查询李四的历史病历"


async def test_split_multi_intent_returns_none_for_short_text():
    """Short single-intent messages should return None without calling LLM."""
    result = await split_multi_intent("记录张三头痛", doctor_id="d1")
    assert result is None


async def test_split_multi_intent_returns_none_when_provider_not_found(monkeypatch):
    """When the configured provider is not in the registry, return None."""
    monkeypatch.setenv("ROUTING_LLM", "nonexistent_provider_xyz")
    monkeypatch.delenv("STRUCTURING_LLM", raising=False)

    result = await split_multi_intent(_LONG_MULTI, doctor_id="d1")
    assert result is None


async def test_split_multi_intent_calls_llm_and_returns_segments(monkeypatch):
    """When multi-intent is detected, split_multi_intent should call LLM and parse segments."""
    monkeypatch.setenv("ROUTING_LLM", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.content = '["记录张三头痛两天", "查询李四历史病历"]'

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

    with patch("services.ai.agent._get_client", return_value=mock_client):
        result = await split_multi_intent(_LONG_MULTI, doctor_id="d1")

    assert result is not None
    assert len(result) == 2
    assert "张三" in result[0]
    assert "李四" in result[1]


async def test_split_multi_intent_returns_none_on_llm_error(monkeypatch):
    """LLM errors should be caught and return None."""
    monkeypatch.setenv("ROUTING_LLM", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    with patch("services.ai.agent._get_client", return_value=mock_client):
        result = await split_multi_intent(_LONG_MULTI, doctor_id="d1")

    assert result is None
