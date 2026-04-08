"""
WeChat JSSDK voice recording support for miniprogram web-view.

Two endpoints:
  GET  /api/wechat/jssdk-config   — returns wx.config parameters (signature)
  POST /api/voice/wx-transcribe   — downloads AMR from WeChat by serverId, runs ASR
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from utils.log import log

router = APIRouter(tags=["voice"])

# ── JSSDK ticket cache ───────────────────────────────────────────────────────

_ticket_cache: dict = {"ticket": "", "expires_at": 0.0}


def _oa_app_id() -> str:
    """Official Account AppId (NOT miniprogram AppId)."""
    return (os.environ.get("WECHAT_OA_APP_ID") or os.environ.get("WECHAT_APP_ID") or "").strip()


def _oa_app_secret() -> str:
    return (os.environ.get("WECHAT_OA_APP_SECRET") or os.environ.get("WECHAT_APP_SECRET") or "").strip()


async def _get_oa_access_token() -> str:
    """Get Official Account access token (separate from miniprogram token)."""
    app_id = _oa_app_id()
    app_secret = _oa_app_secret()
    if not app_id or not app_secret:
        raise HTTPException(503, "WECHAT_OA_APP_ID/SECRET not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={"grant_type": "client_credential", "appid": app_id, "secret": app_secret},
        )
    data = resp.json()
    if "access_token" not in data:
        log(f"[JSSDK] OA token error: {data}", level="error")
        raise HTTPException(503, "Failed to get OA access token")
    return data["access_token"]


async def _get_jsapi_ticket() -> str:
    now = time.time()
    if _ticket_cache["ticket"] and now < _ticket_cache["expires_at"]:
        return _ticket_cache["ticket"]

    token = await _get_oa_access_token()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/ticket/getticket",
            params={"access_token": token, "type": "jsapi"},
        )
    data = resp.json()
    if data.get("errcode", 0) != 0:
        log(f"[JSSDK] ticket error: {data}", level="error")
        raise HTTPException(503, "Failed to get jsapi_ticket")

    _ticket_cache["ticket"] = data["ticket"]
    _ticket_cache["expires_at"] = now + max(1, int(data.get("expires_in", 7200)) - 60)
    return data["ticket"]


def _make_signature(ticket: str, nonce: str, timestamp: int, url: str) -> str:
    raw = f"jsapi_ticket={ticket}&noncestr={nonce}&timestamp={timestamp}&url={url}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ── Endpoints ────────────────────────────────────────────────────────────────


class JssdkConfigRequest(BaseModel):
    url: str


@router.post("/api/wechat/jssdk-config")
async def jssdk_config(body: JssdkConfigRequest):
    """Return wx.config parameters for JSSDK voice recording."""
    ticket = await _get_jsapi_ticket()
    nonce = os.urandom(8).hex()
    timestamp = int(time.time())
    # Strip hash — iOS uses landing URL, Android uses current URL
    url = body.url.split("#")[0]
    signature = _make_signature(ticket, nonce, timestamp, url)

    return {
        "appId": _oa_app_id(),
        "timestamp": timestamp,
        "nonceStr": nonce,
        "signature": signature,
    }


class WxTranscribeRequest(BaseModel):
    serverId: str


@router.post("/api/voice/wx-transcribe")
async def wx_transcribe(
    body: WxTranscribeRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Download AMR voice from WeChat by serverId, transcribe via ASR."""
    from services.asr.provider import ASRProvider, get_asr_provider, transcribe_audio_bytes

    provider = get_asr_provider()
    if provider == ASRProvider.browser:
        raise HTTPException(400, "Server-side ASR not configured (set ASR_PROVIDER)")

    # Download the voice file from WeChat temp media
    token = await _get_oa_access_token()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/media/get",
            params={"access_token": token, "media_id": body.serverId},
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"WeChat media download failed: HTTP {resp.status_code}")
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type or "text/" in content_type:
        log(f"[wx-transcribe] WeChat error response: {resp.text[:200]}", level="error")
        raise HTTPException(502, "WeChat media download returned error")

    audio_bytes = resp.content
    log(f"[wx-transcribe] downloaded {len(audio_bytes)} bytes, type={content_type}")

    # AMR is the default format from wx.uploadVoice
    audio_format = "amr"
    if "silk" in content_type or "speex" in content_type:
        audio_format = "silk"

    try:
        text = await transcribe_audio_bytes(audio_bytes, format=audio_format)
    except Exception as e:
        log(f"[wx-transcribe] ASR failed: {e}", level="error")
        raise HTTPException(500, f"语音识别失败: {e}")

    return {"text": text}
