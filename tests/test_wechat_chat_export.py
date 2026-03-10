"""微信聊天记录导出解析测试：验证个人聊天与群聊的消息解析、发送者过滤、临床内容识别及文本提取的正确性。"""

from services.wechat.wechat_chat_export import (
    extract_clinical_text,
    is_clinical,
    list_senders,
    parse_wechat_export,
    ChatMessage,
)

# ── Sample exports ────────────────────────────────────────────────────────────

PERSONAL_CHAT = """\
导出时间：2023-11-15 20:00:00
———————————————

2023-11-15 14:23:45 张医生
李明，头疼三天，BP 140/90，给予布洛芬400mg。

2023-11-15 14:24:10 张医生
嘱咐多休息，一周后复诊。

2023-11-15 15:01:00 张医生
收到

2023-11-15 15:02:00 张医生
[图片]
"""

GROUP_CHAT = """\
2023-11-15 09:00:00 张医生(微信号:wxid_abc)
李航，胸痛2小时伴大汗，ECG示V1-V4 ST段抬高2mm，拟急诊PCI。

2023-11-15 09:00:30 李护士(微信号:wxid_def)
收到，马上通知导管室。

2023-11-15 09:01:00 王主任（13800000000）
好的

2023-11-15 09:05:00 张医生(微信号:wxid_abc)
已给予阿司匹林300mg，氯吡格雷600mg，肝素5000U静推。
"""


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_parse_personal_chat_messages():
    result = parse_wechat_export(PERSONAL_CHAT)
    assert result.total_messages == 4  # including [图片] and 收到
    assert result.senders == ["张医生"]


def test_parse_group_chat_senders():
    result = parse_wechat_export(GROUP_CHAT)
    assert "张医生" in result.senders
    assert "李护士" in result.senders
    assert "王主任" in result.senders


def test_list_senders_group():
    senders = list_senders(GROUP_CHAT)
    assert senders[0] == "张医生"   # first to speak
    assert len(senders) == 3


def test_list_senders_personal():
    senders = list_senders(PERSONAL_CHAT)
    assert senders == ["张医生"]


def test_is_clinical_filters_ack():
    assert not is_clinical(ChatMessage("2023-01-01", "张医生", "收到"))
    assert not is_clinical(ChatMessage("2023-01-01", "张医生", "好的"))
    assert not is_clinical(ChatMessage("2023-01-01", "张医生", "👍"))


def test_is_clinical_filters_media():
    assert not is_clinical(ChatMessage("2023-01-01", "张医生", "[图片]"))
    assert not is_clinical(ChatMessage("2023-01-01", "张医生", "[语音]"))
    assert not is_clinical(ChatMessage("2023-01-01", "张医生", "[撤回了一条消息]"))


def test_is_clinical_keeps_long_message():
    msg = ChatMessage("2023-01-01", "张医生", "李明，头疼三天，BP 140/90，给予布洛芬400mg，嘱多休息。")
    assert is_clinical(msg)


def test_is_clinical_keeps_short_with_keyword():
    msg = ChatMessage("2023-01-01", "张医生", "BP 140/90")
    assert is_clinical(msg)


def test_extract_clinical_text_personal():
    result = extract_clinical_text(PERSONAL_CHAT)
    assert "布洛芬" in result
    assert "复诊" in result
    assert "收到" not in result
    assert "[图片]" not in result


def test_extract_clinical_text_with_sender_filter():
    result = extract_clinical_text(GROUP_CHAT, sender_filter="张医生")
    assert "胸痛" in result
    assert "阿司匹林" in result
    # Nurse's acknowledgment filtered out
    assert "导管室" not in result
    assert "收到" not in result


def test_extract_clinical_text_no_filter_includes_all_senders():
    result = extract_clinical_text(GROUP_CHAT)
    # Clinical content from 张医生 is included
    assert "胸痛" in result
    # Short acks are filtered even without sender_filter
    assert "收到" not in result


def test_timestamps_preserved_for_chunker():
    """Clinical messages should be prefixed with timestamp for date-boundary chunking."""
    result = extract_clinical_text(PERSONAL_CHAT)
    assert "2023-11-15" in result


def test_preprocess_wechat_chat_export_integration():
    """preprocess_wechat_chat_export in wechat_media_pipeline delegates correctly."""
    from services.wechat.wechat_media_pipeline import preprocess_wechat_chat_export
    result = preprocess_wechat_chat_export(GROUP_CHAT, sender_filter="张医生")
    assert "胸痛" in result
    assert "导管室" not in result
