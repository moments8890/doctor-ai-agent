import pytest

from services.asr.provider import ASRProvider, TranscriptChunk, get_asr_provider


def test_asr_provider_enum():
    assert ASRProvider.browser.value == "browser"
    assert ASRProvider.whisper.value == "whisper"
    assert ASRProvider.tencent.value == "tencent"


def test_default_provider_is_browser(monkeypatch):
    monkeypatch.delenv("ASR_PROVIDER", raising=False)
    assert get_asr_provider() == ASRProvider.browser


def test_provider_from_env(monkeypatch):
    monkeypatch.setenv("ASR_PROVIDER", "whisper")
    assert get_asr_provider() == ASRProvider.whisper


def test_transcript_chunk():
    chunk = TranscriptChunk(text="你好", is_final=True, confidence=0.95)
    assert chunk.text == "你好"
    assert chunk.is_final is True
