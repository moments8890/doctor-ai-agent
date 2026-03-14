"""
Whisper 语音转文字服务，针对医学术语优化提示词。
"""

from __future__ import annotations

import asyncio
import functools
import io
import os
import wave
from services.ai.llm_resilience import call_with_retry_and_fallback
from utils.log import log

_model = None
_model_lock = asyncio.Lock()


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = os.environ.get("WHISPER_MODEL", "large-v3")
        device = os.environ.get("WHISPER_DEVICE", "cpu")
        compute_type = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
        log(f"[Whisper] loading model={model_size} device={device} compute={compute_type}")
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        log("[Whisper] model loaded")
    return _model


def _transcribe_sync(audio_bytes: bytes, initial_prompt: str) -> str:
    model = _get_model()

    # faster-whisper accepts a file-like object or file path
    audio_file = io.BytesIO(audio_bytes)

    segments, info = model.transcribe(
        audio_file,
        language="zh",
        initial_prompt=initial_prompt,
        beam_size=5,
        vad_filter=True,           # skip silence
        vad_parameters={"min_silence_duration_ms": 300},
    )
    text = "".join(seg.text for seg in segments).strip()
    log(f"[Whisper] detected_language={info.language} prob={info.language_probability:.2f} chars={len(text)}")
    return text


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    consultation_mode: bool = False,
) -> str:
    """Transcribe audio bytes to text using local faster-whisper model.

    Falls back to OpenAI Whisper API if faster_whisper is not installed.
    """
    from utils.prompt_loader import get_prompt
    if consultation_mode:
        initial_prompt = await get_prompt("transcription-consultation")
    else:
        initial_prompt = await get_prompt("transcription-medical")
    try:
        async with _model_lock:
            loop = asyncio.get_event_loop()
            fn = functools.partial(_transcribe_sync, audio_bytes, initial_prompt)
            return await loop.run_in_executor(None, fn)
    except ImportError:
        log("[Whisper] faster_whisper not installed, falling back to OpenAI API")
        # PHI egress gate: raw audio contains clinical speech.
        from services.ai.egress_policy import check_cloud_egress
        check_cloud_egress("openai", "transcription")
        from openai import AsyncOpenAI
        model = os.environ.get("WHISPER_API_MODEL", "whisper-1")
        client = AsyncOpenAI(
            timeout=float(os.environ.get("WHISPER_API_TIMEOUT", "60")),
            max_retries=0,
        )

        async def _call(model_name: str):
            return await client.audio.transcriptions.create(
                model=model_name,
                file=(filename, audio_bytes),
                language="zh",
                prompt=initial_prompt,
            )

        response = await call_with_retry_and_fallback(
            _call,
            primary_model=model,
            fallback_model=None,
            max_attempts=int(os.environ.get("WHISPER_API_ATTEMPTS", "3")),
            op_name="transcription.audio",
        )
        return response.text
