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

# Access token cache (WeCom app / WeChat OA)
_token_cache: dict = {"token": "", "expires_at": 0.0}
# Separate cache for WeCom KF access tokens (different corpsecret → different token/permissions)
_kf_token_cache: dict = {"token": "", "expires_at": 0.0}


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


async def _check_db_token_cache(app_id: str, now: float, token_key: str) -> "Optional[str]":
    """检查数据库共享 Token 缓存；命中时更新内存缓存并返回 token，否则返回 None。"""
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
    return None


async def _fetch_fresh_token(app_id: str, app_secret: str, now: float, token_key: str) -> str:
    """从微信/企业微信 API 获取新 Token，更新内存和数据库缓存后返回。"""
    now_dt = datetime.now(timezone.utc)
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
    log(f"[WeChat token] fetched new token (expires_in={data.get('expires_in')}s)")
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


async def _get_access_token(app_id: str, app_secret: str) -> str:
    """获取微信/企业微信 Access Token，优先内存缓存，其次 DB 共享缓存，最后远程刷新。"""
    if not app_id or not app_secret:
        raise RuntimeError("WECHAT_APP_ID/WECHAT_APP_SECRET not configured")

    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        log(f"[WeChat token] using cached token (expires in {int(_token_cache['expires_at'] - now)}s)")
        return _token_cache["token"]

    token_key = _token_key(app_id)
    db_token = await _check_db_token_cache(app_id, now, token_key)
    if db_token is not None:
        return db_token

    return await _fetch_fresh_token(app_id, app_secret, now, token_key)


async def _get_kf_access_token() -> str:
    """Get a WeCom KF access token using WECHAT_KF_CORP_ID + WECHAT_KF_SECRET.

    Uses a separate in-memory cache (_kf_token_cache) to avoid colliding with the
    WeCom custom-app token (_token_cache) when both share the same corp_id.
    The KF token may have different API permissions (e.g. kf/send_msg access).
    Falls back to the regular _get_access_token path if KF credentials are absent.
    """
    kf_corp_id = os.environ.get("WECHAT_KF_CORP_ID", "").strip()
    kf_secret = os.environ.get("WECHAT_KF_SECRET", "").strip()
    if not kf_corp_id or not kf_secret:
        # Fall back: no dedicated KF credentials — reuse whatever is configured
        cfg = _get_config()
        return await _get_access_token(cfg["app_id"], cfg["app_secret"])

    now = time.time()
    if _kf_token_cache["token"] and now < _kf_token_cache["expires_at"]:
        log(f"[WeChat KF token] using cached KF token (expires in {int(_kf_token_cache['expires_at'] - now)}s)")
        return _kf_token_cache["token"]

    # Fetch fresh token with KF credentials
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": kf_corp_id, "corpsecret": kf_secret},
        )
        if hasattr(resp, "raise_for_status"):
            resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict) or "access_token" not in data:
        raise RuntimeError(f"WeChat KF token fetch failed: {data}")
    ttl_seconds = max(1, int(data.get("expires_in", 7200)) - 60)
    _kf_token_cache["token"] = data["access_token"]
    _kf_token_cache["expires_at"] = now + ttl_seconds
    log(f"[WeChat KF token] fetched new KF token (expires in {ttl_seconds}s)")
    return _kf_token_cache["token"]


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


async def upload_temp_media(content: bytes, filename: str, filetype: str = "file") -> str:
    """Upload a file to WeCom temp media store. Returns media_id (valid 3 days).

    filetype: 'image' | 'voice' | 'video' | 'file'
    """
    cfg = _get_config()
    access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
    use_kf = cfg.get("is_kf", False) or cfg.get("is_wecom_app", False)
    if use_kf:
        url = f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={access_token}&type={filetype}"
    else:
        url = f"https://api.weixin.qq.com/cgi-bin/media/upload?access_token={access_token}&type={filetype}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            files={"media": (filename, content, "application/octet-stream")},
        )
    resp.raise_for_status()
    data = resp.json()
    errcode = int(data.get("errcode") or 0)
    if errcode != 0:
        raise RuntimeError(f"upload_temp_media failed: errcode={errcode} errmsg={data.get('errmsg')}")
    media_id = str(data.get("media_id") or "").strip()
    if not media_id:
        raise RuntimeError("upload_temp_media: no media_id returned")
    log(f"[WeChat media] uploaded {filename} → media_id={media_id}")
    return media_id


async def send_file_message(to_user: str, media_id: str, open_kfid: str = "") -> None:
    """Send a file message (already uploaded as temp media) via WeCom customer service or app."""
    cfg = _get_config()
    access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
    if cfg.get("is_wecom_app", False):
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        payload = {
            "touser": to_user,
            "msgtype": "file",
            "agentid": int(cfg["agent_id"]),
            "file": {"media_id": media_id},
        }
    elif cfg.get("is_kf", False):
        kf_id = open_kfid.strip() or cfg["open_kfid"]
        url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={access_token}"
        payload = {
            "touser": to_user,
            "msgtype": "file",
            "open_kfid": kf_id,
            "file": {"media_id": media_id},
        }
    else:
        url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}"
        payload = {"touser": to_user, "msgtype": "file", "file": {"media_id": media_id}}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    errcode = int(data.get("errcode") or 0)
    if errcode != 0:
        raise RuntimeError(f"send_file_message failed: errcode={errcode} errmsg={data.get('errmsg')}")
    log(f"[WeChat media] file message sent to {to_user}")


def _cs_send_url_and_mode(cfg: dict, access_token: str, kf_id: str) -> "tuple[str, str]":
    """根据配置选择客服消息发送 URL 和模式名。"""
    if kf_id:
        return f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={access_token}", "wecom_kf"
    if cfg.get("is_wecom_app", False):
        return f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}", "wecom_app"
    if cfg.get("is_kf", False):
        if not kf_id:
            raise RuntimeError("WECHAT_KF_OPEN_KFID is required when is_kf=True")
        return f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={access_token}", "kf"
    return f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={access_token}", "oa"


def _cs_build_payload(to_user: str, chunk: str, cfg: dict, kf_id: str) -> dict:
    """构建单条客服消息 payload。"""
    if kf_id:
        return {"touser": to_user, "msgtype": "text", "open_kfid": kf_id, "text": {"content": chunk}}
    if cfg.get("is_wecom_app", False):
        return {"touser": to_user, "msgtype": "text", "agentid": int(cfg["agent_id"]), "text": {"content": chunk}}
    return {"touser": to_user, "msgtype": "text", "text": {"content": chunk}}


async def _send_customer_service_msg(
    to_user: str,
    content: str,
    *,
    open_kfid: str = "",
) -> None:
    """向企业微信用户发送客服文本消息，自动分片处理超长内容。"""
    cfg = _get_config()
    if not to_user:
        raise RuntimeError("missing to_user")
    if not content.strip():
        raise RuntimeError("empty notification content")

    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        chunks = _split_message(content)
        kf_id = open_kfid.strip() or cfg.get("open_kfid", "")
        url, mode = _cs_send_url_and_mode(cfg, access_token, kf_id)
        log(f"[WeChat cs] sending {len(chunks)} message(s) to {to_user} mode={mode}")
        async with httpx.AsyncClient() as client:
            for i, chunk in enumerate(chunks):
                payload = _cs_build_payload(to_user, chunk, cfg, kf_id)
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
