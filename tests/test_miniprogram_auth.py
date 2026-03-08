from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import routers.auth as auth_router
from db.models import Doctor
from services.auth.miniprogram_auth import (
    MiniProgramAuthError,
    issue_miniprogram_token,
    parse_bearer_token,
    verify_miniprogram_token,
)


async def test_wechat_mini_login_with_mock_code_inserts_doctor(session_factory):
    with patch("routers.auth.AsyncSessionLocal", session_factory), patch.dict(
        "os.environ",
        {
            "WECHAT_MINI_ALLOW_MOCK_CODE": "true",
            "MINIPROGRAM_TOKEN_SECRET": "test-secret",
            "MINIPROGRAM_TOKEN_TTL_SECONDS": "3600",
        },
        clear=False,
    ):
        resp = await auth_router.wechat_mini_login(
            auth_router.MiniProgramLoginInput(code="mock:openid_u_1", doctor_name="Dr X")
        )

    assert resp.wechat_openid == "openid_u_1"
    assert resp.channel == "wechat_mini"
    assert resp.doctor_id == "wxmini_openid_u_1"
    assert resp.access_token

    async with session_factory() as session:
        doctor = (
            await session.execute(
                select(Doctor).where(Doctor.doctor_id == "wxmini_openid_u_1").limit(1)
            )
        ).scalar_one_or_none()
    assert doctor is not None
    assert doctor.channel == "wechat_mini"
    assert doctor.wechat_user_id == "openid_u_1"


async def test_auth_me_reads_bearer_token():
    with patch.dict(
        "os.environ",
        {
            "MINIPROGRAM_TOKEN_SECRET": "test-secret-2",
            "MINIPROGRAM_TOKEN_TTL_SECONDS": "3600",
        },
        clear=False,
    ):
        token_data = issue_miniprogram_token(
            "wxmini_openid_u_2",
            channel="wechat_mini",
            wechat_openid="openid_u_2",
        )
        me = await auth_router.auth_me(authorization=f"Bearer {token_data['access_token']}")

    assert me.doctor_id == "wxmini_openid_u_2"
    assert me.channel == "wechat_mini"
    assert me.wechat_openid == "openid_u_2"


async def test_auth_me_invalid_token_returns_generic_401():
    with pytest.raises(HTTPException) as exc:
        await auth_router.auth_me(authorization="Bearer invalid-token")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid authorization token"


def test_parse_bearer_token_validation():
    assert parse_bearer_token("Bearer abc") == "abc"
    with pytest.raises(MiniProgramAuthError):
        parse_bearer_token(None)
    with pytest.raises(MiniProgramAuthError):
        parse_bearer_token("Token abc")


def test_verify_miniprogram_token_tamper_and_expired():
    with patch.dict(
        "os.environ",
        {
            "MINIPROGRAM_TOKEN_SECRET": "test-secret-3",
            "MINIPROGRAM_TOKEN_TTL_SECONDS": "3600",
        },
        clear=False,
    ):
        token = issue_miniprogram_token("wxmini_openid_u_3", channel="wechat_mini")["access_token"]
        principal = verify_miniprogram_token(token)
        assert principal.doctor_id == "wxmini_openid_u_3"

        with pytest.raises(MiniProgramAuthError):
            verify_miniprogram_token(token + "x")

        with patch("services.auth.miniprogram_auth.time.time", return_value=99999999999):
            with pytest.raises(MiniProgramAuthError):
                verify_miniprogram_token(token)
