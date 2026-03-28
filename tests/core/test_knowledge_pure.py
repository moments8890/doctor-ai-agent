"""
Pure-function unit tests for the knowledge module.

No mocks, no DB, no async — these cover only the deterministic helpers
in knowledge_crud and knowledge_context.
"""

from __future__ import annotations

import json

import pytest

from domain.knowledge.knowledge_crud import (
    _decode_knowledge_payload,
    _encode_knowledge_payload,
    _normalize_text,
    _sanitize_for_prompt,
    extract_title_from_text,
)
from domain.knowledge.knowledge_context import (
    _score_item,
    _source_weight,
    _tokenize,
)


# ── _normalize_text ────────────────────────────────────────────────


class TestNormalizeText:
    def test_strips_leading_and_trailing_whitespace(self):
        assert _normalize_text("  hello  ") == "hello"

    def test_collapses_internal_spaces(self):
        assert _normalize_text("a   b   c") == "a b c"

    def test_collapses_mixed_whitespace_to_single_space(self):
        assert _normalize_text("a\t\tb\t c") == "a b c"

    def test_newlines_collapsed_to_space(self):
        assert _normalize_text("line1\nline2") == "line1 line2"

    def test_empty_string_returns_empty(self):
        assert _normalize_text("") == ""

    def test_none_treated_as_empty(self):
        # `value or ""` handles None gracefully
        assert _normalize_text(None) == ""  # type: ignore[arg-type]

    def test_chinese_text_preserved(self):
        assert _normalize_text("  诊断：心衰  ") == "诊断：心衰"

    def test_chinese_with_internal_spaces(self):
        assert _normalize_text("诊断：  心衰") == "诊断： 心衰"

    def test_already_normalized_unchanged(self):
        assert _normalize_text("已正规处理") == "已正规处理"

    def test_only_whitespace_returns_empty(self):
        assert _normalize_text("   \t\n  ") == ""

    def test_medical_abbreviation_preserved(self):
        # STEMI, BNP etc. must not be altered
        assert _normalize_text("  STEMI  患者首选PCI  ") == "STEMI 患者首选PCI"


# ── _sanitize_for_prompt ───────────────────────────────────────────


class TestSanitizeForPrompt:
    def test_less_than_replaced_with_fullwidth(self):
        assert "\uff1c" in _sanitize_for_prompt("<script>")

    def test_greater_than_replaced_with_fullwidth(self):
        assert "\uff1e" in _sanitize_for_prompt("<script>")

    def test_html_tag_fully_escaped(self):
        result = _sanitize_for_prompt("<b>text</b>")
        assert "<" not in result
        assert ">" not in result
        assert "\uff1cb\uff1e" in result

    def test_kb_prefix_escaped(self):
        result = _sanitize_for_prompt("[KB-42] 糖尿病")
        assert result.startswith("\\[KB-")

    def test_kb_prefix_mid_string_escaped(self):
        result = _sanitize_for_prompt("参见 [KB-1] 了解详情")
        assert "\\[KB-1]" in result

    def test_multiple_kb_prefixes_all_escaped(self):
        result = _sanitize_for_prompt("[KB-1] 和 [KB-2]")
        assert result.count("\\[KB-") == 2

    def test_control_chars_stripped(self):
        # U+0001 through U+0008 are stripped
        result = _sanitize_for_prompt("clean\x01\x07text")
        assert "\x01" not in result
        assert "\x07" not in result
        assert "cleantext" in result

    def test_newline_preserved(self):
        # 0x0A (newline) must NOT be stripped
        result = _sanitize_for_prompt("line1\nline2")
        assert "\n" in result

    def test_tab_preserved(self):
        # 0x09 (tab) must NOT be stripped
        result = _sanitize_for_prompt("col1\tcol2")
        assert "\t" in result

    def test_clean_chinese_medical_text_unchanged(self):
        text = "用药规范：阿司匹林100mg每日一次，禁止空腹服用"
        result = _sanitize_for_prompt(text)
        assert result == text

    def test_empty_string_returns_empty(self):
        assert _sanitize_for_prompt("") == ""

    def test_medical_xml_like_content_escaped(self):
        result = _sanitize_for_prompt("剂量<100mg/kg")
        assert "\uff1c" in result
        assert "<" not in result


# ── _encode_knowledge_payload ──────────────────────────────────────


class TestEncodeKnowledgePayload:
    def test_returns_valid_json(self):
        raw = _encode_knowledge_payload("心衰治疗", "doctor", 0.9)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_payload_contains_required_keys(self):
        parsed = json.loads(_encode_knowledge_payload("心衰治疗", "doctor", 0.9))
        assert "v" in parsed
        assert "text" in parsed
        assert "source" in parsed
        assert "confidence" in parsed

    def test_version_is_1(self):
        parsed = json.loads(_encode_knowledge_payload("test", "doctor", 1.0))
        assert parsed["v"] == 1

    def test_text_is_normalized(self):
        parsed = json.loads(_encode_knowledge_payload("  hello   world  ", "doctor", 1.0))
        assert parsed["text"] == "hello world"

    def test_source_stored_correctly(self):
        parsed = json.loads(_encode_knowledge_payload("test", "ai", 0.8))
        assert parsed["source"] == "ai"

    def test_confidence_stored_correctly(self):
        parsed = json.loads(_encode_knowledge_payload("test", "doctor", 0.75))
        assert abs(parsed["confidence"] - 0.75) < 1e-9

    def test_confidence_clamped_above_1(self):
        parsed = json.loads(_encode_knowledge_payload("test", "doctor", 1.5))
        assert parsed["confidence"] == 1.0

    def test_confidence_clamped_below_0(self):
        parsed = json.loads(_encode_knowledge_payload("test", "doctor", -0.3))
        assert parsed["confidence"] == 0.0

    def test_confidence_boundary_0(self):
        parsed = json.loads(_encode_knowledge_payload("test", "doctor", 0.0))
        assert parsed["confidence"] == 0.0

    def test_confidence_boundary_1(self):
        parsed = json.loads(_encode_knowledge_payload("test", "doctor", 1.0))
        assert parsed["confidence"] == 1.0

    def test_chinese_text_not_ascii_escaped(self):
        raw = _encode_knowledge_payload("糖尿病管理", "doctor", 1.0)
        assert "糖尿病管理" in raw

    def test_medical_abbreviations_preserved(self):
        parsed = json.loads(_encode_knowledge_payload("BNP>400提示心衰", "doctor", 0.9))
        assert "BNP" in parsed["text"]
        assert "400" in parsed["text"]

    def test_round_trips_via_decode(self):
        raw = _encode_knowledge_payload("eGFR<60考虑CKD", "doctor", 0.85)
        text, source, confidence, source_url, file_path = _decode_knowledge_payload(raw)
        assert "eGFR" in text
        assert source == "doctor"
        assert abs(confidence - 0.85) < 1e-9
        assert source_url is None
        assert file_path is None


# ── _decode_knowledge_payload ──────────────────────────────────────


class TestDecodeKnowledgePayload:
    def test_decodes_valid_v1_payload(self):
        raw = json.dumps({"v": 1, "text": "心衰管理", "source": "doctor", "confidence": 0.9})
        text, source, conf, source_url, file_path = _decode_knowledge_payload(raw)
        assert text == "心衰管理"
        assert source == "doctor"
        assert abs(conf - 0.9) < 1e-9
        assert source_url is None
        assert file_path is None

    def test_empty_string_returns_defaults(self):
        text, source, conf, source_url, file_path = _decode_knowledge_payload("")
        assert text == ""
        assert source == "doctor"
        assert conf == 1.0
        assert source_url is None
        assert file_path is None

    def test_none_returns_defaults(self):
        text, source, conf, source_url, file_path = _decode_knowledge_payload(None)  # type: ignore[arg-type]
        assert text == ""
        assert source == "doctor"
        assert conf == 1.0
        assert source_url is None
        assert file_path is None

    def test_whitespace_only_returns_defaults(self):
        text, source, conf, source_url, file_path = _decode_knowledge_payload("   ")
        assert text == ""
        assert source == "doctor"
        assert conf == 1.0
        assert source_url is None
        assert file_path is None

    def test_legacy_plain_text_fallback(self):
        # Raw text that doesn't start with { → legacy plain text
        raw = "注意心率控制在60-80次/分"
        text, source, conf, source_url, file_path = _decode_knowledge_payload(raw)
        assert text == "注意心率控制在60-80次/分"
        assert source == "doctor"
        assert conf == 1.0
        assert source_url is None
        assert file_path is None

    def test_legacy_text_is_normalized(self):
        raw = "  多余空格   测试  "
        text, source, conf, _url, _fp = _decode_knowledge_payload(raw)
        assert text == "多余空格 测试"

    def test_json_without_text_key_falls_back_to_raw(self):
        # Starts with { but no "text" key → treated as raw text
        raw = '{"other": "value"}'
        text, source, conf, _url, _fp = _decode_knowledge_payload(raw)
        assert text == raw.strip()
        assert source == "doctor"

    def test_malformed_json_falls_back_to_raw(self):
        raw = '{"text": "broken", "v": 1'  # truncated JSON
        text, source, conf, _url, _fp = _decode_knowledge_payload(raw)
        assert source == "doctor"
        assert conf == 1.0

    def test_confidence_clamped_on_decode(self):
        raw = json.dumps({"v": 1, "text": "test", "source": "doctor", "confidence": 2.5})
        _, _, conf, _, _ = _decode_knowledge_payload(raw)
        assert conf == 1.0

    def test_confidence_clamped_negative_on_decode(self):
        raw = json.dumps({"v": 1, "text": "test", "source": "doctor", "confidence": -1.0})
        _, _, conf, _, _ = _decode_knowledge_payload(raw)
        assert conf == 0.0

    def test_missing_confidence_defaults_to_1(self):
        raw = json.dumps({"v": 1, "text": "诊断规范", "source": "doctor"})
        _, _, conf, _, _ = _decode_knowledge_payload(raw)
        assert conf == 1.0

    def test_missing_source_defaults_to_doctor(self):
        raw = json.dumps({"v": 1, "text": "诊断规范", "confidence": 0.8})
        _, source, _, _, _ = _decode_knowledge_payload(raw)
        assert source == "doctor"

    def test_non_string_confidence_defaults_to_1(self):
        raw = json.dumps({"v": 1, "text": "test", "source": "ai", "confidence": None})
        _, _, conf, _, _ = _decode_knowledge_payload(raw)
        assert conf == 1.0

    def test_text_normalized_on_decode(self):
        raw = json.dumps({"v": 1, "text": "  多余  空格  ", "source": "doctor", "confidence": 1.0})
        text, _, _, _, _ = _decode_knowledge_payload(raw)
        assert text == "多余 空格"

    def test_ai_source_preserved(self):
        raw = json.dumps({"v": 1, "text": "AI生成内容", "source": "ai", "confidence": 0.7})
        _, source, _, _, _ = _decode_knowledge_payload(raw)
        assert source == "ai"

    def test_medical_abbreviations_survive_round_trip(self):
        for abbr in ("STEMI", "BNP", "eGFR", "LVEF", "NT-proBNP"):
            encoded = _encode_knowledge_payload(f"{abbr}异常需要复查", "doctor", 0.95)
            text, _, _, _, _ = _decode_knowledge_payload(encoded)
            assert abbr in text

    def test_source_url_round_trip(self):
        encoded = _encode_knowledge_payload("test", "doctor", 1.0, source_url="https://example.com/doc.pdf")
        text, source, conf, source_url, file_path = _decode_knowledge_payload(encoded)
        assert text == "test"
        assert source_url == "https://example.com/doc.pdf"
        assert file_path is None

    def test_source_url_none_omitted_from_payload(self):
        encoded = _encode_knowledge_payload("test", "doctor", 1.0, source_url=None)
        import json as _json
        parsed = _json.loads(encoded)
        assert "source_url" not in parsed
        _, _, _, source_url, _ = _decode_knowledge_payload(encoded)
        assert source_url is None

    def test_file_path_round_trip(self):
        encoded = _encode_knowledge_payload(
            "test", "doctor", 1.0,
            file_path="uploads/doc123/20260328_120000_report.pdf",
        )
        text, source, conf, source_url, file_path = _decode_knowledge_payload(encoded)
        assert text == "test"
        assert file_path == "uploads/doc123/20260328_120000_report.pdf"
        assert source_url is None

    def test_file_path_none_omitted_from_payload(self):
        encoded = _encode_knowledge_payload("test", "doctor", 1.0, file_path=None)
        import json as _json
        parsed = _json.loads(encoded)
        assert "file_path" not in parsed
        _, _, _, _, file_path = _decode_knowledge_payload(encoded)
        assert file_path is None


# ── extract_title_from_text ────────────────────────────────────────


class TestExtractTitleFromText:
    def test_empty_string_returns_empty(self):
        assert extract_title_from_text("") == ""

    def test_none_returns_empty(self):
        assert extract_title_from_text(None) == ""  # type: ignore[arg-type]

    def test_first_line_used_when_no_colon_or_period(self):
        text = "术后头痛危险信号\n先排除再出血"
        assert extract_title_from_text(text) == "术后头痛危险信号"

    def test_fullwidth_colon_splits_title(self):
        text = "蛛网膜下腔出血（SAH）：突发剧烈头痛，伴恶心呕吐。Fisher分级。"
        assert extract_title_from_text(text) == "蛛网膜下腔出血（SAH）"

    def test_ascii_colon_splits_title(self):
        text = "STEMI处理: 尽快转导管室，开通IRA"
        assert extract_title_from_text(text) == "STEMI处理"

    def test_colon_takes_priority_over_period(self):
        # Colon is preferred even when both delimiters appear on the same line
        text = "诊断标准：BNP>400。其他说明"
        assert extract_title_from_text(text) == "诊断标准"

    def test_period_used_when_no_colon(self):
        text = "术后头痛危险信号。先排除再出血"
        assert extract_title_from_text(text) == "术后头痛危险信号"

    def test_truncates_to_default_20_chars(self):
        long = "这是一个非常非常非常非常非常非常非常非常非常非常长的标题"
        result = extract_title_from_text(long)
        assert result.endswith("…")
        # 20 CJK characters + ellipsis = 21 total
        assert len(result) == 21

    def test_truncates_to_custom_max_len(self):
        long = "A" * 50
        result = extract_title_from_text(long, max_len=10)
        assert result.endswith("…")
        assert len(result) == 11

    def test_no_truncation_when_within_limit(self):
        short = "短标题"
        assert extract_title_from_text(short) == "短标题"
        assert "…" not in extract_title_from_text(short)

    def test_exactly_max_len_not_truncated(self):
        text = "A" * 20
        result = extract_title_from_text(text, max_len=20)
        assert not result.endswith("…")
        assert result == text

    def test_one_over_max_len_truncated(self):
        text = "A" * 21
        result = extract_title_from_text(text, max_len=20)
        assert result.endswith("…")

    def test_multiline_only_first_line_used(self):
        text = "第一行标题\n第二行内容：详细说明"
        assert extract_title_from_text(text) == "第一行标题"

    def test_sah_with_parentheses_preserved(self):
        # Real medical text from the codebase comment
        text = "蛛网膜下腔出血（SAH）：突发剧烈头痛"
        assert extract_title_from_text(text) == "蛛网膜下腔出血（SAH）"

    def test_ascii_only_text(self):
        text = "EGFR threshold: below 60 indicates CKD"
        assert extract_title_from_text(text) == "EGFR threshold"


# ── _tokenize ─────────────────────────────────────────────────────


class TestTokenize:
    def test_empty_string_returns_empty_list(self):
        assert _tokenize("") == []

    def test_none_returns_empty_list(self):
        assert _tokenize(None) == []  # type: ignore[arg-type]

    def test_pure_ascii_words(self):
        assert _tokenize("hello world") == ["hello", "world"]

    def test_tokens_are_lowercased(self):
        assert _tokenize("STEMI BNP eGFR") == ["stemi", "bnp", "egfr"]

    def test_cjk_characters_extracted(self):
        tokens = _tokenize("心衰治疗")
        assert "心衰治疗" in tokens

    def test_mixed_cjk_and_ascii_adjacent(self):
        # The regex [\u4e00-\u9fffA-Za-z0-9_]+ treats adjacent ASCII+CJK as ONE
        # token because there is no separator between them.
        tokens = _tokenize("BNP升高提示心衰")
        assert len(tokens) == 1
        assert tokens[0] == "bnp升高提示心衰"

    def test_mixed_cjk_and_ascii_space_separated(self):
        # When a space separates the ASCII prefix from the CJK run they are
        # distinct tokens.
        tokens = _tokenize("BNP 升高提示心衰")
        assert "bnp" in tokens
        assert "升高提示心衰" in tokens

    def test_punctuation_not_included(self):
        tokens = _tokenize("诊断：心衰。")
        assert "：" not in tokens
        assert "。" not in tokens

    def test_digits_included(self):
        tokens = _tokenize("BNP400")
        assert "bnp400" in tokens

    def test_underscore_included(self):
        tokens = _tokenize("doctor_id")
        assert "doctor_id" in tokens

    def test_whitespace_between_tokens(self):
        tokens = _tokenize("term1  term2")
        assert "term1" in tokens
        assert "term2" in tokens

    def test_medical_abbreviations_preserved(self):
        for abbr in ("STEMI", "BNP", "EGFR", "LVEF"):
            tokens = _tokenize(abbr)
            assert abbr.lower() in tokens

    def test_chinese_medical_terms(self):
        tokens = _tokenize("糖尿病患者随访注意事项")
        # Entire CJK run is one token
        assert len(tokens) >= 1
        assert all(isinstance(t, str) for t in tokens)

    def test_numbers_alone(self):
        tokens = _tokenize("400 800")
        assert "400" in tokens
        assert "800" in tokens


# ── _score_item ────────────────────────────────────────────────────


class TestScoreItem:
    def test_empty_query_scores_zero(self):
        assert _score_item("", "心衰治疗方案") == 0

    def test_none_query_scores_zero(self):
        assert _score_item(None, "心衰治疗方案") == 0  # type: ignore[arg-type]

    def test_single_match_scores_2(self):
        # Each matching token adds 2
        assert _score_item("心衰", "心衰治疗") == 2

    def test_two_token_both_match_scores_4(self):
        score = _score_item("BNP 心衰", "BNP升高提示心衰")
        assert score == 4

    def test_no_match_scores_zero(self):
        assert _score_item("头痛", "心衰治疗方案") == 0

    def test_case_insensitive_matching(self):
        # Query "BNP" → token "bnp", haystack lowercase should match
        score = _score_item("BNP", "bnp升高")
        assert score == 2

    def test_partial_token_does_not_match(self):
        # "心" is a single CJK run — won't match "心衰" as a token in the query
        # but haystack matching is substring: "心" in "心衰" → True
        # This tests the actual substring-in-haystack behaviour
        score = _score_item("心", "心衰治疗")
        assert score == 2  # "心" is a substring of "心衰治疗"

    def test_empty_item_content_scores_zero(self):
        assert _score_item("心衰", "") == 0

    def test_none_item_content_scores_zero(self):
        assert _score_item("心衰", None) == 0  # type: ignore[arg-type]

    def test_medical_abbreviation_match(self):
        score = _score_item("STEMI 心电图", "STEMI患者需急诊PCI，心电图ST段抬高")
        assert score >= 4  # both tokens match

    def test_score_is_integer(self):
        score = _score_item("诊断", "诊断标准")
        assert isinstance(score, int)

    def test_repeated_query_token_counted_once_per_token(self):
        # query has two tokens: "bnp" and "bnp" after tokenization → ["bnp", "bnp"]
        # each hit adds 2, so two tokens even if identical = 4
        score = _score_item("BNP BNP", "bnp升高")
        assert score == 4  # two tokens, each adds 2

    def test_longer_query_more_tokens_higher_max_score(self):
        short = _score_item("心衰", "心衰患者BNP升高需要随访")
        long = _score_item("心衰 BNP 随访", "心衰患者BNP升高需要随访")
        assert long >= short


# ── _source_weight ─────────────────────────────────────────────────


class TestSourceWeight:
    def test_doctor_source_returns_half(self):
        assert _source_weight("doctor") == 0.5

    def test_ai_source_returns_point_two(self):
        assert _source_weight("ai") == 0.2

    def test_empty_string_returns_point_two(self):
        assert _source_weight("") == 0.2

    def test_unknown_source_returns_point_two(self):
        assert _source_weight("system") == 0.2
        assert _source_weight("unknown") == 0.2

    def test_doctor_case_sensitive(self):
        # "Doctor" != "doctor" — must return non-doctor weight
        assert _source_weight("Doctor") == 0.2

    def test_return_type_is_float(self):
        assert isinstance(_source_weight("doctor"), float)
        assert isinstance(_source_weight("ai"), float)

    @pytest.mark.parametrize("source,expected", [
        ("doctor", 0.5),
        ("ai", 0.2),
        ("", 0.2),
        ("system", 0.2),
        ("manual", 0.2),
        ("import", 0.2),
    ])
    def test_all_non_doctor_sources_return_low_weight(self, source, expected):
        assert _source_weight(source) == expected
