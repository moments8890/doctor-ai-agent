import pytest
from domain.patient_lifecycle.draft_reply import detect_red_flags, RED_FLAG_KEYWORDS


def test_detect_red_flags_positive():
    assert detect_red_flags("今天头痛加剧了，还有恶心") is True


def test_detect_red_flags_negative():
    assert detect_red_flags("恢复得不错，感觉好多了") is False


def test_detect_red_flags_empty():
    assert detect_red_flags("") is False


def test_red_flag_keywords_not_empty():
    assert len(RED_FLAG_KEYWORDS) > 10


def test_detect_red_flags_single_keyword():
    for kw in RED_FLAG_KEYWORDS:
        assert detect_red_flags(f"患者说{kw}") is True, f"Should detect: {kw}"
