"""Unit tests for the style guard detector.

Tests are LLM-free — only exercise the regex/string-match detection logic
and the correction-message shape. Integration with llm_call is covered
by the followup_reply sniff tests when an LLM is available.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent.style_guard import (
    detect_hard_violations,
    detect_soft_chain,
    build_correction_message,
)


def test_detect_clean_text():
    assert detect_hard_violations("胃镜后稍微疼是正常的，可以吃稀饭。") == []


def test_detect_single_hard_violation():
    found = detect_hard_violations("您好！希望对您有帮助。")
    assert "希望对您有帮助" in found


def test_detect_multiple_hard_violations():
    text = "您好！综上所述，请遵医嘱，祝您身体健康。"
    found = detect_hard_violations(text)
    assert "综上所述" in found
    assert "请遵医嘱" in found
    assert "祝您身体健康" in found


def test_detect_soft_chain_triggers_at_three():
    text = "建议多喝水，注意休息，清淡饮食。"
    found = detect_soft_chain(text, threshold=3)
    assert len(found) == 3


def test_detect_soft_single_does_not_trigger():
    text = "建议多喝水，多吃蔬菜。"
    assert detect_soft_chain(text, threshold=3) == []


def test_detect_soft_chain_below_threshold():
    text = "多喝水，注意休息。"
    assert detect_soft_chain(text, threshold=3) == []


def test_correction_message_shape():
    msg = build_correction_message(["希望对您有帮助", "请遵医嘱"])
    assert msg["role"] == "system"
    assert "希望对您有帮助" in msg["content"]
    assert "请遵医嘱" in msg["content"]
    assert "AI 味" in msg["content"]


def test_correction_message_caps_at_five():
    """Corrective message lists at most 5 violations to keep the prompt tight."""
    many = ["希望对您有帮助", "综上所述", "祝您身体健康", "请遵医嘱",
            "如有不适请及时就医", "请咨询专业医生", "愿您早日康复"]
    msg = build_correction_message(many)
    # First 5 should be cited; last 2 should NOT
    assert "请咨询专业医生" not in msg["content"]
    assert "愿您早日康复" not in msg["content"]
    assert "希望对您有帮助" in msg["content"]
    assert "如有不适请及时就医" in msg["content"]


def test_empty_text_no_violations():
    assert detect_hard_violations("") == []
    assert detect_soft_chain("") == []
