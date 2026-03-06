from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import httpx

from services.wechat_notify import _get_access_token, _get_config
from utils.log import log

_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_NEGATIVE_CACHE: Dict[str, float] = {}


def _cache_ttl_seconds() -> int:
    raw = os.environ.get("WECHAT_KF_CUSTOMER_CACHE_TTL", "600").strip()
    try:
        ttl = int(raw)
    except ValueError:
        ttl = 600
    return max(60, ttl)


def _enabled() -> bool:
    raw = os.environ.get("WECHAT_KF_ENABLE_CUSTOMER_ENRICH", "1").strip().lower()
    return raw not in ("0", "false", "no")


def get_cached_customer_profile(external_userid: str) -> Optional[Dict[str, Any]]:
    if not external_userid:
        return None
    now = time.time()
    item = _PROFILE_CACHE.get(external_userid)
    if item and item.get("expires_at", 0) > now:
        profile = item.get("profile")
        if isinstance(profile, dict):
            return profile
    return None


async def prefetch_customer_profile(
    external_userid: str,
    *,
    need_enter_session_context: bool = True,
) -> Optional[Dict[str, Any]]:
    """Best-effort fetch of WeCom KF customer profile; failures never raise."""
    if not _enabled() or not external_userid:
        return None

    now = time.time()
    negative_until = _NEGATIVE_CACHE.get(external_userid, 0.0)
    if negative_until > now:
        return None

    cached = get_cached_customer_profile(external_userid)
    if cached is not None:
        return cached

    cfg = _get_config()
    if not cfg.get("app_id") or not cfg.get("app_secret"):
        return None

    try:
        access_token = await _get_access_token(cfg["app_id"], cfg["app_secret"])
        payload: Dict[str, Any] = {
            "external_userid_list": [external_userid],
            "need_enter_session_context": 1 if need_enter_session_context else 0,
        }
        url = "https://qyapi.weixin.qq.com/cgi-bin/kf/customer/batchget"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, params={"access_token": access_token}, json=payload)
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, dict) or data.get("errcode", 0) != 0:
            log(f"[WeCom KF] customer.batchget failed: {data}")
            return None

        invalid = data.get("invalid_external_userid") or []
        if isinstance(invalid, list) and external_userid in invalid:
            _NEGATIVE_CACHE[external_userid] = now + 120.0
            return None

        customers = data.get("customer_list") or []
        if not isinstance(customers, list):
            return None
        for item in customers:
            if not isinstance(item, dict):
                continue
            if str(item.get("external_userid") or "") != external_userid:
                continue
            ttl = _cache_ttl_seconds()
            _PROFILE_CACHE[external_userid] = {
                "profile": item,
                "expires_at": now + float(ttl),
            }
            return item
    except Exception as e:
        log(f"[WeCom KF] customer.batchget FAILED: {e}")
        return None

    return None
