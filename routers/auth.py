"""
认证路由：处理 WeCom OAuth 回调并签发内部 JWT 访问令牌。
"""

from __future__ import annotations

import os
import secrets
import urllib.parse
from datetime import datetime, timezone
import logging
from typing import Optional, Tuple

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Doctor
from services.auth.miniprogram_auth import (
    MiniProgramAuthError,
    issue_miniprogram_token,
    parse_bearer_token,
    verify_miniprogram_token,
)
from services.auth.rate_limit import enforce_doctor_rate_limit

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


class WebLoginInput(BaseModel):
    doctor_id: str
    name: Optional[str] = None


class WebLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    doctor_id: str
    channel: str


class WecomLoginUrlResponse(BaseModel):
    url: str


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


async def _upsert_web_doctor(doctor_id: str, name: Optional[str]) -> None:
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
                    channel="app",
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing.updated_at = now
            if name and not existing.name:
                existing.name = name

        await session.commit()


@router.post("/web/login", response_model=WebLoginResponse)
async def web_login(body: WebLoginInput) -> WebLoginResponse:
    doctor_id = (body.doctor_id or "").strip()
    if not doctor_id:
        raise HTTPException(status_code=422, detail="doctor_id is required")

    enforce_doctor_rate_limit(doctor_id, scope="auth.login")
    await _upsert_web_doctor(doctor_id, body.name)
    token_data = issue_miniprogram_token(doctor_id, channel="app")

    return WebLoginResponse(
        access_token=str(token_data["access_token"]),
        token_type=str(token_data["token_type"]),
        expires_in=int(token_data["expires_in"]),
        doctor_id=doctor_id,
        channel="app",
    )


def _wecom_corp_id() -> str:
    return (os.environ.get("WECOM_CORP_ID") or "").strip()


def _wecom_secret() -> str:
    return (os.environ.get("WECOM_SECRET") or "").strip()


def _wecom_agent_id() -> str:
    return (os.environ.get("WECOM_AGENT_ID") or "").strip()


def _api_base_url() -> str:
    return (os.environ.get("MINIPROGRAM_API_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


async def _wecom_access_token() -> str:
    corp_id = _wecom_corp_id()
    secret = _wecom_secret()
    if not corp_id or not secret:
        raise HTTPException(status_code=500, detail="WECOM_CORP_ID/WECOM_SECRET not configured")
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": corp_id, "corpsecret": secret},
        )
    resp.raise_for_status()
    data = resp.json()
    if int(data.get("errcode") or 0) != 0:
        raise HTTPException(status_code=500, detail=f"WeCom gettoken failed: {data.get('errmsg')}")
    return str(data["access_token"])


async def _wecom_user_info(code: str) -> Tuple[str, Optional[str]]:
    """Exchange OAuth code for (user_id, display_name)."""
    access_token = await _wecom_access_token()
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/user/getuserinfo",
            params={"access_token": access_token, "code": code},
        )
    resp.raise_for_status()
    data = resp.json()
    if int(data.get("errcode") or 0) != 0:
        raise HTTPException(status_code=401, detail=f"WeCom getuserinfo failed: {data.get('errmsg')}")
    user_id = str(data.get("UserId") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="WeCom: only internal corp members are supported")

    # Attempt to fetch the display name from the user profile
    name: Optional[str] = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r2 = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/user/get",
                params={"access_token": access_token, "userid": user_id},
            )
        if r2.is_success:
            u = r2.json()
            name = str(u.get("name") or "").strip() or None
    except Exception:
        pass

    return user_id, name


async def _upsert_wecom_doctor(user_id: str, name: Optional[str]) -> str:
    doctor_id = f"wecom_{user_id}"
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
                    channel="wecom",
                    wechat_user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            existing.updated_at = now
            if name and not existing.name:
                existing.name = name
        await session.commit()
    return doctor_id


@router.get("/wecom/login-url", response_model=WecomLoginUrlResponse)
async def wecom_login_url() -> WecomLoginUrlResponse:
    corp_id = _wecom_corp_id()
    agent_id = _wecom_agent_id()
    if not corp_id or not agent_id:
        raise HTTPException(status_code=500, detail="WECOM_CORP_ID/WECOM_AGENT_ID not configured")

    callback = f"{_api_base_url()}/api/auth/wecom/callback"
    state = secrets.token_urlsafe(16)
    url = (
        "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
        f"?appid={urllib.parse.quote(corp_id)}"
        f"&agentid={urllib.parse.quote(str(agent_id))}"
        f"&redirect_uri={urllib.parse.quote(callback, safe='')}"
        f"&state={urllib.parse.quote(state)}"
    )
    return WecomLoginUrlResponse(url=url)


@router.get("/wecom/callback")
async def wecom_callback(code: str = "", state: str = "") -> RedirectResponse:
    if not code:
        return RedirectResponse(url="/login?error=missing_code")
    try:
        user_id, name = await _wecom_user_info(code)
        doctor_id = await _upsert_wecom_doctor(user_id, name)
        enforce_doctor_rate_limit(doctor_id, scope="auth.login")
        token_data = issue_miniprogram_token(doctor_id, channel="wecom")
        qs = urllib.parse.urlencode({
            "token": token_data["access_token"],
            "doctor_id": doctor_id,
            "name": name or doctor_id,
        })
        return RedirectResponse(url=f"/login?{qs}")
    except HTTPException as exc:
        return RedirectResponse(url=f"/login?error={urllib.parse.quote(str(exc.detail))}")


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
