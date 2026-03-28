"""
认证路由：处理 WeCom OAuth 回调并签发内部 JWT 访问令牌。

Hub module — includes sub-routers from:
  auth_miniapp  — WeChat mini-program login + openid linking
  auth_invite   — web invite login + invite code management

Shared helpers and models are defined here and imported by sub-modules.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.crud import get_doctor_by_id
from db.engine import AsyncSessionLocal
from db.models import Doctor, InviteCode

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Shared Pydantic models (re-exported for sub-modules)
# ---------------------------------------------------------------------------

class WebLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    doctor_id: str
    channel: str


class MeResponse(BaseModel):
    doctor_id: str
    channel: str
    name: Optional[str] = None
    wechat_openid: Optional[str] = None


# ---------------------------------------------------------------------------
# Shared helper — used by both auth_miniapp and auth_invite
# ---------------------------------------------------------------------------

def _invite_is_usable(invite: InviteCode, now: datetime) -> bool:
    """Check active flag, expiry, and usage limits."""
    if not invite.active:
        return False
    if invite.expires_at is not None and invite.expires_at <= now:
        return False
    if invite.max_uses and (invite.used_count or 0) >= invite.max_uses:
        return False
    return True


# ---------------------------------------------------------------------------
# /me endpoint
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
async def auth_me(authorization: Optional[str] = Header(default=None)) -> MeResponse:
    from infra.auth.unified import extract_token, verify_token
    try:
        token = extract_token(authorization)
        payload = verify_token(token)
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger("auth").warning("[Auth] /me token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    doctor_id = payload.get("doctor_id") or payload.get("sub") or ""
    if not doctor_id:
        raise HTTPException(status_code=401, detail="Token missing doctor_id")

    # Fetch display name from DB
    doctor_name: Optional[str] = None
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(Doctor).where(Doctor.doctor_id == str(doctor_id)).limit(1))
        ).scalar_one_or_none()
        if row:
            doctor_name = row.name

    return MeResponse(
        doctor_id=str(doctor_id),
        channel="web",
        name=doctor_name,
        wechat_openid=None,
    )


# ---------------------------------------------------------------------------
# Include sub-routers
# ---------------------------------------------------------------------------

from channels.web.auth_miniapp import router as _miniapp_router  # noqa: E402
from channels.web.auth_invite import router as _invite_router    # noqa: E402

router.include_router(_miniapp_router)
router.include_router(_invite_router)


# ---------------------------------------------------------------------------
# Re-exports (keep public API stable for any external importers)
# ---------------------------------------------------------------------------

from channels.web.auth_miniapp import (  # noqa: F401
    MiniProgramLoginInput,
    MiniProgramLoginResponse,
    _fetch_wechat_openid,
    _upsert_mini_doctor,
)
from channels.web.auth_invite import (  # noqa: F401
    InviteLoginInput,
    _upsert_web_doctor,
    _resolve_invite_doctor_id,
    _bind_new_doctor_to_invite,
    _link_mini_openid_from_jscode,
)
