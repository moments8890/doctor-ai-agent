import pytest

from services.asr.provider import ASRProvider, TranscriptChunk, get_asr_provider, transcribe_audio_bytes


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


def test_tencent_provider_from_env(monkeypatch):
    monkeypatch.setenv("ASR_PROVIDER", "tencent")
    assert get_asr_provider() == ASRProvider.tencent


def test_transcript_chunk():
    chunk = TranscriptChunk(text="你好", is_final=True, confidence=0.95)
    assert chunk.text == "你好"
    assert chunk.is_final is True


@pytest.mark.asyncio
async def test_tencent_batch_no_credentials(monkeypatch):
    """Tencent batch should return empty string when no credentials configured."""
    monkeypatch.setenv("ASR_PROVIDER", "tencent")
    monkeypatch.delenv("TENCENT_ASR_SECRET_ID", raising=False)
    monkeypatch.delenv("TENCENT_ASR_SECRET_KEY", raising=False)
    result = await transcribe_audio_bytes(b"fake audio", format="wav")
    assert result == ""


@pytest.mark.asyncio
async def test_browser_provider_returns_empty(monkeypatch):
    """Browser provider should return empty string (no server-side transcription)."""
    monkeypatch.setenv("ASR_PROVIDER", "browser")
    result = await transcribe_audio_bytes(b"fake audio", format="wav")
    assert result == ""
