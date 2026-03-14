"""
微信小程序登录授权：code 换 session_key、用户信息解密和 JWT 令牌签发。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import jwt


class MiniProgramAuthError(ValueError):
    pass


@dataclass(frozen=True)
class MiniProgramPrincipal:
    doctor_id: str
    channel: str
    wechat_openid: Optional[str]


def _token_secret() -> str:
    secret = os.environ.get("MINIPROGRAM_TOKEN_SECRET", "").strip()
    if not secret or secret == "dev-miniprogram-secret":
        from services.auth import is_production
        if is_production():
            raise RuntimeError(
                "MINIPROGRAM_TOKEN_SECRET must be set to a strong random "
                "value in production (not the dev default)."
            )
        secret = "dev-miniprogram-secret"
    return secret


def assert_auth_config() -> None:
    """Call at startup to fail fast if auth secrets are missing in production."""
    _token_secret()


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
    token = jwt.encode(payload, _token_secret(), algorithm="HS256")
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ttl,
    }


def verify_miniprogram_token(token: str) -> MiniProgramPrincipal:
    token_value = (token or "").strip()
    if not token_value:
        raise MiniProgramAuthError("Invalid token format")

    try:
        payload = jwt.decode(
            token_value,
            _token_secret(),
            algorithms=["HS256"],
            # PyJWT's built-in exp check uses datetime.now() which is hard to
            # patch in tests.  We add a leeway of 0 so PyJWT still rejects
            # grossly expired tokens, and perform a manual time.time() check
            # below so tests can inject a clock via patch("time.time").
        )
    except jwt.ExpiredSignatureError:
        raise MiniProgramAuthError("Token expired")
    except jwt.InvalidTokenError:
        raise MiniProgramAuthError("Invalid token")

    doctor_id = str(payload.get("sub") or "").strip()
    if not doctor_id:
        raise MiniProgramAuthError("Token subject missing")

    # Secondary expiry check using patchable time.time() for test control.
    now = int(time.time())
    exp_raw = payload.get("exp")
    try:
        exp = int(exp_raw)
    except (TypeError, ValueError):
        raise MiniProgramAuthError("Token exp invalid")
    if exp <= now:
        raise MiniProgramAuthError("Token expired")

    channel = str(payload.get("channel") or "").strip() or "wechat_mini"

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
