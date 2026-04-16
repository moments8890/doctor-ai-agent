"""Unit tests for voice→rule extraction helper (mocks the LLM)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from channels.web.doctor_dashboard.knowledge_handlers import (
    VoiceExtractLLMResult,
    extract_rule_from_transcript,
)
from db.models.doctor import KnowledgeCategory


@pytest.mark.asyncio
async def test_extract_returns_candidate_on_clean_transcript():
    fake_llm_result = VoiceExtractLLMResult(
        content="术后第二周关注记忆变化",
        category=KnowledgeCategory.followup,
        error=None,
    )
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=fake_llm_result),
    ):
        result = await extract_rule_from_transcript(
            transcript="前交通动脉瘤术后第二周要关注记忆问题",
            specialty="神经外科",
        )
    assert result.error is None
    assert result.candidate is not None
    assert result.candidate.content == "术后第二周关注记忆变化"
    assert result.candidate.category == KnowledgeCategory.followup


@pytest.mark.asyncio
async def test_extract_propagates_no_rule_error():
    fake = VoiceExtractLLMResult(content=None, category=None, error="no_rule_found")
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=fake),
    ):
        result = await extract_rule_from_transcript(transcript="一段闲聊", specialty="")
    assert result.error == "no_rule_found"
    assert result.candidate is None


@pytest.mark.asyncio
async def test_extract_propagates_multi_rule_error():
    fake = VoiceExtractLLMResult(content=None, category=None, error="multi_rule_detected")
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=fake),
    ):
        result = await extract_rule_from_transcript(transcript="两条规则", specialty="")
    assert result.error == "multi_rule_detected"


@pytest.mark.asyncio
async def test_extract_handles_empty_transcript():
    # Empty transcript bypasses LLM and returns audio_unclear sentinel
    result = await extract_rule_from_transcript(transcript="", specialty="")
    assert result.error == "audio_unclear"
    assert result.candidate is None
