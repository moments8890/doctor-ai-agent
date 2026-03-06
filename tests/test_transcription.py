"""Tests for services/transcription.py — faster_whisper is mocked.

Covers the new consultation_mode parameter and initial_prompt selection logic
added in the voice input feature.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services.transcription import (
    _CONSULTATION_PROMPT,
    _MEDICAL_PROMPT,
    transcribe_audio,
)


async def test_transcribe_audio_uses_medical_prompt_by_default():
    """consultation_mode=False (default) passes _MEDICAL_PROMPT to _transcribe_sync."""
    with patch("services.transcription._transcribe_sync", return_value="医嘱录入") as mock_sync:
        result = await transcribe_audio(b"audio", "test.wav")
    assert result == "医嘱录入"
    mock_sync.assert_called_once()
    _, prompt_arg = mock_sync.call_args[0]
    assert prompt_arg is _MEDICAL_PROMPT


async def test_transcribe_audio_uses_consultation_prompt_when_mode_true():
    """consultation_mode=True passes _CONSULTATION_PROMPT to _transcribe_sync."""
    with patch("services.transcription._transcribe_sync", return_value="问诊内容") as mock_sync:
        result = await transcribe_audio(b"audio", "consult.wav", consultation_mode=True)
    assert result == "问诊内容"
    _, prompt_arg = mock_sync.call_args[0]
    assert prompt_arg is _CONSULTATION_PROMPT


async def test_transcribe_audio_passes_bytes_as_first_arg():
    """audio_bytes is the first positional arg to _transcribe_sync."""
    audio = b"raw_audio_data"
    with patch("services.transcription._transcribe_sync", return_value="ok") as mock_sync:
        await transcribe_audio(audio, "x.wav")
    bytes_arg, _ = mock_sync.call_args[0]
    assert bytes_arg is audio
