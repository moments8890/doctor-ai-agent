"""
微信聊天记录解析器：将导出的聊天记录文本转换为可导入的临床内容。

WeChat PC export format (personal chat):
    2023-11-15 14:23:45 张医生
    李明，头疼三天，BP 140/90，给予布洛芬400mg。

    2023-11-15 15:01:00 张医生
    复查血压正常，停药。

WeChat PC export format (group chat):
    2023-11-15 14:23:45 张医生(微信号:wxid_abc)
    李明，头疼三天...

    2023-11-15 14:24:10 李护士(微信号:wxid_def)
    收到

Non-clinical content to strip:
    - Short acknowledgments: 收到, 好的, 谢谢, OK, 嗯嗯, 👍
    - System messages: [图片], [语音], [视频], [文件], [撤回了一条消息]
    - Stickers / emoji-only lines
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ── Compiled patterns ─────────────────────────────────────────────────────────

# Timestamp + sender line: "2023-11-15 14:23:45 张医生" or "2023-11-15 张医生"
_MSG_HEADER_RE = re.compile(
    r"^(\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)\s+"
    r"(.+?)(?:\(微信号:[^)]*\)|\（[^）]*\）|\([^)]*\))?\s*$"
)

# Pure date line: "2023-11-15" or "- 2023/11/15 -"
_DATE_ONLY_RE = re.compile(r"^[-\s]*\d{4}[-/]\d{1,2}[-/]\d{1,2}[-\s]*$")

# System / media placeholder messages
_SYSTEM_MSG_RE = re.compile(
    r"^\[(?:图片|语音|视频|文件|动画表情|红包|转账|位置|名片|撤回了一条消息|系统消息)[^\]]*\]$"
)

# Non-clinical short acknowledgments (standalone line)
_ACK_WORDS = frozenset([
    "收到", "好的", "好", "嗯", "嗯嗯", "嗯哦", "哦", "哦哦",
    "ok", "OK", "Ok", "好滴", "知道了", "谢谢", "谢", "辛苦了",
    "👍", "🙏", "✅", "好的好的", "明白", "明白了",
])

# Clinical signal keywords — message containing any of these is kept regardless of length
_CLINICAL_SIGNALS = frozenset([
    "主诉", "诊断", "处方", "用药", "血压", "心率", "体温", "血糖", "血氧",
    "症状", "病史", "检查", "化验", "B超", "CT", "MRI", "X线", "心电图",
    "入院", "出院", "手术", "复诊", "随访", "转科", "病历",
    "mg", "ml", "μg", "片", "支", "次/日", "bid", "tid", "qd",
    "BP", "HR", "SpO2", "HbA1c", "INR", "PT", "APTT",
])

# Minimum chars for a message to be considered clinical without explicit keywords
_MIN_CLINICAL_LEN = 15


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    timestamp: str          # "2023-11-15 14:23:45"
    sender: str             # "张医生"
    content: str            # message body (may be multi-line)


@dataclass
class ParseResult:
    messages: List[ChatMessage] = field(default_factory=list)
    senders: List[str] = field(default_factory=list)    # unique senders in order of appearance
    total_messages: int = 0
    clinical_messages: int = 0


# ── Parser ────────────────────────────────────────────────────────────────────

def _iter_chat_lines(
    lines: List[str],
) -> "tuple[List[ChatMessage], dict[str, int]]":
    """逐行解析聊天记录，返回 (messages, seen_senders)。"""
    messages: List[ChatMessage] = []
    seen_senders: dict[str, int] = {}
    current_ts: Optional[str] = None
    current_sender: Optional[str] = None
    current_lines: List[str] = []

    def _flush() -> None:
        if current_sender is None:
            return
        body = "\n".join(current_lines).strip()
        if body:
            messages.append(ChatMessage(
                timestamp=current_ts or "",
                sender=current_sender,
                content=body,
            ))
            if current_sender not in seen_senders:
                seen_senders[current_sender] = len(seen_senders)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("导出时间") or set(stripped) <= {"—", "－", "-", " ", "="}:
            continue
        if _DATE_ONLY_RE.match(stripped):
            continue
        m = _MSG_HEADER_RE.match(stripped)
        if m:
            _flush()
            current_ts = m.group(1).strip()
            current_sender = m.group(2).strip()
            current_lines = []
            continue
        if stripped:
            current_lines.append(stripped)

    _flush()
    return messages, seen_senders


def parse_wechat_export(text: str) -> ParseResult:
    """将微信 PC 导出聊天记录解析为结构化消息列表（个人聊天和群聊均支持）。"""
    lines = text.splitlines()
    messages, seen_senders = _iter_chat_lines(lines)
    ordered_senders = sorted(seen_senders.keys(), key=lambda s: seen_senders[s])
    return ParseResult(
        messages=messages,
        senders=ordered_senders,
        total_messages=len(messages),
    )


# ── Clinical filter ───────────────────────────────────────────────────────────

def is_clinical(msg: ChatMessage) -> bool:
    """Return True if a message likely contains clinical content worth importing."""
    content = msg.content.strip()

    # System / media placeholders
    if _SYSTEM_MSG_RE.match(content):
        return False

    # Pure acknowledgment
    if content in _ACK_WORDS:
        return False

    # Very short with no clinical keywords
    if len(content) < _MIN_CLINICAL_LEN:
        return any(kw in content for kw in _CLINICAL_SIGNALS)

    # Longer message: keep unless it's pure non-clinical
    return True


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_clinical_text(
    text: str,
    sender_filter: Optional[str] = None,
) -> str:
    """Parse a WeChat chat export and return clinical content as plain text.

    Args:
        text: Raw WeChat export text.
        sender_filter: If set, only include messages from this sender name.
                       If None, include all senders' clinical messages.

    Returns:
        Cleaned text ready for _preprocess_import_text → _chunk_history_text pipeline.
        Each message is prefixed with its timestamp so the chunker can split by date.
    """
    result = parse_wechat_export(text)

    kept: List[str] = []
    clinical_count = 0

    for msg in result.messages:
        if sender_filter and msg.sender != sender_filter:
            continue
        if not is_clinical(msg):
            continue
        clinical_count += 1
        # Prefix with timestamp so date-boundary chunker can split correctly
        kept.append(f"{msg.timestamp}\n{msg.content}")

    result.clinical_messages = clinical_count
    return "\n\n".join(kept)


def list_senders(text: str) -> List[str]:
    """Return unique senders from a WeChat export, in order of first appearance.

    Used to present the doctor with a choice of whose messages to import.
    """
    result = parse_wechat_export(text)
    return result.senders
