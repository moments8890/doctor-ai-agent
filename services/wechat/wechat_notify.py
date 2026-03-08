"""
WeCom/微信 Access Token 管理及客服消息发送。
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

from db.crud import get_runtime_token, upsert_runtime_token
from db.engine import AsyncSessionLocal
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
    # WeCom 自建应用 (custom internal app) — takes priority if configured.
    wecom_corp_id = os.environ.get("WECOM_CORP_ID", "").strip()
    wecom_agent_id = os.environ.get("WECOM_AGENT_ID", "").strip()
    wecom_secret = os.environ.get("WECOM_SECRET", "").strip()
    is_wecom_app = bool(wecom_corp_id and wecom_agent_id and wecom_secret)

    # WeCom KF (customer service) — used only when 自建应用 is not configured.
    kf_corp_id = os.environ.get("WECHAT_KF_CORP_ID", "").strip()
    kf_secret = os.environ.get("WECHAT_KF_SECRET", "").strip()
    is_kf = bool(kf_corp_id and kf_secret) and not is_wecom_app

    if is_wecom_app:
        app_id = wecom_corp_id
        app_secret = wecom_secret
    else:
        app_id = _env_first("WECHAT_KF_CORP_ID", "WECHAT_APP_ID")
        app_secret = _env_first("WECHAT_KF_SECRET", "WECHAT_APP_SECRET")

    return {
        "token": _env_first("WECHAT_KF_TOKEN", "WECHAT_TOKEN"),
        "app_id": app_id,
        "app_secret": app_secret,
        "aes_key": _env_first("WECHAT_AES_KEY", "WECHAT_KF_ENCODING_AES_KEY", "WECHAT_ENCODING_AES_KEY"),
        "open_kfid": os.environ.get("WECHAT_KF_OPEN_KFID", "").strip(),
        "agent_id": wecom_agent_id,
        "is_kf": is_kf,
        "is_wecom_app": is_wecom_app,
    }


def _token_key(app_id: str) -> str:
    channel = "wecom_kf" if app_id.startswith("ww") else "wechat_oa"
    return "access_token:{0}:{1}".format(channel, app_id)


def _dt_to_ts(value: datetime) -> float:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).timestamp()
    return value.astimezone(timezone.utc).timestamp()


async def _get_access_token(app_id: str, app_secret: str) -> str:
    if not app_id or not app_secret:
        raise RuntimeError("WECHAT_APP_ID/WECHAT_APP_SECRET not configured")

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        log(f"[WeChat token] using cached token (expires in {int(_token_cache['expires_at'] - now)}s)")
        return _token_cache["token"]

    # Shared cache lookup (cross-instance/restart safe).
    now_dt = datetime.now(timezone.utc)
    token_key = _token_key(app_id)
    try:
        async with AsyncSessionLocal() as session:
            runtime_token = await get_runtime_token(session, token_key)
        if (
            runtime_token is not None
            and runtime_token.token_value
            and runtime_token.expires_at is not None
            and _dt_to_ts(runtime_token.expires_at) > now
        ):
            _token_cache["token"] = runtime_token.token_value
            _token_cache["expires_at"] = _dt_to_ts(runtime_token.expires_at)
            log("[WeChat token] using shared DB token cache")
            return runtime_token.token_value
    except Exception as e:
        log(f"[WeChat token] shared cache lookup FAILED: {e}")

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
        ttl_seconds = max(1, int(data["expires_in"]) - 60)
        _token_cache["expires_at"] = now + ttl_seconds
        expires_at = now_dt + timedelta(seconds=ttl_seconds)
        try:
            async with AsyncSessionLocal() as session:
                await upsert_runtime_token(
                    session,
                    token_key=token_key,
                    token_value=data["access_token"],
                    expires_at=expires_at,
                )
        except Exception as e:
            log(f"[WeChat token] shared cache persist FAILED: {e}")
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
        kf_id = ""
        if cfg.get("is_wecom_app", False):
            url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        elif cfg.get("is_kf", False):
            kf_id = open_kfid.strip() or cfg["open_kfid"]
            if not kf_id:
                raise RuntimeError("WECHAT_KF_OPEN_KFID not configured for WeChat KF send")
            url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={access_token}"
        else:
            url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}"
        log(
            f"[WeChat cs] sending {len(chunks)} message(s) to {to_user} "
            f"mode={'wecom_app' if cfg.get('is_wecom_app', False) else 'kf' if cfg.get('is_kf', False) else 'oa'}"
        )
        async with httpx.AsyncClient() as client:
            for i, chunk in enumerate(chunks):
                if cfg.get("is_wecom_app", False):
                    payload = {
                        "touser": to_user,
                        "msgtype": "text",
                        "agentid": int(cfg["agent_id"]),
                        "text": {"content": chunk},
                    }
                elif cfg.get("is_kf", False):
                    payload = {"touser": to_user, "msgtype": "text", "open_kfid": kf_id, "text": {"content": chunk}}
                else:
                    payload = {"touser": to_user, "msgtype": "text", "text": {"content": chunk}}
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
