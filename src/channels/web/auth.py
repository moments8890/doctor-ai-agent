"""
认证路由：处理 WeCom OAuth 回调并签发内部 JWT 访问令牌。
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.crud import get_doctor_by_mini_openid, get_doctor_by_id, link_mini_openid
from db.engine import AsyncSessionLocal
from db.models import Doctor, InviteCode
from infra.auth.wechat_id_hash import hash_wechat_id
from infra.observability.audit import audit
from infra.auth.miniprogram_auth import (
    MiniProgramAuthError,
    issue_miniprogram_token,
    parse_bearer_token,
    verify_miniprogram_token,
)
from infra.auth.rate_limit import enforce_doctor_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    wechat_openid: str


class WebLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    doctor_id: str
    channel: str


class InviteLoginInput(BaseModel):
    code: str
    specialty: Optional[str] = None
    # Optional: WeChat mini app js_code to link this doctor's mini openid.
    js_code: Optional[str] = None


class MeResponse(BaseModel):
    doctor_id: str
    channel: str
    name: Optional[str] = None
    wechat_openid: Optional[str] = None


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


def _invite_is_usable(invite: InviteCode, now: datetime) -> bool:
    """Check active flag, expiry, and usage limits."""
    if not invite.active:
        return False
    if invite.expires_at is not None and invite.expires_at <= now:
        return False
    if invite.max_uses and (invite.used_count or 0) >= invite.max_uses:
        return False
    return True


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


@router.post("/wechat-mini/login", response_model=MiniProgramLoginResponse)
async def wechat_mini_login(body: MiniProgramLoginInput) -> MiniProgramLoginResponse:
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="code is required")

    openid = await _fetch_wechat_openid(code)
    doctor_id = await _upsert_mini_doctor(openid, body.doctor_name, body.invite_code)
    enforce_doctor_rate_limit(doctor_id, scope="auth.login")
    token_data = issue_miniprogram_token(doctor_id, channel="wechat_mini", wechat_openid=openid)

    return MiniProgramLoginResponse(
        access_token=str(token_data["access_token"]),
        token_type=str(token_data["token_type"]),
        expires_in=int(token_data["expires_in"]),
        doctor_id=doctor_id,
        channel="wechat_mini",
        wechat_openid=openid,
    )


async def _upsert_web_doctor(doctor_id: str, name: Optional[str], specialty: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(Doctor).where(Doctor.doctor_id == doctor_id).limit(1))
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                Doctor(
                    doctor_id=doctor_id,
                    name=name,
                    specialty=specialty or None,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing.updated_at = now
            if name and not existing.name:
                existing.name = name
            if specialty:
                existing.specialty = specialty

        await session.commit()



async def _resolve_invite_doctor_id(code: str) -> tuple[str, Optional[str], Optional[str]]:
    """Validate invite code and return (doctor_id, doctor_name, new_doctor_id_or_None)."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        invite = (
            await session.execute(select(InviteCode).where(InviteCode.code == code).limit(1))
        ).scalar_one_or_none()
        if invite is None or not _invite_is_usable(invite, now):
            raise HTTPException(status_code=401, detail="Invalid or inactive invite code")
        new_doctor_id = None
        if invite.doctor_id is None:
            new_doctor_id = f"inv_{secrets.token_urlsafe(8)}"
        doctor_id = invite.doctor_id or new_doctor_id
        return doctor_id, invite.doctor_name, new_doctor_id


async def _bind_new_doctor_to_invite(code: str, new_doctor_id: str) -> str:
    """Write new_doctor_id back to invite code row. Returns final doctor_id (may differ on race)."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        invite_row = (
            await session.execute(
                select(InviteCode).where(InviteCode.code == code).limit(1).with_for_update()
            )
        ).scalar_one_or_none()
        if invite_row is None or not _invite_is_usable(invite_row, now):
            raise HTTPException(status_code=401, detail="Invite code expired or usage limit reached")
        if invite_row.doctor_id is None:
            invite_row.doctor_id = new_doctor_id
            invite_row.used_count = (invite_row.used_count or 0) + 1
            await session.commit()
            return new_doctor_id
        invite_row.used_count = (invite_row.used_count or 0) + 1
        await session.commit()
        if invite_row.doctor_id != new_doctor_id:
            return invite_row.doctor_id
    return new_doctor_id


async def _link_mini_openid_from_jscode(js_code: str, doctor_id: str) -> Optional[str]:
    """Exchange js_code for openid and link it to the doctor. Returns openid or None on error."""
    try:
        mini_openid = await _fetch_wechat_openid(js_code)
        async with AsyncSessionLocal() as session:
            await link_mini_openid(session, doctor_id, mini_openid)
        return mini_openid
    except Exception as link_err:
        logging.getLogger("auth").warning(
            "[Auth] invite/login mini openid link failed: %s", link_err
        )
        return None


@router.post("/invite/login", response_model=WebLoginResponse)
async def invite_login(body: InviteLoginInput) -> WebLoginResponse:
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="code is required")

    # Rate-limit invite code attempts BEFORE the DB lookup to prevent
    # brute-force enumeration of valid codes.
    enforce_doctor_rate_limit(code, scope="auth.invite_code", max_requests=5)

    doctor_id, doctor_name, new_doctor_id = await _resolve_invite_doctor_id(code)
    enforce_doctor_rate_limit(doctor_id, scope="auth.login")
    await _upsert_web_doctor(doctor_id, doctor_name, specialty=(body.specialty or "").strip() or None)

    if new_doctor_id:
        doctor_id = await _bind_new_doctor_to_invite(code, new_doctor_id)

    mini_openid: Optional[str] = None
    if body.js_code:
        mini_openid = await _link_mini_openid_from_jscode(body.js_code, doctor_id)

    token_data = issue_miniprogram_token(
        doctor_id,
        channel="wechat_mini" if mini_openid else "app",
        wechat_openid=mini_openid,
    )

    from utils.log import safe_create_task
    safe_create_task(audit(doctor_id, "LOGIN", resource_type="invite_code", resource_id=code))

    return WebLoginResponse(
        access_token=str(token_data["access_token"]),
        token_type=str(token_data["token_type"]),
        expires_in=int(token_data["expires_in"]),
        doctor_id=doctor_id,
        channel="wechat_mini" if mini_openid else "app",
    )


@router.delete("/mini-link", status_code=204)
async def unlink_mini_openid(authorization: Optional[str] = Header(default=None)) -> None:
    """Remove the mini_openid link from the authenticated doctor's record.

    The doctor must present a valid JWT (from either wechat_mini or app channel).
    After unlinking, future mini app logins will create a fresh wxmini_ doctor unless
    re-linked via invite code.
    """
    try:
        token = parse_bearer_token(authorization)
        principal = verify_miniprogram_token(token)
    except MiniProgramAuthError as exc:
        logging.getLogger("auth").warning("[Auth] /mini-link token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    async with AsyncSessionLocal() as session:
        row = await get_doctor_by_id(session, principal.doctor_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Doctor not found")
        # Clear wechat binding from DoctorWechat table
        from db.models.doctor_wechat import DoctorWechat
        wechat_row = (
            await session.execute(
                select(DoctorWechat).where(DoctorWechat.doctor_id == principal.doctor_id).limit(1)
            )
        ).scalar_one_or_none()
        if wechat_row is not None:
            wechat_row.mini_openid = None
            wechat_row.wechat_user_id = None
        row.updated_at = datetime.now(timezone.utc)
        await session.commit()


@router.get("/me", response_model=MeResponse)
async def auth_me(authorization: Optional[str] = Header(default=None)) -> MeResponse:
    try:
        token = parse_bearer_token(authorization)
        principal = verify_miniprogram_token(token)
    except MiniProgramAuthError as exc:
        logging.getLogger("auth").warning("[Auth] /me token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    # Fetch display name from DB
    doctor_name: Optional[str] = None
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(Doctor).where(Doctor.doctor_id == principal.doctor_id).limit(1))
        ).scalar_one_or_none()
        if row:
            doctor_name = row.name

    return MeResponse(
        doctor_id=principal.doctor_id,
        channel=principal.channel,
        name=doctor_name,
        wechat_openid=principal.wechat_openid,
    )
