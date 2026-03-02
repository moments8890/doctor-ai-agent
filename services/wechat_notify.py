from __future__ import annotations

import os
import time
from typing import List

import httpx

from utils.log import log

# Access token cache
_token_cache: dict = {"token": "", "expires_at": 0.0}


def _get_config() -> dict:
    return {
        "token": os.environ.get("WECHAT_TOKEN", ""),
        "app_id": os.environ.get("WECHAT_APP_ID", ""),
        "app_secret": os.environ.get("WECHAT_APP_SECRET", ""),
        "aes_key": os.environ.get("WECHAT_ENCODING_AES_KEY", ""),
    }


async def _get_access_token(app_id: str, app_secret: str) -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        log(f"[WeChat token] using cached token (expires in {int(_token_cache['expires_at'] - now)}s)")
        return _token_cache["token"]

    url = "https://api.weixin.qq.com/cgi-bin/token"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params={
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        })
        data = resp.json()
        log(f"[WeChat token] fetched new token: {data}")
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + data["expires_in"] - 60
        return _token_cache["token"]


def _split_message(text: str, limit: int = 600) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("【", 1, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:]
    return chunks


async def _send_customer_service_msg(to_user: str, content: str) -> None:
    cfg = _get_config()
    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}"
        chunks = _split_message(content)
        log(f"[WeChat cs] sending {len(chunks)} message(s) to {to_user}")
        async with httpx.AsyncClient() as client:
            for i, chunk in enumerate(chunks):
                payload = {"touser": to_user, "msgtype": "text", "text": {"content": chunk}}
                resp = await client.post(url, json=payload)
                log(f"[WeChat cs] chunk {i+1}/{len(chunks)}: {resp.json()}")
    except Exception as e:
        log(f"[WeChat cs] FAILED: {e}")
