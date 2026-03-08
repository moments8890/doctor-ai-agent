"""
微信小程序登录授权：code 换 session_key、用户信息解密和 JWT 令牌签发。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional


class MiniProgramAuthError(ValueError):
    pass


@dataclass(frozen=True)
class MiniProgramPrincipal:
    doctor_id: str
    channel: str
    wechat_openid: Optional[str]


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + padding).encode("utf-8"))


def _token_secret() -> str:
    return (os.environ.get("MINIPROGRAM_TOKEN_SECRET") or "dev-miniprogram-secret").strip()


def _token_ttl_seconds() -> int:
    raw = (os.environ.get("MINIPROGRAM_TOKEN_TTL_SECONDS") or "604800").strip()
    try:
        return max(60, int(raw))
    except (TypeError, ValueError):
        return 604800


def issue_miniprogram_token(
    doctor_id: str,
    *,
    channel: str = "wechat_mini",
    wechat_openid: Optional[str] = None,
) -> Dict[str, object]:
    now = int(time.time())
    ttl = _token_ttl_seconds()
    payload = {
        "sub": doctor_id,
        "channel": channel,
        "wechat_openid": wechat_openid,
        "iat": now,
        "exp": now + ttl,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_part = _b64url_encode(payload_json)
    sig = hmac.new(_token_secret().encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{payload_part}.{sig}"
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ttl,
    }


def verify_miniprogram_token(token: str) -> MiniProgramPrincipal:
    token_value = (token or "").strip()
    if not token_value or "." not in token_value:
        raise MiniProgramAuthError("Invalid token format")

    payload_part, sig = token_value.rsplit(".", 1)
    expected_sig = hmac.new(
        _token_secret().encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise MiniProgramAuthError("Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except Exception as exc:  # pragma: no cover
        raise MiniProgramAuthError("Invalid token payload") from exc

    doctor_id = str(payload.get("sub") or "").strip()
    channel = str(payload.get("channel") or "").strip() or "wechat_mini"
    if not doctor_id:
        raise MiniProgramAuthError("Token subject missing")

    now = int(time.time())
    exp_raw = payload.get("exp")
    try:
        exp = int(exp_raw)
    except (TypeError, ValueError):
        raise MiniProgramAuthError("Token exp invalid")
    if exp <= now:
        raise MiniProgramAuthError("Token expired")

    wechat_openid_raw = payload.get("wechat_openid")
    wechat_openid = None if wechat_openid_raw in (None, "") else str(wechat_openid_raw)
    return MiniProgramPrincipal(
        doctor_id=doctor_id,
        channel=channel,
        wechat_openid=wechat_openid,
    )


def parse_bearer_token(authorization: Optional[str]) -> str:
    header = (authorization or "").strip()
    if not header:
        raise MiniProgramAuthError("Missing Authorization header")

    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise MiniProgramAuthError("Authorization must be Bearer <token>")
    return parts[1].strip()
