from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services.auth.miniprogram_auth import issue_miniprogram_token

import routers.miniprogram as mini
import routers.records as records


def _principal_header() -> str:
    token_data = issue_miniprogram_token(
        "wxmini_openid_case_1",
        channel="wechat_mini",
        wechat_openid="openid_case_1",
    )
    return f"Bearer {token_data['access_token']}"


def test_require_mini_principal_ok():
    with patch.dict("os.environ", {"MINIPROGRAM_TOKEN_SECRET": "mini-route-secret"}, clear=False):
        token_data = issue_miniprogram_token("wxmini_openid_a", channel="wechat_mini")
        principal = mini._require_mini_principal(f"Bearer {token_data['access_token']}")
    assert principal.doctor_id == "wxmini_openid_a"


def test_require_mini_principal_invalid_token_returns_generic_401():
    with pytest.raises(HTTPException) as exc:
        mini._require_mini_principal("Bearer invalid-token")
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid authorization token"


async def test_mini_chat_injects_doctor_id():
    expected = records.ChatResponse(reply="ok", record=None)
    with patch.dict("os.environ", {"MINIPROGRAM_TOKEN_SECRET": "mini-route-secret-2"}, clear=False), patch(
        "routers.miniprogram.records_router._chat_for_doctor",
        new=AsyncMock(return_value=expected),
    ) as chat_mock:
        out = await mini.mini_chat(
            mini.MiniChatInput(text="你好"),
            principal=mini._require_mini_principal(_principal_header()),
        )

    assert out.reply == "ok"
    called_body = chat_mock.await_args.args[0]
    assert called_body.doctor_id == "wxmini_openid_case_1"
    assert called_body.text == "你好"


async def test_mini_tasks_forward_to_tasks_router():
    fake_out = []
    with patch.dict("os.environ", {"MINIPROGRAM_TOKEN_SECRET": "mini-route-secret-3"}, clear=False), patch(
        "routers.miniprogram.tasks_router._get_tasks_for_doctor",
        new=AsyncMock(return_value=fake_out),
    ) as task_mock:
        out = await mini.mini_tasks(
            status="pending",
            principal=mini._require_mini_principal(_principal_header()),
        )

    assert out == []
    assert task_mock.await_args.kwargs["doctor_id"] == "wxmini_openid_case_1"
    assert task_mock.await_args.kwargs["status"] == "pending"
