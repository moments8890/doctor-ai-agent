"""
WeChat mini-program login and openid linking endpoints.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud import get_doctor_by_mini_openid, get_doctor_by_id
from db.engine import AsyncSessionLocal, get_db
from db.models import Doctor, InviteCode
from infra.auth.wechat_id_hash import hash_wechat_id
from infra.auth.rate_limit import enforce_doctor_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class MiniProgramLoginInput(BaseModel):
    code: str
    doctor_name: Optional[str] = None
    # Optional: link this mini openid to an existing KF doctor via invite code.
    invite_code: Optional[str] = None


class MiniProgramLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    doctor_id: str
    channel: str


# ---------------------------------------------------------------------------
# WeChat API helpers
# ---------------------------------------------------------------------------

def _wechat_mini_app_id() -> str:
    return (os.environ.get("WECHAT_MINI_APP_ID") or "").strip()


def _wechat_mini_secret() -> str:
    return (os.environ.get("WECHAT_MINI_APP_SECRET") or "").strip()


def _allow_mock_codes() -> bool:
    from infra.auth import is_production
    if is_production():
        return False  # hard-disabled in production regardless of flag
    return (os.environ.get("WECHAT_MINI_ALLOW_MOCK_CODE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _fetch_wechat_openid(js_code: str) -> str:
    if _allow_mock_codes() and js_code.startswith("mock:"):
        openid = js_code.split(":", 1)[1].strip()
        if openid:
            return openid

    appid = _wechat_mini_app_id()
    secret = _wechat_mini_secret()
    if not appid or not secret:
        raise HTTPException(status_code=503, detail="WeChat authentication service unavailable")

    params = {
        "appid": appid,
        "secret": secret,
        "js_code": js_code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get("https://api.weixin.qq.com/sns/jscode2session", params=params)
    resp.raise_for_status()
    payload = resp.json()

    errcode = int(payload.get("errcode") or 0)
    if errcode != 0:
        errmsg = str(payload.get("errmsg") or "unknown")
        logging.getLogger("auth").warning(
            "[Auth] code2session failed: errcode=%s errmsg=%s", errcode, errmsg,
        )
        raise HTTPException(status_code=401, detail="WeChat login failed — please try again")

    openid = str(payload.get("openid") or "").strip()
    if not openid:
        raise HTTPException(status_code=401, detail="code2session missing openid")
    return openid


# ---------------------------------------------------------------------------
# Doctor upsert helpers (mini-program flow)
# ---------------------------------------------------------------------------

async def _try_link_via_invite(
    session,
    openid: str,
    invite_code: str,
    doctor_name: Optional[str],
    now: datetime,
) -> Optional[str]:
    """Attempt to link openid to an existing doctor via invite code. Returns doctor_id or None."""
    # TODO: wechat binding now lives in DoctorWechat table — migrate this function to upsert there
    invite = (
        await session.execute(
            select(InviteCode).where(InviteCode.code == invite_code).limit(1)
        )
    ).scalar_one_or_none()
    from channels.web.auth.routes import _invite_is_usable
    if invite is None or not _invite_is_usable(invite, now):
        return None
    target = (
        await session.execute(
            select(Doctor).where(Doctor.doctor_id == invite.doctor_id).limit(1)
        )
    ).scalar_one_or_none()
    if target is None:
        return None
    # TODO: write mini_openid to DoctorWechat table instead of Doctor row
    from db.models.doctor_wechat import DoctorWechat
    wechat_row = (
        await session.execute(
            select(DoctorWechat).where(DoctorWechat.doctor_id == target.doctor_id).limit(1)
        )
    ).scalar_one_or_none()
    if wechat_row is None:
        session.add(DoctorWechat(doctor_id=target.doctor_id, mini_openid=hash_wechat_id(openid)))
    else:
        wechat_row.mini_openid = hash_wechat_id(openid)
    target.updated_at = now
    if doctor_name and not target.name:
        target.name = doctor_name
    invite.used_count = (invite.used_count or 0) + 1
    await session.commit()
    return invite.doctor_id


async def _upsert_mini_doctor_new(
    session,
    openid: str,
    doctor_name: Optional[str],
    now: datetime,
) -> str:
    """Create or touch the fallback wxmini_ doctor row. Returns doctor_id."""
    # TODO: channel/wechat binding now live in DoctorWechat table — migrate fully
    from db.models.doctor_wechat import DoctorWechat
    doctor_id = f"wxmini_{openid}"
    existing_by_id = (
        await session.execute(select(Doctor).where(Doctor.doctor_id == doctor_id).limit(1))
    ).scalar_one_or_none()
    hashed = hash_wechat_id(openid)
    if existing_by_id is None:
        session.add(Doctor(doctor_id=doctor_id, name=doctor_name, created_at=now, updated_at=now))
        await session.flush()
        session.add(DoctorWechat(doctor_id=doctor_id, wechat_user_id=hashed, mini_openid=hashed))
    else:
        existing_by_id.updated_at = now
        if doctor_name and not existing_by_id.name:
            existing_by_id.name = doctor_name
        wechat_row = (
            await session.execute(
                select(DoctorWechat).where(DoctorWechat.doctor_id == doctor_id).limit(1)
            )
        ).scalar_one_or_none()
        if wechat_row is None:
            session.add(DoctorWechat(doctor_id=doctor_id, wechat_user_id=hashed, mini_openid=hashed))
        else:
            wechat_row.wechat_user_id = hashed
            if not wechat_row.mini_openid:
                wechat_row.mini_openid = hashed
    await session.commit()
    return doctor_id


async def _upsert_mini_doctor(
    openid: str,
    doctor_name: Optional[str],
    invite_code: Optional[str] = None,
) -> str:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        # 1. Already linked by mini_openid — covers re-logins after linking.
        existing_by_mini = await get_doctor_by_mini_openid(session, openid)
        if existing_by_mini is not None:
            existing_by_mini.updated_at = now
            if doctor_name and not existing_by_mini.name:
                existing_by_mini.name = doctor_name
            await session.commit()
            return existing_by_mini.doctor_id

        # 2. Invite code provided — link this openid to the existing doctor.
        if invite_code:
            linked_id = await _try_link_via_invite(session, openid, invite_code, doctor_name, now)
            if linked_id is not None:
                return linked_id

        # 3. Legacy fallback: find by wechat_user_id in DoctorWechat table.
        # TODO: channel field removed from Doctor — lookup via DoctorWechat.wechat_user_id
        from db.models.doctor_wechat import DoctorWechat
        wechat_row = (
            await session.execute(
                select(DoctorWechat)
                .where(DoctorWechat.wechat_user_id == hash_wechat_id(openid))
                .limit(1)
            )
        ).scalar_one_or_none()
        if wechat_row is not None:
            existing_by_wechat = await get_doctor_by_id(session, wechat_row.doctor_id)
            if existing_by_wechat is not None:
                if not wechat_row.mini_openid:
                    wechat_row.mini_openid = hash_wechat_id(openid)
                existing_by_wechat.updated_at = now
                if doctor_name and not existing_by_wechat.name:
                    existing_by_wechat.name = doctor_name
                await session.commit()
                return existing_by_wechat.doctor_id

        # 4. No existing record — create a standalone mini app doctor.
        return await _upsert_mini_doctor_new(session, openid, doctor_name, now)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/wechat-mini/login", response_model=MiniProgramLoginResponse)
async def wechat_mini_login(body: MiniProgramLoginInput) -> MiniProgramLoginResponse:
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="code is required")

    openid = await _fetch_wechat_openid(code)
    doctor_id = await _upsert_mini_doctor(openid, body.doctor_name, body.invite_code)
    enforce_doctor_rate_limit(doctor_id, scope="auth.login")
    from infra.auth.unified import issue_token
    access_token = issue_token(role="doctor", doctor_id=doctor_id)

    # Seed demo data in background (idempotent — is_seeded check prevents duplicates)
    from channels.web.auth.invite import _seed_new_doctor
    from utils.log import safe_create_task
    safe_create_task(_seed_new_doctor(doctor_id))

    return MiniProgramLoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=604800,
        doctor_id=doctor_id,
        channel="wechat_mini",
    )


@router.delete("/mini-link", status_code=204)
async def unlink_mini_openid(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove the mini_openid link from the authenticated doctor's record.

    The doctor must present a valid JWT (from either wechat_mini or app channel).
    After unlinking, future mini app logins will create a fresh wxmini_ doctor unless
    re-linked via invite code.
    """
    from infra.auth.unified import extract_token, verify_token
    try:
        token = extract_token(authorization)
        payload = verify_token(token)
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger("auth").warning("[Auth] /mini-link token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    doctor_id = payload.get("doctor_id") or payload.get("sub") or ""
    if not doctor_id:
        raise HTTPException(status_code=401, detail="Token missing doctor_id")

    row = await get_doctor_by_id(db, str(doctor_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Doctor not found")
    # Clear wechat binding from DoctorWechat table
    from db.models.doctor_wechat import DoctorWechat
    wechat_row = (
        await db.execute(
            select(DoctorWechat).where(DoctorWechat.doctor_id == str(doctor_id)).limit(1)
        )
    ).scalar_one_or_none()
    if wechat_row is not None:
        wechat_row.mini_openid = None
        wechat_row.wechat_user_id = None
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
