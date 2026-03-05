from __future__ import annotations

import os
import time
from typing import List

import httpx

from utils.log import log

# Access token cache
_token_cache: dict = {"token": "", "expires_at": 0.0}


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _get_config() -> dict:
    kf_corp_id = os.environ.get("WECHAT_KF_CORP_ID", "").strip()
    kf_secret = os.environ.get("WECHAT_KF_SECRET", "").strip()
    is_kf = bool(kf_corp_id and kf_secret)
    return {
        # Prefer WeCom KF env names used by doctor-openclaw; keep legacy aliases.
        "token": _env_first("WECHAT_KF_TOKEN", "WECHAT_TOKEN"),
        "app_id": _env_first("WECHAT_KF_CORP_ID", "WECHAT_APP_ID"),
        "app_secret": _env_first("WECHAT_KF_SECRET", "WECHAT_APP_SECRET"),
        "aes_key": _env_first("WECHAT_KF_ENCODING_AES_KEY", "WECHAT_ENCODING_AES_KEY"),
        "open_kfid": os.environ.get("WECHAT_KF_OPEN_KFID", "").strip(),
        "is_kf": is_kf,
    }


async def _get_access_token(app_id: str, app_secret: str) -> str:
    if not app_id or not app_secret:
        raise RuntimeError("WECHAT_APP_ID/WECHAT_APP_SECRET not configured")

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        log(f"[WeChat token] using cached token (expires in {int(_token_cache['expires_at'] - now)}s)")
        return _token_cache["token"]

    use_kf = app_id.startswith("ww")
    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken" if use_kf else "https://api.weixin.qq.com/cgi-bin/token"
    params = (
        {"corpid": app_id, "corpsecret": app_secret}
        if use_kf
        else {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        if hasattr(resp, "raise_for_status"):
            resp.raise_for_status()
        data = resp.json()
        log(f"[WeChat token] fetched new token: {data}")
        if not isinstance(data, dict) or "access_token" not in data:
            errcode = data.get("errcode") if isinstance(data, dict) else None
            errmsg = data.get("errmsg") if isinstance(data, dict) else str(data)
            raise RuntimeError(f"WeChat token fetch failed: errcode={errcode}, errmsg={errmsg}")

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


async def _send_customer_service_msg(
    to_user: str,
    content: str,
    *,
    open_kfid: str = "",
) -> None:
    cfg = _get_config()
    if not to_user:
        raise RuntimeError("missing to_user")
    if not content.strip():
        raise RuntimeError("empty notification content")

    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        chunks = _split_message(content)
        if cfg["is_kf"]:
            kf_id = open_kfid.strip() or cfg["open_kfid"]
            if not kf_id:
                raise RuntimeError("WECHAT_KF_OPEN_KFID not configured for WeChat KF send")
            url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={access_token}"
        else:
            url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}"
        log(f"[WeChat cs] sending {len(chunks)} message(s) to {to_user}")
        async with httpx.AsyncClient() as client:
            for i, chunk in enumerate(chunks):
                payload = {"touser": to_user, "msgtype": "text", "text": {"content": chunk}}
                if cfg["is_kf"]:
                    payload["open_kfid"] = kf_id
                resp = await client.post(url, json=payload)
                if hasattr(resp, "raise_for_status"):
                    resp.raise_for_status()
                data = resp.json()
                log(f"[WeChat cs] chunk {i+1}/{len(chunks)}: {data}")
                if isinstance(data, dict) and data.get("errcode", 0) != 0:
                    raise RuntimeError(
                        f"WeChat send failed: errcode={data.get('errcode')} errmsg={data.get('errmsg')}"
                    )
    except Exception as e:
        log(f"[WeChat cs] FAILED: {e}")
        raise
