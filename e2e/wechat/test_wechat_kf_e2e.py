"""微信客服（WeCom KF）端到端测试（callback/sync_msg 路径）。

覆盖目标：
- 通过 WeCom KF sync payload 重跑真实医生笔记场景。
- 验证消息接入 -> 意图路由 -> DB 持久化 -> KF 回复全链路。
- 验证 KF 文档中 image/voice/video 媒体 payload 形态均被正确处理。

WeChat KF end-to-end style tests (callback/sync_msg path).

Coverage goals:
- Reuse real-world doctor note scenarios through WeCom KF sync payloads.
- Validate message ingestion -> intent routing -> DB persistence -> KF reply.
- Validate media payload shapes from KF docs (`image/voice/video`) are handled.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import routers.wechat as wechat
from db.crud import find_patient_by_name, get_records_for_patient
from services.ai.intent import Intent, IntentResult
from tests.fixtures.realworld_cases import REALWORLD_SCENARIOS


def _extract_name(text: str) -> Optional[str]:
    m = re.match(r"^\s*([\u4e00-\u9fff]{2,4})", text or "")
    if m:
        return m.group(1)
    return None


def _normalize_chief(text: str) -> str:
    normalized = text.replace("chest pain", "胸痛").replace("Chest pain", "胸痛")
    normalized = normalized.replace("stmei", "STEMI").replace("pc1", "PCI")
    return normalized


def _extract_treatment(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(k in text for k in ["拟", "建议", "继续", "予", "优化", "治疗"]):
        return "按医嘱继续治疗"
    if "plan" in lowered:
        return "按计划处理"
    return None


def _extract_follow_up(text: str) -> Optional[str]:
    lowered = text.lower()
    if "复查" in text or "follow-up" in lowered or "follow up" in lowered:
        return "按计划复查"
    return None


async def _fake_dispatch(text: str, history: Optional[List[Dict[str, str]]] = None) -> IntentResult:
    name = _extract_name(text) or "未命名患者"
    chief = _normalize_chief(text)
    structured_fields = {
        "chief_complaint": chief,
        "diagnosis": "待评估",
        "treatment_plan": _extract_treatment(text),
        "follow_up_plan": _extract_follow_up(text),
    }
    return IntentResult(
        intent=Intent.add_record,
        patient_name=name,
        structured_fields=structured_fields,
        chat_reply="已记录。",
    )


class _Resp:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return self._payload


class _SingleResponseClient:
    def __init__(self, payload: Dict[str, Any]):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, _url: str, params: Dict[str, Any], json: Dict[str, Any]):
        return _Resp(self.payload)


async def _wait_for_awaited(mock_obj: AsyncMock, min_calls: int = 1, timeout_s: float = 1.5) -> None:
    steps = int(timeout_s / 0.01)
    for _ in range(steps):
        if mock_obj.await_count >= min_calls:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timed out waiting for async mock to be awaited")


async def _latest_record_for(session_factory, doctor_id: str, patient_name: str):
    async with session_factory() as session:
        patient = await find_patient_by_name(session, doctor_id, patient_name)
        if patient is None:
            return None, None
        records = await get_records_for_patient(session, doctor_id, patient.id)
        if not records:
            return patient, None
        return patient, records[0]


def _build_kf_text_payload(case_id: str, doctor_id: str, open_kfid: str, input_text: str) -> dict:
    """构建 WeCom KF sync_msg 文本消息 payload。"""
    return {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "msg_{0}".format(case_id),
                "external_userid": doctor_id,
                "open_kfid": open_kfid,
                "send_time": 5000,
                "msgtype": "text",
                "text": {"content": input_text},
            }
        ],
    }


async def _run_kf_event_with_mocks(session_factory, payload: dict) -> AsyncMock:
    """在 mock 环境中触发 KF 事件并等待消息发送；返回 send_mock。"""
    spawned_tasks: List[asyncio.Task] = []

    def _track_task(coro):
        task = asyncio.get_running_loop().create_task(coro)
        spawned_tasks.append(task)
        return task

    send_mock = AsyncMock()
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat._get_config", return_value={"app_id": "ww-corp", "app_secret": "sec"}), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_SingleResponseClient(payload)), \
         patch("routers.wechat.asyncio.create_task", side_effect=_track_task), \
         patch("routers.wechat.agent_dispatch", new=AsyncMock(side_effect=_fake_dispatch)), \
         patch("routers.wechat._send_customer_service_msg", new=send_mock), \
         patch("routers.wechat.maybe_compress", new=AsyncMock()), \
         patch("routers.wechat.load_context_message", new=AsyncMock(return_value=None)), \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5000)
        if spawned_tasks:
            await asyncio.gather(*spawned_tasks)
        await _wait_for_awaited(send_mock, min_calls=1)
    return send_mock


def _assert_kf_record_tokens(record, case_id: str, expected_tokens: List[str],
                              expect_no_treatment: bool) -> None:
    """断言病历字段包含期望关键词，并可选地验证 treatment_plan 为空。"""
    blob = "\n".join([
        record.chief_complaint or "",
        record.diagnosis or "",
        record.treatment_plan or "",
        record.follow_up_plan or "",
    ]).lower()
    for token in expected_tokens:
        assert token.lower() in blob, "missing token={0} case={1}".format(token, case_id)
    if expect_no_treatment:
        assert not (record.treatment_plan or "").strip()


@pytest.mark.parametrize(
    "case_id,patient_name,input_text,expected_tokens,expect_no_treatment",
    REALWORLD_SCENARIOS,
)
async def test_wecom_kf_text_realworld_matrix_e2e(
    session_factory,
    case_id: str,
    patient_name: str,
    input_text: str,
    expected_tokens: List[str],
    expect_no_treatment: bool,
):
    """Reuse all real-world cases via WeCom KF sync_msg text ingestion."""
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    doctor_id = "inttest_kf_{0}".format(case_id)
    open_kfid = "kf_{0}".format(case_id)

    payload = _build_kf_text_payload(case_id, doctor_id, open_kfid, input_text)
    await _run_kf_event_with_mocks(session_factory, payload)

    patient, record = await _latest_record_for(session_factory, doctor_id, patient_name)
    assert patient is not None, "patient not persisted for case={0}".format(case_id)
    assert record is not None, "record not persisted for case={0}".format(case_id)
    _assert_kf_record_tokens(record, case_id, expected_tokens, expect_no_treatment)


@pytest.mark.parametrize(
    "msgtype,msg_body,expected_notice",
    [
        ("image", {"image": {"media_id": "m-image-1"}}, "已收到图片，正在识别文字"),
        ("voice", {"voice": {"media_id": "m-voice-1"}}, "已收到语音，正在识别"),
        ("video", {"video": {"media_id": "m-video-1"}}, "当前暂不支持自动转写视频"),
    ],
)
async def test_wecom_kf_media_message_shapes_follow_doc(
    msgtype: str,
    msg_body: Dict[str, Any],
    expected_notice: str,
):
    """Validate `sync_msg` media payload shapes from WeCom KF docs are consumed."""
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    msg = {
        "origin": 3,
        "msgid": "media-{0}".format(msgtype),
        "external_userid": "inttest_kf_media",
        "open_kfid": "kf_media",
        "send_time": 5000,
        "msgtype": msgtype,
    }
    msg.update(msg_body)

    payload = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [msg],
    }

    send_mock = AsyncMock()
    with patch("routers.wechat._get_config", return_value={"app_id": "ww-corp", "app_secret": "sec"}), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_SingleResponseClient(payload)), \
         patch("routers.wechat._send_customer_service_msg", new=send_mock), \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5000)
        await _wait_for_awaited(send_mock, min_calls=1)

    sent_texts = [call.args[1] for call in send_mock.await_args_list if len(call.args) >= 2]
    assert any(expected_notice in text for text in sent_texts)


async def test_wecom_kf_callback_event_ack_and_triggers_sync_task():
    """`Event=kf_msg_or_event` callback should ACK success and schedule sync task."""

    class _DummyReq:
        def __init__(self, xml_text: str):
            self.query_params = {}
            self._body = xml_text.encode("utf-8")

        async def body(self):
            return self._body

    xml = (
        "<xml>"
        "<Event><![CDATA[kf_msg_or_event]]></Event>"
        "<MsgId><![CDATA[msg-evt-1]]></MsgId>"
        "<CreateTime>5000</CreateTime>"
        "</xml>"
    )

    called = {"ok": False}

    async def _fake_sync(
        expected_msgid: str = "",
        event_create_time: int = 0,
        event_token: str = "",
        event_open_kfid: str = "",
    ):
        called["ok"] = expected_msgid == "msg-evt-1" and event_create_time == 5000

    with patch("routers.wechat._get_config", return_value={"token": "t", "aes_key": "", "app_id": ""}), \
         patch("routers.wechat._handle_wecom_kf_event_bg", new=_fake_sync), \
         patch("routers.wechat.asyncio.create_task", side_effect=lambda coro: asyncio.get_running_loop().create_task(coro)):
        resp = await wechat.handle_message(_DummyReq(xml))
        await asyncio.sleep(0.02)

    assert resp.status_code == 200
    assert resp.body.decode("utf-8") == "success"
    assert called["ok"]


@pytest.mark.integration
async def test_wecom_kf_sync_msg_live_https():
    """Live HTTPS check against WeCom KF sync_msg endpoint.

    Enable explicitly with:
      WECHAT_KF_LIVE_TEST=1
      WECHAT_KF_ACCESS_TOKEN=<real_access_token>
    Optional:
      WECHAT_KF_SYNC_LIMIT=<int>   # default 1
      WECHAT_KF_SYNC_CURSOR=<str>
      WECHAT_KF_EVENT_TOKEN=<token-from-callback-event>
      WECHAT_KF_OPEN_KFID=<wkxxxxxx>
      WECHAT_KF_VOICE_FORMAT=0|1
    """
    if os.environ.get("WECHAT_KF_LIVE_TEST") != "1":
        pytest.skip("Set WECHAT_KF_LIVE_TEST=1 to run live WeCom KF sync_msg test")

    access_token = (os.environ.get("WECHAT_KF_ACCESS_TOKEN") or "").strip()
    if not access_token:
        pytest.skip("Missing WECHAT_KF_ACCESS_TOKEN for live sync_msg request")

    limit_raw = os.environ.get("WECHAT_KF_SYNC_LIMIT", "1").strip()
    try:
        limit = max(1, min(1000, int(limit_raw)))
    except ValueError:
        limit = 1

    payload: Dict[str, Any] = {"limit": limit}
    cursor = (os.environ.get("WECHAT_KF_SYNC_CURSOR") or "").strip()
    if cursor:
        payload["cursor"] = cursor
    callback_token = (os.environ.get("WECHAT_KF_EVENT_TOKEN") or "").strip()
    if callback_token:
        payload["token"] = callback_token
    open_kfid = (os.environ.get("WECHAT_KF_OPEN_KFID") or "").strip()
    if open_kfid:
        payload["open_kfid"] = open_kfid
    voice_format = (os.environ.get("WECHAT_KF_VOICE_FORMAT") or "").strip()
    if voice_format in ("0", "1"):
        payload["voice_format"] = int(voice_format)

    url = "https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, params={"access_token": access_token}, json=payload)

    assert resp.status_code == 200, "sync_msg HTTP status should be 200"
    data = resp.json()
    assert isinstance(data, dict), "sync_msg response must be JSON object"
    assert "errcode" in data, "sync_msg response should contain errcode"
