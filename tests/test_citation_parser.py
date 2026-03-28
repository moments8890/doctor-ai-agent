"""Tests for citation parser (Task 3 — Knowledge Foundation)."""
from __future__ import annotations

import json

from domain.knowledge.citation_parser import (
    CitationResult,
    ValidationResult,
    extract_citations,
    validate_citations,
)


# ── extract_citations ────────────────────────────────────────────


def test_single_citation():
    result = extract_citations("建议观察 [KB-42]")
    assert result.cited_ids == [42]


def test_multiple_citations():
    result = extract_citations("内容 [KB-42][KB-15]")
    assert result.cited_ids == [42, 15]


def test_citation_inside_json_string():
    text = json.dumps({"detail": "内容 [KB-3]"}, ensure_ascii=False)
    result = extract_citations(text)
    assert result.cited_ids == [3]


def test_no_citations():
    result = extract_citations("普通文本没有引用")
    assert result.cited_ids == []


def test_duplicate_deduplication():
    result = extract_citations("[KB-5] 和 [KB-5]")
    assert result.cited_ids == [5]


def test_escaped_citation_ignored():
    result = extract_citations("\\[KB-99]")
    assert result.cited_ids == []


def test_citations_across_multiple_json_fields():
    data = {
        "diagnosis": "高血压 [KB-10]",
        "treatment": "建议 [KB-20]",
        "note": "参考 [KB-10]",  # duplicate of diagnosis
    }
    text = json.dumps(data, ensure_ascii=False)
    result = extract_citations(text)
    assert result.cited_ids == [10, 20]


def test_preserves_first_occurrence_order():
    result = extract_citations("[KB-7] 然后 [KB-3] 再 [KB-7] 最后 [KB-1]")
    assert result.cited_ids == [7, 3, 1]


def test_raw_text_preserved():
    text = "一些文本 [KB-1]"
    result = extract_citations(text)
    assert result.raw_text == text


# ── validate_citations ───────────────────────────────────────────


def test_validation_valid_ids_kept():
    result = validate_citations([1, 2, 3], {1, 2, 5, 10})
    assert result.valid_ids == [1, 2]
    assert result.hallucinated_ids == [3]


def test_validation_hallucinated_ids_removed():
    result = validate_citations([99, 100], {1, 2, 3})
    assert result.valid_ids == []
    assert result.hallucinated_ids == [99, 100]


def test_validation_empty_extraction():
    result = validate_citations([], {1, 2, 3})
    assert result.valid_ids == []
    assert result.hallucinated_ids == []


def test_validation_all_valid():
    result = validate_citations([1, 2], {1, 2, 3})
    assert result.valid_ids == [1, 2]
    assert result.hallucinated_ids == []


# ── dataclass defaults ───────────────────────────────────────────


def test_citation_result_defaults():
    r = CitationResult()
    assert r.cited_ids == []
    assert r.raw_text == ""


def test_validation_result_defaults():
    r = ValidationResult()
    assert r.valid_ids == []
    assert r.hallucinated_ids == []
