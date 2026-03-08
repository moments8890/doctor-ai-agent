"""
通知发送服务：向医生 WeChat 账号推送随访提醒和紧急任务通知。
"""

from __future__ import annotations

import os
import time

import httpx
from db.crud import get_doctor_wechat_user_id
from db.engine import AsyncSessionLocal
from services.wechat.wechat_notify import _send_customer_service_msg
from utils.log import log

_MINI_TOKEN_CACHE: dict[str, object] = {"token": "", "expires_at": 0.0}


def _provider() -> str:
    return os.environ.get("NOTIFICATION_PROVIDER", "log").strip().lower()


def _wechat_fallback_to_user() -> str:
    return os.environ.get("WECHAT_NOTIFY_FALLBACK_TO_USER", "").strip()


def _is_invalid_wechat_user_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "errcode=40096" in msg or "invalid external userid" in msg


def _mini_app_id() -> str:
    return (os.environ.get("WECHAT_MINI_APP_ID") or "").strip()


def _mini_app_secret() -> str:
    return (os.environ.get("WECHAT_MINI_APP_SECRET") or "").strip()


def _mini_template_id() -> str:
    return (os.environ.get("MINIPROGRAM_SUBSCRIBE_TEMPLATE_ID") or "").strip()


def _mini_page_path() -> str:
    return (os.environ.get("MINIPROGRAM_SUBSCRIBE_PAGEPATH") or "pages/doctor/doctor").strip()


def _mini_data_key() -> str:
    return (os.environ.get("MINIPROGRAM_SUBSCRIBE_DATA_KEY") or "thing1").strip() or "thing1"


async def _mini_access_token() -> str:
    now = time.time()
    cached = str(_MINI_TOKEN_CACHE.get("token") or "")
    expires_at = float(_MINI_TOKEN_CACHE.get("expires_at") or 0.0)
    if cached and now < expires_at - 30:
        return cached

    appid = _mini_app_id()
    secret = _mini_app_secret()
    if not appid or not secret:
        raise RuntimeError("WECHAT_MINI_APP_ID/WECHAT_MINI_APP_SECRET not configured")

    params = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get("https://api.weixin.qq.com/cgi-bin/token", params=params)
    resp.raise_for_status()
    payload = resp.json()
    errcode = int(payload.get("errcode") or 0)
    if errcode != 0:
        raise RuntimeError(
            "Mini access token failed: errcode={0} errmsg={1}".format(
                errcode, payload.get("errmsg") or "unknown"
            )
        )
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Mini access token missing access_token")
    expires_in = int(payload.get("expires_in") or 7200)
    _MINI_TOKEN_CACHE["token"] = token
    _MINI_TOKEN_CACHE["expires_at"] = now + max(60, expires_in)
    return token


async def _send_miniprogram_subscribe_msg(target_user: str, message: str) -> None:
    template_id = _mini_template_id()
    if not template_id:
        raise RuntimeError("MINIPROGRAM_SUBSCRIBE_TEMPLATE_ID not configured")

    access_token = await _mini_access_token()
    data_key = _mini_data_key()
    payload = {
        "touser": target_user,
        "template_id": template_id,
        "page": _mini_page_path(),
        "data": {data_key: {"value": (message or "")[:20]}},
    }

    url = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={0}".format(access_token)
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.post(url, json=payload)
    resp.raise_for_status()
    body = resp.json()
    errcode = int(body.get("errcode") or 0)
    if errcode != 0:
        raise RuntimeError(
            "Mini subscribe send failed: errcode={0} errmsg={1}".format(
                errcode, body.get("errmsg") or "unknown"
            )
        )


async def send_doctor_notification(doctor_id: str, message: str) -> None:
    """Send doctor notification via configured provider.

    Providers:
    - log (default): log-only sink for local/dev, always succeeds
    - wechat: send through WeChat customer service API
    """
    provider = _provider()
    if provider == "wechat":
        target_user = doctor_id
        try:
            async with AsyncSessionLocal() as db:
                mapped = await get_doctor_wechat_user_id(db, doctor_id)
            if mapped:
                target_user = mapped
        except Exception as map_err:
            log(
                "[Notify:wechat] resolve mapped wechat_user_id failed; fallback to doctor_id",
                logger_name="tasks",
                doctor_id=doctor_id,
                error=str(map_err),
            )
        try:
            await _send_customer_service_msg(target_user, message)
            return
        except Exception as e:
            fallback_to_user = _wechat_fallback_to_user()
            if _is_invalid_wechat_user_error(e) and fallback_to_user and fallback_to_user != target_user:
                log(
                    "[Notify:wechat] primary recipient invalid; retrying with fallback recipient",
                    logger_name="tasks",
                    doctor_id=doctor_id,
                    target_user=target_user,
                    fallback_to_user=fallback_to_user,
                )
                await _send_customer_service_msg(fallback_to_user, message)
                return
            raise
        return

    if provider == "wechat_mini_subscribe":
        target_user = doctor_id
        try:
            async with AsyncSessionLocal() as db:
                mapped = await get_doctor_wechat_user_id(db, doctor_id)
            if mapped:
                target_user = mapped
        except Exception as map_err:
            log(
                "[Notify:wechat_mini_subscribe] resolve mapped wechat_user_id failed; fallback to doctor_id",
                logger_name="tasks",
                doctor_id=doctor_id,
                error=str(map_err),
            )

        await _send_miniprogram_subscribe_msg(target_user, message)
        return

    if provider == "log":
        preview = message.replace("\n", " ")[:120]
        log(
            "[Notify:log] delivered",
            logger_name="tasks",
            doctor_id=doctor_id,
            preview=preview,
        )
        return

    raise RuntimeError(f"Unsupported NOTIFICATION_PROVIDER: {provider}")
