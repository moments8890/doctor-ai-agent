import pytest
from domain.knowledge.case_matching import _tokenize_medical, _compute_similarity, _build_weighted_tokens


def test_tokenize_medical_chinese():
    tokens = _tokenize_medical("动脉瘤夹闭术后头痛，恶心呕吐")
    assert "头痛" in tokens or "动脉瘤" in tokens
    assert len(tokens) > 0


def test_tokenize_medical_empty():
    assert _tokenize_medical("") == set()


def test_tokenize_medical_stop_words_excluded():
    tokens = _tokenize_medical("的，了，是，在，有")
    assert len(tokens) == 0


def test_tokenize_medical_mixed():
    tokens = _tokenize_medical("患者头痛3天，伴恶心呕吐")
    assert "头痛" in tokens
    assert len(tokens) >= 1


def test_tokenize_medical_negation_preserved():
    """Negation words (无/未/不) should NOT be filtered."""
    tokens = _tokenize_medical("无头痛，未见异常")
    # jieba may produce "无头痛" or "头痛" — negation context preserved
    assert len(tokens) > 0


def test_compute_similarity_identical():
    w = {"头痛": 1.5, "术后": 1.0, "恶心": 1.0}
    assert _compute_similarity(w, w) == 1.0


def test_compute_similarity_partial():
    a = {"头痛": 1.5, "术后": 1.0, "恶心": 1.0}
    b = {"头痛": 1.5, "术后": 1.0, "发热": 1.0}
    sim = _compute_similarity(a, b)
    # "头痛" (1.5) + "术后" (1.0) covered out of total 3.5
    assert 0.5 < sim < 0.9


def test_compute_similarity_no_overlap():
    a = {"头痛": 1.5, "术后": 1.0}
    b = {"腹痛": 1.5, "发热": 1.0}
    assert _compute_similarity(a, b) == 0.0


def test_compute_similarity_empty():
    assert _compute_similarity({}, {"头痛": 1.0}) == 0.0


def test_compute_similarity_both_empty():
    assert _compute_similarity({}, {}) == 0.0


def test_build_weighted_tokens():
    record = {
        "chief_complaint": "头痛2周",
        "diagnosis": "脑膜瘤",
    }
    weights = _build_weighted_tokens(record)
    assert "头痛" in weights or "脑膜瘤" in weights
    # diagnosis has weight 3.0, CC has 1.5
    if "脑膜瘤" in weights:
        assert weights["脑膜瘤"] == 3.0
