import pytest
from domain.knowledge.case_matching import _tokenize_medical, _compute_similarity


def test_tokenize_medical_chinese():
    tokens = _tokenize_medical("动脉瘤夹闭术后头痛，恶心呕吐")
    assert "动脉瘤夹闭术后头痛" in tokens or "头痛" in tokens
    assert len(tokens) > 0


def test_tokenize_medical_empty():
    assert _tokenize_medical("") == set()


def test_tokenize_medical_stop_words_excluded():
    # Stop words are excluded when they appear as individual tokens (after splitting)
    tokens = _tokenize_medical("的，了，是，在，有")
    assert len(tokens) == 0


def test_tokenize_medical_mixed():
    tokens = _tokenize_medical("患者头痛3天，伴恶心呕吐")
    assert "患者头痛3天" in tokens or "头痛" in tokens
    assert len(tokens) >= 1


def test_compute_similarity_identical():
    tokens = {"头痛", "术后", "恶心"}
    assert _compute_similarity(tokens, tokens) == 1.0


def test_compute_similarity_partial():
    a = {"头痛", "术后", "恶心"}
    b = {"头痛", "术后", "发热"}
    sim = _compute_similarity(a, b)
    assert 0.4 < sim < 0.6  # 2/4 overlap


def test_compute_similarity_no_overlap():
    a = {"头痛", "术后"}
    b = {"腹痛", "发热"}
    assert _compute_similarity(a, b) == 0.0


def test_compute_similarity_empty():
    assert _compute_similarity(set(), {"头痛"}) == 0.0


def test_compute_similarity_both_empty():
    assert _compute_similarity(set(), set()) == 0.0
