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


async def _whisper_batch(audio_bytes: bytes, format: str, language: str) -> str:
    """Transcribe using local Whisper model."""
    import json
    import subprocess
    import tempfile

    suffix = f".{format}" if format else ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        # Try faster-whisper first (Python API), fall back to CLI
        try:
            from faster_whisper import WhisperModel
            model_size = os.getenv("WHISPER_MODEL", "large-v3")
            device = os.getenv("WHISPER_DEVICE", "cpu")
            model = WhisperModel(model_size, device=device)
            segments, _ = model.transcribe(tmp_path, language=language)
            return " ".join(seg.text for seg in segments).strip()
        except ImportError:
            # Fall back to whisper CLI
            result = subprocess.run(
                ["whisper", tmp_path, "--language", language, "--output_format", "json", "--output_dir", "/tmp"],
                capture_output=True, timeout=120,
            )
            json_path = tmp_path.rsplit(".", 1)[0] + ".json"
            with open(json_path) as jf:
                data = json.load(jf)
            return data.get("text", "").strip()
    finally:
        import os as _os
        _os.unlink(tmp_path)


async def _tencent_batch(audio_bytes: bytes, format: str, language: str) -> str:
    """Transcribe using Tencent Cloud ASR batch API."""
    # Placeholder -- will be implemented when Tencent SDK is integrated
    from utils.log import log
    log("[ASR] Tencent batch transcription not yet implemented", level="warning")
    return ""
