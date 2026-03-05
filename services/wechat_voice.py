import asyncio
import os
import subprocess

import httpx

from utils.log import log

def _media_get_url() -> str:
    # WeCom KF uses qyapi endpoint; Official Account uses api.weixin endpoint.
    if os.environ.get("WECHAT_KF_CORP_ID", "").strip():
        return "https://qyapi.weixin.qq.com/cgi-bin/media/get"
    return "https://api.weixin.qq.com/cgi-bin/media/get"


async def download_voice(media_id: str, access_token: str) -> bytes:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _media_get_url(),
            params={"access_token": access_token, "media_id": media_id},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"WeChat media download failed: HTTP {resp.status_code}")
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            raise RuntimeError(f"WeChat media error: {resp.json()}")
        log(f"[Voice] downloaded {len(resp.content)} bytes, content-type={content_type!r}")
        return resp.content


def _ffmpeg_to_wav(audio_bytes: bytes) -> bytes:
    """Convert AMR/SILK audio to 16kHz mono WAV using ffmpeg (via stdin/stdout)."""
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", "pipe:0",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            "pipe:1",
        ],
        input=audio_bytes,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode()[:300]}")
    return result.stdout


async def download_and_convert(media_id: str, access_token: str) -> bytes:
    """Download WeChat voice and convert to WAV bytes ready for Whisper."""
    raw = await download_voice(media_id, access_token)
    loop = asyncio.get_event_loop()
    wav = await loop.run_in_executor(None, _ffmpeg_to_wav, raw)
    log(f"[Voice] converted to WAV: {len(wav)} bytes")
    return wav
