from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import routers.auth as auth_router
import routers.miniprogram as mini_router
import routers.records as records_router
from services.ai.intent import Intent, IntentResult


async def test_miniprogram_login_and_chat_e2e(session_factory):
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(mini_router.router)

    with patch("routers.auth.AsyncSessionLocal", session_factory), patch.dict(
        "os.environ",
        {
            "WECHAT_MINI_ALLOW_MOCK_CODE": "true",
            "MINIPROGRAM_TOKEN_SECRET": "mini-e2e-secret",
            "MINIPROGRAM_TOKEN_TTL_SECONDS": "7200",
        },
        clear=False,
    ), patch(
        "routers.miniprogram.records_router._chat_for_doctor",
        new=AsyncMock(return_value=records_router.ChatResponse(reply="mini ok", record=None)),
    ) as chat_mock:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            login_resp = await client.post(
                "/api/auth/wechat-mini/login",
                json={"code": "mock:openid_mini_e2e_1", "doctor_name": "Dr Mini"},
            )
            assert login_resp.status_code == 200
            login_body = login_resp.json()
            assert login_body["doctor_id"] == "wxmini_openid_mini_e2e_1"
            assert login_body["access_token"]

            token = login_body["access_token"]
            me_resp = await client.get(
                "/api/mini/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert me_resp.status_code == 200
            assert me_resp.json()["doctor_id"] == "wxmini_openid_mini_e2e_1"

            chat_resp = await client.post(
                "/api/mini/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"text": "你好", "history": []},
            )
            assert chat_resp.status_code == 200
            assert chat_resp.json()["reply"] == "mini ok"

    called_input = chat_mock.await_args.args[0]
    assert called_input.doctor_id == "wxmini_openid_mini_e2e_1"


async def test_miniprogram_real_life_10_turn_chat_e2e(session_factory):
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(mini_router.router)

    scripted_turns = [
        {
            "user": "你好，我是今天门诊值班医生。",
            "reply": "您好，我可以协助建档、记录病历和查询随访任务。",
            "keyword": "协助",
        },
        {
            "user": "新建患者 张建国 男 58岁。",
            "reply": "已为患者【张建国】建档（男、58岁）。",
            "keyword": "建档",
        },
        {
            "user": "张建国，反复胸痛2天，活动后加重。",
            "reply": "已记录主诉：反复胸痛2天，活动后加重。",
            "keyword": "主诉",
        },
        {
            "user": "补充：既往高血压10年，长期口服缬沙坦。",
            "reply": "已补充既往史与用药信息。",
            "keyword": "既往史",
        },
        {
            "user": "今天心电图提示V1-V4导联ST段压低。",
            "reply": "已记录辅助检查：V1-V4导联ST段压低。",
            "keyword": "辅助检查",
        },
        {
            "user": "初步考虑不稳定型心绞痛，继续监测肌钙蛋白。",
            "reply": "已更新诊断与后续检查计划。",
            "keyword": "诊断",
        },
        {
            "user": "给他安排三天后复诊提醒。",
            "reply": "已创建随访任务：3天后复诊。",
            "keyword": "随访任务",
        },
        {
            "user": "查看他的最近病历。",
            "reply": "已返回患者【张建国】最近病历摘要。",
            "keyword": "最近病历",
        },
        {
            "user": "再查一下我当前待办任务。",
            "reply": "当前有1条待办任务：张建国复诊提醒。",
            "keyword": "待办任务",
        },
        {
            "user": "好的，今天先这样，谢谢。",
            "reply": "不客气，需要时随时继续补录病历。",
            "keyword": "随时",
        },
    ]

    state = {"turn": 0}

    async def _fake_records_chat(chat_input, doctor_id):
        idx = state["turn"]
        expected = scripted_turns[idx]
        assert doctor_id == "wxmini_openid_mini_e2e_chat10"
        assert chat_input.doctor_id == "wxmini_openid_mini_e2e_chat10"
        assert chat_input.text == expected["user"]
        # Mini endpoint should pass through full client-provided history.
        assert len(chat_input.history) == idx * 2
        state["turn"] = idx + 1
        return records_router.ChatResponse(reply=expected["reply"], record=None)

    with patch("routers.auth.AsyncSessionLocal", session_factory), patch.dict(
        "os.environ",
        {
            "WECHAT_MINI_ALLOW_MOCK_CODE": "true",
            "MINIPROGRAM_TOKEN_SECRET": "mini-e2e-secret-chat10",
            "MINIPROGRAM_TOKEN_TTL_SECONDS": "7200",
        },
        clear=False,
    ), patch(
        "routers.miniprogram.records_router._chat_for_doctor",
        new=AsyncMock(side_effect=_fake_records_chat),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            login_resp = await client.post(
                "/api/auth/wechat-mini/login",
                json={"code": "mock:openid_mini_e2e_chat10", "doctor_name": "Dr Chat10"},
            )
            assert login_resp.status_code == 200
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            history = []
            for turn in scripted_turns:
                resp = await client.post(
                    "/api/mini/chat",
                    headers=headers,
                    json={"text": turn["user"], "history": history},
                )
                assert resp.status_code == 200
                body = resp.json()
                reply = str(body.get("reply") or "")
                assert turn["keyword"] in reply
                history.append({"role": "user", "content": turn["user"]})
                history.append({"role": "assistant", "content": reply})

    assert state["turn"] == 10


async def test_miniprogram_real_life_10_turn_chat_live_records_path_e2e(session_factory):
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(mini_router.router)

    turns = [
        "你好，我是值班医生。",
        "今天门诊排班挺满的。",
        "下午我打算先做随访整理。",
        "提醒我晚点回顾本周工作。",
        "这个页面响应挺快。",
        "我准备测试十轮对话稳定性。",
        "目前历史消息累积正常。",
        "请继续返回简单确认消息。",
        "第九条消息用于验证链路。",
        "好的，最后一条结束测试。",
    ]

    async def _fake_dispatch(text: str, history=None):
        return IntentResult(intent=Intent.unknown, chat_reply="收到：" + text)

    with patch("routers.auth.AsyncSessionLocal", session_factory), patch(
        "routers.records.AsyncSessionLocal", session_factory
    ), patch.dict(
        "os.environ",
        {
            "WECHAT_MINI_ALLOW_MOCK_CODE": "true",
            "MINIPROGRAM_TOKEN_SECRET": "mini-e2e-secret-live10",
            "MINIPROGRAM_TOKEN_TTL_SECONDS": "7200",
        },
        clear=False,
    ), patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(side_effect=_fake_dispatch),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            login_resp = await client.post(
                "/api/auth/wechat-mini/login",
                json={"code": "mock:openid_mini_e2e_live10", "doctor_name": "Dr Live10"},
            )
            assert login_resp.status_code == 200
            token = login_resp.json()["access_token"]
            headers = {"Authorization": "Bearer {0}".format(token)}

            history = []
            for idx, text in enumerate(turns):
                resp = await client.post(
                    "/api/mini/chat",
                    headers=headers,
                    json={"text": text, "history": history},
                )
                assert resp.status_code == 200
                reply = str(resp.json().get("reply") or "")
                assert reply  # any non-empty reply is acceptable
                history.append({"role": "user", "content": text})
                history.append({"role": "assistant", "content": reply})

                me_resp = await client.get("/api/mini/me", headers=headers)
                assert me_resp.status_code == 200
                assert me_resp.json()["doctor_id"] == "wxmini_openid_mini_e2e_live10"
                assert len(history) == (idx + 1) * 2
