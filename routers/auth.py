from __future__ import annotations

import os
from datetime import datetime, timezone
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Doctor
from services.miniprogram_auth import (
    MiniProgramAuthError,
    issue_miniprogram_token,
    parse_bearer_token,
    verify_miniprogram_token,
)
from services.rate_limit import enforce_doctor_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class MiniProgramLoginInput(BaseModel):
    code: str
    doctor_name: Optional[str] = None


class MiniProgramLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    doctor_id: str
    channel: str
    wechat_openid: str


class MeResponse(BaseModel):
    doctor_id: str
    channel: str
    wechat_openid: Optional[str] = None


def _wechat_mini_app_id() -> str:
    return (os.environ.get("WECHAT_MINI_APP_ID") or "").strip()


def _wechat_mini_secret() -> str:
    return (os.environ.get("WECHAT_MINI_APP_SECRET") or "").strip()


def _allow_mock_codes() -> bool:
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
        raise HTTPException(status_code=500, detail="WECHAT_MINI_APP_ID/WECHAT_MINI_APP_SECRET not configured")

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
        raise HTTPException(status_code=401, detail=f"code2session failed: errcode={errcode}, errmsg={errmsg}")

    openid = str(payload.get("openid") or "").strip()
    if not openid:
        raise HTTPException(status_code=401, detail="code2session missing openid")
    return openid


async def _upsert_mini_doctor(openid: str, doctor_name: Optional[str]) -> str:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        existing_by_wechat = (
            await session.execute(
                select(Doctor)
                .where(Doctor.channel == "wechat_mini", Doctor.wechat_user_id == openid)
                .limit(1)
            )
        ).scalar_one_or_none()

        if existing_by_wechat is not None:
            existing_by_wechat.updated_at = now
            if doctor_name and not existing_by_wechat.name:
                existing_by_wechat.name = doctor_name
            await session.commit()
            return existing_by_wechat.doctor_id

        doctor_id = f"wxmini_{openid}"
        existing_by_id = (
            await session.execute(select(Doctor).where(Doctor.doctor_id == doctor_id).limit(1))
        ).scalar_one_or_none()

        if existing_by_id is None:
            session.add(
                Doctor(
                    doctor_id=doctor_id,
                    name=doctor_name,
                    channel="wechat_mini",
                    wechat_user_id=openid,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing_by_id.updated_at = now
            existing_by_id.channel = "wechat_mini"
            existing_by_id.wechat_user_id = openid
            if doctor_name and not existing_by_id.name:
                existing_by_id.name = doctor_name

        await session.commit()
        return doctor_id


@router.post("/wechat-mini/login", response_model=MiniProgramLoginResponse)
async def wechat_mini_login(body: MiniProgramLoginInput) -> MiniProgramLoginResponse:
    code = (body.code or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="code is required")

    openid = await _fetch_wechat_openid(code)
    doctor_id = await _upsert_mini_doctor(openid, body.doctor_name)
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


@router.get("/me", response_model=MeResponse)
async def auth_me(authorization: Optional[str] = Header(default=None)) -> MeResponse:
    try:
        token = parse_bearer_token(authorization)
        principal = verify_miniprogram_token(token)
    except MiniProgramAuthError as exc:
        logging.getLogger("auth").warning("[Auth] /me token validation failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    return MeResponse(
        doctor_id=principal.doctor_id,
        channel=principal.channel,
        wechat_openid=principal.wechat_openid,
    )
