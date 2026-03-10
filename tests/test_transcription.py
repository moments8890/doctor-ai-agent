"""语音转文字服务测试：验证医嘱录入与问诊对话两种模式下的提示词选择，以及 OpenAI API 回退路径的弹性包装调用。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services.ai.transcription import (
    _CONSULTATION_PROMPT,
    _MEDICAL_PROMPT,
    transcribe_audio,
)


async def test_transcribe_audio_uses_medical_prompt_by_default():
    """consultation_mode=False (default) passes _MEDICAL_PROMPT to _transcribe_sync."""
    with patch("services.ai.transcription._transcribe_sync", return_value="医嘱录入") as mock_sync:
        result = await transcribe_audio(b"audio", "test.wav")
    assert result == "医嘱录入"
    mock_sync.assert_called_once()
    _, prompt_arg = mock_sync.call_args[0]
    assert prompt_arg is _MEDICAL_PROMPT


async def test_transcribe_audio_uses_consultation_prompt_when_mode_true():
    """consultation_mode=True passes _CONSULTATION_PROMPT to _transcribe_sync."""
    with patch("services.ai.transcription._transcribe_sync", return_value="问诊内容") as mock_sync:
        result = await transcribe_audio(b"audio", "consult.wav", consultation_mode=True)
    assert result == "问诊内容"
    _, prompt_arg = mock_sync.call_args[0]
    assert prompt_arg is _CONSULTATION_PROMPT


async def test_transcribe_audio_passes_bytes_as_first_arg():
    """audio_bytes is the first positional arg to _transcribe_sync."""
    audio = b"raw_audio_data"
    with patch("services.ai.transcription._transcribe_sync", return_value="ok") as mock_sync:
        await transcribe_audio(audio, "x.wav")
    bytes_arg, _ = mock_sync.call_args[0]
    assert bytes_arg is audio


async def test_transcribe_audio_openai_fallback_uses_resilience_wrapper(monkeypatch):
    monkeypatch.setenv("WHISPER_API_MODEL", "whisper-1")
    monkeypatch.setenv("WHISPER_API_TIMEOUT", "42")
    monkeypatch.setenv("WHISPER_API_ATTEMPTS", "4")

    with patch("services.ai.transcription._transcribe_sync", side_effect=ImportError()), \
         patch("openai.AsyncOpenAI") as mock_client_cls, \
         patch(
             "services.ai.transcription.call_with_retry_and_fallback",
             new=AsyncMock(return_value=SimpleNamespace(text="fallback text")),
         ) as mock_resilience:
        out = await transcribe_audio(b"audio-bytes", "fallback.wav")

    assert out == "fallback text"
    mock_client_cls.assert_called_once()
    assert mock_client_cls.call_args.kwargs["timeout"] == 42.0
    assert mock_client_cls.call_args.kwargs["max_retries"] == 0
    assert mock_resilience.await_args.kwargs["primary_model"] == "whisper-1"
    assert mock_resilience.await_args.kwargs["max_attempts"] == 4
    assert mock_resilience.await_args.kwargs["op_name"] == "transcription.audio"
