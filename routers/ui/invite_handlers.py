"""
邀请码管理端点：仅限管理员操作的邀请码生成、列表和吊销接口。
"""

from __future__ import annotations

import re
import secrets as _secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import InviteCode
from routers.ui._utils import _fmt_ts, _require_ui_admin_access

router = APIRouter(tags=["ui"])


class InviteCodeCreate(BaseModel):
    doctor_name: Optional[str] = None
    code: Optional[str] = None  # custom code; auto-generated if omitted
    expires_at: Optional[str] = None  # ISO-8601 datetime string
    max_uses: Optional[int] = None  # None → default (1)


class InviteCodeRow(BaseModel):
    code: str
    doctor_id: Optional[str]  # None until first login
    doctor_name: Optional[str]
    active: bool
    created_at: str
    expires_at: Optional[str]
    max_uses: int
    used_count: int


@router.get("/api/admin/invite-codes")
async def list_invite_codes(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(InviteCode).order_by(InviteCode.created_at.desc()))
        ).scalars().all()
    return {
        "items": [
            InviteCodeRow(
                code=r.code,
                doctor_id=r.doctor_id,
                doctor_name=r.doctor_name,
                active=bool(r.active),
                created_at=_fmt_ts(r.created_at),
                expires_at=_fmt_ts(r.expires_at) if r.expires_at else None,
                max_uses=r.max_uses or 1,
                used_count=r.used_count or 0,
            )
            for r in rows
        ]
    }


def _validate_or_generate_code(body: InviteCodeCreate) -> str:
    """Validate a custom invite code or generate one automatically."""
    if body.code:
        custom = body.code.strip()
        if not re.match(r'^[A-Za-z0-9_-]{4,32}$', custom):
            raise HTTPException(
                status_code=422,
                detail="邀请码只能包含字母、数字、- 和 _，长度 4-32 位",
            )
        return custom
    return _secrets.token_urlsafe(9)  # 12-char URL-safe string


@router.post("/api/admin/invite-codes")
async def create_invite_code(
    body: InviteCodeCreate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    code = _validate_or_generate_code(body)
    doctor_name = (body.doctor_name or "").strip() or None
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(InviteCode).where(InviteCode.code == code).limit(1))
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="该邀请码已存在")
        expires_at = None
        if body.expires_at:
            try:
                expires_at = datetime.fromisoformat(body.expires_at)
            except ValueError:
                raise HTTPException(status_code=422, detail="expires_at must be ISO-8601")
        max_uses = body.max_uses if body.max_uses is not None else 1
        session.add(InviteCode(
            code=code,
            doctor_id=None,  # assigned on first login
            doctor_name=doctor_name,
            active=1,
            created_at=now,
            expires_at=expires_at,
            max_uses=max_uses,
        ))
        await session.commit()
    return InviteCodeRow(
        code=code, doctor_id=None, doctor_name=doctor_name,
        active=True, created_at=_fmt_ts(now),
        expires_at=_fmt_ts(expires_at) if expires_at else None,
        max_uses=max_uses, used_count=0,
    )


@router.delete("/api/admin/invite-codes/{code}")
async def revoke_invite_code(
    code: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as session:
        invite = (
            await session.execute(select(InviteCode).where(InviteCode.code == code).limit(1))
        ).scalar_one_or_none()
        if invite is None:
            raise HTTPException(status_code=404, detail="Invite code not found")
        invite.active = 0
        await session.commit()
    return {"ok": True}
