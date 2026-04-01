"""
Web invite login and invite code management endpoints.
"""

from __future__ import annotations

import secrets
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Doctor, InviteCode
from db.crud import link_mini_openid
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class InviteLoginInput(BaseModel):
    code: str
    specialty: Optional[str] = None
    # Optional: WeChat mini app js_code to link this doctor's mini openid.
    js_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Doctor upsert helpers (invite / web flow)
# ---------------------------------------------------------------------------

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
    """Validate invite code and return (doctor_id, doctor_name, new_doctor_id_or_None).

    Multi-use codes (max_uses > 1): always create a new doctor per login.
    Single-use codes (max_uses == 1): bind doctor_id on first use, reuse on subsequent.
    """
    from channels.web.auth.routes import _invite_is_usable
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        invite = (
            await session.execute(select(InviteCode).where(InviteCode.code == code).limit(1))
        ).scalar_one_or_none()
        if invite is None or not _invite_is_usable(invite, now):
            raise HTTPException(status_code=401, detail="Invalid or inactive invite code")

        is_multi_use = (invite.max_uses or 1) > 1

        if is_multi_use:
            # Multi-use beta code: every login creates a fresh doctor
            new_doctor_id = f"inv_{secrets.token_urlsafe(8)}"
            return new_doctor_id, invite.doctor_name, new_doctor_id

        # Single-use code: reuse bound doctor_id or create new
        new_doctor_id = None
        if invite.doctor_id is None:
            new_doctor_id = f"inv_{secrets.token_urlsafe(8)}"
        doctor_id = invite.doctor_id or new_doctor_id
        return doctor_id, invite.doctor_name, new_doctor_id


async def _bind_new_doctor_to_invite(code: str, new_doctor_id: str) -> str:
    """Write new_doctor_id back to invite code row. Returns final doctor_id (may differ on race).

    Multi-use codes: only increment used_count, never bind doctor_id.
    Single-use codes: bind doctor_id on first use.
    """
    from channels.web.auth.routes import _invite_is_usable
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        invite_row = (
            await session.execute(
                select(InviteCode).where(InviteCode.code == code).limit(1).with_for_update()
            )
        ).scalar_one_or_none()
        if invite_row is None or not _invite_is_usable(invite_row, now):
            raise HTTPException(status_code=401, detail="Invite code expired or usage limit reached")

        is_multi_use = (invite_row.max_uses or 1) > 1
        invite_row.used_count = (invite_row.used_count or 0) + 1

        if is_multi_use:
            # Never bind doctor_id — keep it None for next user
            await session.commit()
            return new_doctor_id

        # Single-use: bind on first use
        if invite_row.doctor_id is None:
            invite_row.doctor_id = new_doctor_id
            await session.commit()
            return new_doctor_id
        await session.commit()
        if invite_row.doctor_id != new_doctor_id:
            return invite_row.doctor_id
    return new_doctor_id


async def _link_mini_openid_from_jscode(js_code: str, doctor_id: str) -> Optional[str]:
    """Exchange js_code for openid and link it to the doctor. Returns openid or None on error."""
    from channels.web.auth.miniapp import _fetch_wechat_openid
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/invite/login")
async def invite_login(body: InviteLoginInput):
    from channels.web.auth.routes import WebLoginResponse
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

    from infra.auth.unified import issue_token
    access_token = issue_token(role="doctor", doctor_id=doctor_id)
    channel = "wechat_mini" if mini_openid else "app"

    from utils.log import safe_create_task
    safe_create_task(audit(doctor_id, "LOGIN", resource_type="invite_code", resource_id=code))

    return WebLoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=604800,
        doctor_id=doctor_id,
        channel=channel,
    )
