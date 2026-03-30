"""REST endpoint for batch audio transcription."""

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Header, UploadFile

from services.asr.provider import ASRProvider, get_asr_provider, transcribe_audio_bytes
from utils.log import log

router = APIRouter()

ALLOWED_AUDIO_FORMATS = {"wav", "mp3", "m4a", "ogg", "webm", "amr", "silk", "flac"}
MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/api/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    """Batch transcribe an uploaded audio file to text."""
    provider = get_asr_provider()
    if provider == ASRProvider.browser:
        raise HTTPException(400, "Server-side transcription not available in browser/dev mode")

    filename = file.filename or "audio.wav"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_AUDIO_FORMATS:
        raise HTTPException(400, f"不支持的音频格式。支持: {', '.join(sorted(ALLOWED_AUDIO_FORMATS))}")

    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "音频文件过大，最大支持 50MB")
    if not audio_bytes:
        raise HTTPException(400, "音频文件为空")

    try:
        text = await transcribe_audio_bytes(audio_bytes, format=ext)
    except Exception as e:
        log(f"[transcribe] failed: {e}", level="error")
        raise HTTPException(500, f"转写失败: {str(e)}")

    return {"text": text, "provider": provider.value}
