"""Tests for channel adapter implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from unittest.mock import AsyncMock, patch

import pytest

from services.domain.adapters.web_adapter import WebAdapter
from services.domain.adapters.wechat_adapter import WeChatAdapter, split_wechat_message
from services.domain.intent_handlers._types import HandlerResult
from services.domain.message import ChannelAdapter, Message


# ── Fixtures ──────────────────────────────────────────────────────────────────


@dataclass
class FakeChatInput:
    """Minimal stand-in for routers.records.ChatInput."""
    text: str = ""
    history: list = None
    doctor_id: str = "doc_001"

    def __post_init__(self):
        if self.history is None:
            self.history = []


@dataclass
class FakeHistoryMessage:
    role: str = "user"
    content: str = ""


@dataclass
class FakeWeChatMessage:
    """Minimal stand-in for wechatpy message objects."""
    content: str = ""
    source: str = "openid_123"
    type: str = "text"
    media_id: str = None
    recognition: str = None
    format: str = None


# ── Protocol conformance ──────────────────────────────────────────────────────


def test_web_adapter_is_channel_adapter():
    """WebAdapter structurally satisfies ChannelAdapter Protocol."""
    adapter = WebAdapter()
    assert isinstance(adapter, ChannelAdapter)


def test_wechat_adapter_is_channel_adapter():
    """WeChatAdapter structurally satisfies ChannelAdapter Protocol."""
    adapter = WeChatAdapter()
    assert isinstance(adapter, ChannelAdapter)


# ── WebAdapter ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_parse_inbound_basic():
    adapter = WebAdapter()
    inp = FakeChatInput(text="创建患者张三", doctor_id="doc_001")
    msg = await adapter.parse_inbound(inp)
    assert isinstance(msg, Message)
    assert msg.text == "创建患者张三"
    assert msg.doctor_id == "doc_001"
    assert msg.channel == "web"
    assert msg.content_type == "text"


@pytest.mark.asyncio
async def test_web_parse_strips_voice_prefix():
    adapter = WebAdapter()
    inp = FakeChatInput(text="语音转文字：患者胸痛两小时")
    msg = await adapter.parse_inbound(inp)
    assert msg.text == "患者胸痛两小时"


@pytest.mark.asyncio
async def test_web_parse_normalizes_history():
    adapter = WebAdapter()
    inp = FakeChatInput(
        text="hello",
        history=[
            FakeHistoryMessage(role="user", content="张三"),
            FakeHistoryMessage(role="assistant", content="已创建"),
        ],
    )
    msg = await adapter.parse_inbound(inp)
    assert len(msg.history) == 2
    assert msg.history[0] == {"role": "user", "content": "张三"}
    assert msg.history[1] == {"role": "assistant", "content": "已创建"}


@pytest.mark.asyncio
async def test_web_parse_dict_history():
    adapter = WebAdapter()
    inp = FakeChatInput(
        text="hello",
        history=[{"role": "user", "content": "hi"}],
    )
    msg = await adapter.parse_inbound(inp)
    assert msg.history == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_web_format_reply():
    adapter = WebAdapter()
    result = HandlerResult(
        reply="已创建患者",
        pending_id="abc-123",
        pending_patient_name="张三",
    )
    formatted = await adapter.format_reply(result)
    assert formatted["reply"] == "已创建患者"
    assert formatted["pending_id"] == "abc-123"
    assert formatted["pending_patient_name"] == "张三"
    assert formatted["switch_notification"] is None


@pytest.mark.asyncio
async def test_web_format_reply_with_switch_notification():
    adapter = WebAdapter()
    result = HandlerResult(
        reply="📂 患者【张三】最近 2 条记录",
        switch_notification="🔄 已从【李四】切换到【张三】",
    )
    formatted = await adapter.format_reply(result)
    assert formatted["reply"] == "📂 患者【张三】最近 2 条记录"
    assert formatted["switch_notification"] == "🔄 已从【李四】切换到【张三】"


@pytest.mark.asyncio
async def test_web_send_reply_is_noop():
    adapter = WebAdapter()
    await adapter.send_reply("doc_001", "hello")  # should not raise


@pytest.mark.asyncio
async def test_web_send_notification_is_noop():
    adapter = WebAdapter()
    await adapter.send_notification("doc_001", "reminder")  # should not raise


@pytest.mark.asyncio
async def test_web_get_history_empty():
    adapter = WebAdapter()
    history = await adapter.get_history("doc_001")
    assert history == []


def test_web_channel_name():
    assert WebAdapter().channel_name == "web"


# ── WeChatAdapter ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wechat_parse_inbound_text():
    adapter = WeChatAdapter()
    msg_obj = FakeWeChatMessage(content="你好", source="openid_doc")
    msg = await adapter.parse_inbound(msg_obj)
    assert isinstance(msg, Message)
    assert msg.text == "你好"
    assert msg.doctor_id == "openid_doc"
    assert msg.channel == "wechat"
    assert msg.content_type == "text"


@pytest.mark.asyncio
async def test_wechat_parse_inbound_voice_with_recognition():
    adapter = WeChatAdapter()
    msg_obj = FakeWeChatMessage(
        content="",
        source="openid_doc",
        type="voice",
        recognition="患者胸痛两小时",
    )
    msg = await adapter.parse_inbound(msg_obj)
    assert msg.content_type == "voice"
    assert msg.text == "患者胸痛两小时"
    assert msg.metadata["recognition"] == "患者胸痛两小时"


@pytest.mark.asyncio
async def test_wechat_parse_inbound_image():
    adapter = WeChatAdapter()
    msg_obj = FakeWeChatMessage(
        content="",
        source="openid_doc",
        type="image",
        media_id="media_abc",
    )
    msg = await adapter.parse_inbound(msg_obj)
    assert msg.content_type == "image"
    assert msg.metadata["media_id"] == "media_abc"


@pytest.mark.asyncio
async def test_wechat_parse_inbound_dict():
    adapter = WeChatAdapter()
    raw = {"content": "查询张三", "source": "openid_doc", "type": "text"}
    msg = await adapter.parse_inbound(raw)
    assert msg.text == "查询张三"
    assert msg.doctor_id == "openid_doc"


@pytest.mark.asyncio
async def test_wechat_parse_inbound_video():
    adapter = WeChatAdapter()
    msg_obj = FakeWeChatMessage(content="", type="video")
    msg = await adapter.parse_inbound(msg_obj)
    assert msg.content_type == "file"


@pytest.mark.asyncio
async def test_wechat_format_reply():
    adapter = WeChatAdapter()
    result = HandlerResult(reply="✅ 已创建患者【张三】")
    formatted = await adapter.format_reply(result)
    assert formatted == "✅ 已创建患者【张三】"


@pytest.mark.asyncio
async def test_wechat_format_reply_empty():
    adapter = WeChatAdapter()
    result = HandlerResult(reply="")
    formatted = await adapter.format_reply(result)
    assert formatted == ""


@pytest.mark.asyncio
async def test_wechat_format_reply_with_switch_notification():
    adapter = WeChatAdapter()
    result = HandlerResult(
        reply="📂 患者【张三】最近 2 条记录",
        switch_notification="🔄 已从【李四】切换到【张三】",
    )
    formatted = await adapter.format_reply(result)
    assert "🔄 已从【李四】切换到【张三】" in formatted
    assert "📂 患者【张三】最近 2 条记录" in formatted
    # switch_notification should be prepended as a separate line
    lines = formatted.split("\n")
    assert lines[0] == "🔄 已从【李四】切换到【张三】"
    assert lines[1] == "📂 患者【张三】最近 2 条记录"


@pytest.mark.asyncio
async def test_wechat_format_reply_switch_notification_none():
    """When switch_notification is None, only reply is returned."""
    adapter = WeChatAdapter()
    result = HandlerResult(reply="some reply", switch_notification=None)
    formatted = await adapter.format_reply(result)
    assert formatted == "some reply"


@pytest.mark.asyncio
async def test_wechat_send_reply_stub():
    adapter = WeChatAdapter()
    await adapter.send_reply("openid_doc", "hello")  # should not raise


@pytest.mark.asyncio
async def test_wechat_send_notification_calls_cs_api():
    """send_notification delegates to _send_customer_service_msg."""
    adapter = WeChatAdapter()
    with patch(
        "services.wechat.wechat_notify._send_customer_service_msg",
        new=AsyncMock(),
    ) as mock_send:
        await adapter.send_notification("openid_doc", "reminder")
    mock_send.assert_awaited_once_with("openid_doc", "reminder", open_kfid="")


@pytest.mark.asyncio
async def test_wechat_get_history_empty_session():
    """get_history with no session data returns empty list."""
    adapter = WeChatAdapter()
    with patch("services.session.get_session") as mock_get:
        mock_get.return_value = type("FakeSession", (), {"conversation_history": []})()
        history = await adapter.get_history("openid_doc")
        assert history == []


@pytest.mark.asyncio
async def test_wechat_get_history_returns_conversation_history():
    """get_history uses the correct field (conversation_history, not history)."""
    adapter = WeChatAdapter()
    expected = [{"role": "user", "content": "hello"}]
    with patch("services.session.get_session") as mock_get:
        mock_get.return_value = type("FakeSession", (), {"conversation_history": expected})()
        history = await adapter.get_history("openid_doc")
        assert history == expected


@pytest.mark.asyncio
async def test_wechat_get_history_import_error():
    """get_history gracefully handles import/session errors."""
    adapter = WeChatAdapter()
    with patch("services.session.get_session", side_effect=RuntimeError):
        history = await adapter.get_history("openid_doc")
        assert history == []


def test_wechat_channel_name():
    assert WeChatAdapter().channel_name == "wechat"


# ── split_wechat_message ──────────────────────────────────────────────────────


def test_split_empty():
    assert split_wechat_message("") == []


def test_split_short():
    assert split_wechat_message("hello") == ["hello"]


def test_split_exact_limit():
    text = "a" * 600
    assert split_wechat_message(text, limit=600) == [text]


def test_split_over_limit():
    line1 = "a" * 400
    line2 = "b" * 300
    text = f"{line1}\n{line2}"
    chunks = split_wechat_message(text, limit=600)
    assert len(chunks) == 2
    assert chunks[0] == line1
    assert chunks[1] == line2


def test_split_single_long_line():
    text = "x" * 1500
    chunks = split_wechat_message(text, limit=600)
    assert len(chunks) == 3
    assert chunks[0] == "x" * 600
    assert chunks[1] == "x" * 600
    assert chunks[2] == "x" * 300


def test_split_multiple_short_lines():
    lines = ["line" + str(i) for i in range(100)]
    text = "\n".join(lines)
    chunks = split_wechat_message(text, limit=600)
    assert all(len(c) <= 600 for c in chunks)
    # Reconstruct should contain all lines.
    reconstructed = "\n".join(chunks)
    for line in lines:
        assert line in reconstructed


# ── Message dataclass ─────────────────────────────────────────────────────────


def test_message_defaults():
    msg = Message(content_type="text", text="hello", doctor_id="d1", channel="web")
    assert msg.raw_payload is None
    assert msg.metadata == {}
    assert msg.history == []


def test_message_with_metadata():
    msg = Message(
        content_type="image",
        text="",
        doctor_id="d1",
        channel="wechat",
        metadata={"media_id": "abc"},
    )
    assert msg.metadata["media_id"] == "abc"


# ── Adapter-router parity tests ──────────────────────────────────────────────
# These tests verify that the adapter parse_inbound() produces the same
# output as the old manual parsing that was previously inline in routers.


@pytest.mark.asyncio
async def test_web_adapter_parity_with_old_parse():
    """WebAdapter.parse_inbound() matches the old _parse_web_message() output."""
    adapter = WebAdapter()
    inp = FakeChatInput(
        text="语音转文字：患者李四 STEMI入院",
        history=[
            FakeHistoryMessage(role="user", content="张三"),
            {"role": "assistant", "content": "已创建"},
        ],
        doctor_id="doc_parity",
    )
    msg = await adapter.parse_inbound(inp)

    # Old _parse_web_message would strip voice prefix
    assert msg.text == "患者李四 STEMI入院"
    assert msg.doctor_id == "doc_parity"
    assert msg.channel == "web"
    assert msg.content_type == "text"
    # History: objects normalized to dicts, dicts passed through
    assert msg.history[0] == {"role": "user", "content": "张三"}
    assert msg.history[1] == {"role": "assistant", "content": "已创建"}
    assert msg.raw_payload is inp


@pytest.mark.asyncio
async def test_wechat_adapter_parity_text_only():
    """WeChatAdapter.parse_inbound(dict) matches old _parse_wechat_message(text, doctor_id)."""
    adapter = WeChatAdapter()
    raw = {"content": "  创建患者王五  ", "source": "doc_wx", "type": "text"}
    msg = await adapter.parse_inbound(raw)

    # Old _parse_wechat_message would strip whitespace
    assert msg.text == "创建患者王五"
    assert msg.doctor_id == "doc_wx"
    assert msg.channel == "wechat"
    assert msg.content_type == "text"


@pytest.mark.asyncio
async def test_wechat_adapter_parity_with_msg_object():
    """WeChatAdapter.parse_inbound(wechatpy msg) matches old _parse_wechat_message(text, doctor_id, msg=msg)."""
    adapter = WeChatAdapter()
    fake_msg = FakeWeChatMessage(content="  查询张三  ", source="doc_wx", type="text")
    msg = await adapter.parse_inbound(fake_msg)

    assert msg.text == "查询张三"
    assert msg.doctor_id == "doc_wx"
    assert msg.channel == "wechat"
    assert msg.content_type == "text"
    assert msg.raw_payload is fake_msg


@pytest.mark.asyncio
async def test_wechat_adapter_parity_voice_no_recognition():
    """Voice message without recognition returns empty text."""
    adapter = WeChatAdapter()
    fake_msg = FakeWeChatMessage(
        content="", source="doc_wx", type="voice",
        media_id="mid_123", recognition=None,
    )
    msg = await adapter.parse_inbound(fake_msg)
    assert msg.content_type == "voice"
    assert msg.text == ""
    assert msg.metadata.get("media_id") == "mid_123"



# _parse_wechat_message tests removed — function was inlined during adapter refactor.
# The equivalent parsing logic is tested via WeChatAdapter.parse_inbound above.
