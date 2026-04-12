"""ASR provider abstraction. Supports browser (dev noop), whisper (self-hosted), tencent (prod)."""

import os
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Optional


class ASRProvider(str, Enum):
    browser = "browser"    # Dev mode -- frontend handles ASR via browser API
    whisper = "whisper"    # Self-hosted Whisper model
    tencent = "tencent"    # Tencent Cloud real-time ASR


@dataclass
class TranscriptChunk:
    text: str
    is_final: bool  # True = sentence complete, False = interim/partial
    confidence: float = 1.0


def get_asr_provider() -> ASRProvider:
    return ASRProvider(os.getenv("ASR_PROVIDER", "browser"))


async def transcribe_audio_bytes(audio_bytes: bytes, format: str = "wav", language: str = "zh") -> str:
    """Batch transcribe an audio file. Returns full text."""
    provider = get_asr_provider()
    if provider == ASRProvider.whisper:
        return await _whisper_batch(audio_bytes, format, language)
    elif provider == ASRProvider.tencent:
        return await _tencent_batch(audio_bytes, format, language)
    else:
        return ""  # browser mode -- no server-side transcription


_whisper_model = None


def _get_whisper_model():
    """Lazy-load and cache the Whisper model singleton."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        model_size = os.getenv("WHISPER_MODEL", "large-v3")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        _whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _whisper_model


async def _whisper_batch(audio_bytes: bytes, format: str, language: str) -> str:
    """Transcribe using local Whisper model (cached singleton, runs in thread)."""
    import asyncio
    import tempfile

    suffix = f".{format}" if format else ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        def _transcribe():
            model = _get_whisper_model()
            segments, _ = model.transcribe(tmp_path, language=language)
            return " ".join(seg.text for seg in segments).strip()

        return await asyncio.get_event_loop().run_in_executor(None, _transcribe)
    finally:
        import os as _os
        _os.unlink(tmp_path)


async def _convert_to_wav(audio_bytes: bytes, src_format: str) -> bytes:
    """Convert audio to 16kHz mono WAV via ffmpeg (runs in thread pool)."""
    import asyncio
    import subprocess
    import tempfile

    def _run():
        with tempfile.NamedTemporaryFile(suffix=f".{src_format}", delete=False) as src:
            src.write(audio_bytes)
            src_path = src.name
        dst_path = src_path + ".wav"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", dst_path],
                capture_output=True, timeout=30,
            )
            with open(dst_path, "rb") as f:
                return f.read()
        finally:
            import os as _os
            _os.unlink(src_path)
            if _os.path.exists(dst_path):
                _os.unlink(dst_path)

    return await asyncio.get_event_loop().run_in_executor(None, _run)


async def _tencent_batch(audio_bytes: bytes, format: str, language: str) -> str:
    """Transcribe using Tencent Cloud ASR one-sentence recognition API.

    Good for short audio clips (<60s). For longer audio, use file ASR.
    Uses 16k_zh_medical engine for medical Chinese vocabulary.
    """
    import base64

    from utils.log import log

    secret_id = os.getenv("TENCENT_ASR_SECRET_ID", "")
    secret_key = os.getenv("TENCENT_ASR_SECRET_KEY", "")
    engine = os.getenv("TENCENT_ASR_ENGINE", "16k_zh_medical")

    if not secret_id or not secret_key:
        log("[ASR] Tencent ASR credentials not configured (TENCENT_ASR_SECRET_ID/KEY)", level="warning")
        return ""

    # Tencent ASR supported formats (webm is NOT supported)
    TENCENT_FORMATS = {"wav", "pcm", "ogg-opus", "speex", "silk", "mp3", "m4a", "aac"}
    FORMAT_MAP = {
        "wav": "wav", "pcm": "pcm", "ogg": "ogg-opus",
        "speex": "speex", "silk": "silk", "mp3": "mp3",
        "m4a": "m4a", "aac": "aac",
    }
    voice_format = FORMAT_MAP.get(format)

    # Convert unsupported formats (webm, amr, flac, etc.) to wav via ffmpeg
    if not voice_format:
        audio_bytes = await _convert_to_wav(audio_bytes, format)
        voice_format = "wav"

    # Base64 encode the audio
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    try:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.asr.v20190614 import asr_client, models as asr_models

        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = "asr.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        client = asr_client.AsrClient(cred, "", client_profile)

        req = asr_models.SentenceRecognitionRequest()
        req.ProjectId = 0
        req.SubServiceType = 2  # one-sentence
        req.EngSerViceType = engine
        req.SourceType = 1  # audio data (not URL)
        req.VoiceFormat = voice_format
        req.Data = audio_b64
        req.DataLen = len(audio_bytes)

        resp = client.SentenceRecognition(req)
        return resp.Result or ""

    except ImportError:
        log(
            "[ASR] tencentcloud SDK not installed. "
            "Install: pip install tencentcloud-sdk-python",
            level="error",
        )
        return ""
    except Exception as e:
        log(f"[ASR] Tencent ASR request failed: {e}", level="error")
        return ""
