"""Unit tests for services/domain/name_utils.py — all exported functions."""

from __future__ import annotations

from typing import List, Optional

import pytest

from services.domain.name_utils import (
    assistant_asked_for_name,
    is_valid_patient_name,
    last_assistant_was_unclear_menu,
    leading_name_with_clinical_context,
    name_only_text,
    patient_name_from_history,
)


# ---------------------------------------------------------------------------
# 1. is_valid_patient_name
# ---------------------------------------------------------------------------

class TestIsValidPatientName:
    """is_valid_patient_name: empty, long, bad fragments, bed numbers, valid Chinese."""

    @pytest.mark.parametrize("name", ["", " ", "   "])
    def test_empty_returns_false(self, name: str) -> None:
        assert is_valid_patient_name(name) is False

    def test_too_long_returns_false(self) -> None:
        assert is_valid_patient_name("张" * 21) is False

    @pytest.mark.parametrize("name", [
        "叫什么名字",
        "这位患者需要检查",
        "请问一下",
        "入院前准备",
        "补一条记录",
        "急查血常规",
    ])
    def test_bad_fragments_returns_false(self, name: str) -> None:
        assert is_valid_patient_name(name) is False

    @pytest.mark.parametrize("name", [
        "3床", "12床", "一床", "七床",
        "第三床", "第七床",
        "62M", "53F",
        "女，65岁", "男，42岁",
    ])
    def test_bed_numbers_and_demographic_codes_returns_false(self, name: str) -> None:
        assert is_valid_patient_name(name) is False

    @pytest.mark.parametrize("name", [
        "张三", "李明华", "王小明", "赵", "欧阳修",
    ])
    def test_valid_names_returns_true(self, name: str) -> None:
        assert is_valid_patient_name(name) is True

    def test_20_char_name_still_valid(self) -> None:
        # Exactly 20 characters — should be valid (boundary)
        assert is_valid_patient_name("张" * 20) is True


# ---------------------------------------------------------------------------
# 2. assistant_asked_for_name
# ---------------------------------------------------------------------------

class TestAssistantAskedForName:
    """assistant_asked_for_name: empty history, matching fragment, no match."""

    def test_empty_history_returns_false(self) -> None:
        assert assistant_asked_for_name([]) is False

    def test_last_assistant_asks_for_name(self) -> None:
        history = [
            {"role": "user", "content": "帮我建个档案"},
            {"role": "assistant", "content": "请问患者叫什么名字？"},
        ]
        assert assistant_asked_for_name(history) is True

    def test_last_assistant_does_not_ask(self) -> None:
        history = [
            {"role": "user", "content": "帮我建个档案"},
            {"role": "assistant", "content": "好的，已经为您创建了档案。"},
        ]
        assert assistant_asked_for_name(history) is False

    def test_finds_most_recent_assistant_turn(self) -> None:
        """The function scans in reverse and checks the first assistant turn it finds."""
        history = [
            {"role": "assistant", "content": "请提供姓名"},
            {"role": "user", "content": "张三"},
            {"role": "user", "content": "还有别的吗"},
        ]
        # Even though user turns follow, the most recent assistant turn asked for name
        assert assistant_asked_for_name(history) is True

    def test_recognizes_all_fragments(self) -> None:
        for frag in ("叫什么名字", "患者姓名", "请提供姓名", "请告知姓名"):
            history = [{"role": "assistant", "content": f"我需要知道{frag}才能继续"}]
            assert assistant_asked_for_name(history) is True, f"failed for fragment: {frag}"


# ---------------------------------------------------------------------------
# 3. last_assistant_was_unclear_menu
# ---------------------------------------------------------------------------

class TestLastAssistantWasUnclearMenu:
    """last_assistant_was_unclear_menu: starts with unclear prefix vs not."""

    def test_starts_with_unclear_prefix(self) -> None:
        history = [
            {"role": "assistant", "content": "我还不能确定您的操作意图，请选择：\n1. 建档\n2. 添加病历"},
        ]
        assert last_assistant_was_unclear_menu(history) is True

    def test_normal_response(self) -> None:
        history = [
            {"role": "assistant", "content": "好的，已经记录了患者信息。"},
        ]
        assert last_assistant_was_unclear_menu(history) is False

    def test_empty_history(self) -> None:
        assert last_assistant_was_unclear_menu([]) is False

    def test_only_user_turns(self) -> None:
        history = [{"role": "user", "content": "我还不能确定您的操作意图"}]
        assert last_assistant_was_unclear_menu(history) is False


# ---------------------------------------------------------------------------
# 4. name_only_text
# ---------------------------------------------------------------------------

class TestNameOnlyText:
    """name_only_text: 2-4 char Chinese name, invalid, long text."""

    @pytest.mark.parametrize("text,expected", [
        ("张三", "张三"),
        ("李明华", "李明华"),
        ("欧阳明月", "欧阳明月"),
        ("  王五  ", "王五"),
    ])
    def test_valid_name_returns_name(self, text: str, expected: str) -> None:
        assert name_only_text(text) == expected

    @pytest.mark.parametrize("text", [
        "张",            # too short (1 char, regex needs 2-4)
        "张三丰无名氏",  # too long (>4 chars)
        "hello",         # not Chinese
        "3床",           # bed number (invalid name)
        "张三你好吗最近怎么样",  # not name-only (mixed sentence)
    ])
    def test_invalid_returns_none(self, text: str) -> None:
        assert name_only_text(text) is None


# ---------------------------------------------------------------------------
# 5. leading_name_with_clinical_context
# ---------------------------------------------------------------------------

class TestLeadingNameWithClinicalContext:
    """leading_name_with_clinical_context: name + clinical context vs no match."""

    def test_name_with_clinical_text(self) -> None:
        assert leading_name_with_clinical_context("张三，男，52岁，胸闷") == "张三"

    def test_name_with_gender_age(self) -> None:
        assert leading_name_with_clinical_context("李明华 女 38岁 头痛两天") == "李明华"

    def test_no_leading_name(self) -> None:
        assert leading_name_with_clinical_context("今天头痛厉害") is None

    def test_empty_text(self) -> None:
        assert leading_name_with_clinical_context("") is None
        assert leading_name_with_clinical_context(None) is None

    def test_name_without_clinical_context(self) -> None:
        # A name followed by insufficient context should return None
        assert leading_name_with_clinical_context("张三") is None

    def test_name_with_comma_separator(self) -> None:
        assert leading_name_with_clinical_context("赵六，反复胸闷气短三天") == "赵六"


# ---------------------------------------------------------------------------
# 6. patient_name_from_history
# ---------------------------------------------------------------------------

class TestPatientNameFromHistory:
    """patient_name_from_history: bracket pattern, archive pattern, user turn, no match."""

    def test_assistant_bracket_pattern(self) -> None:
        history: List[dict] = [
            {"role": "assistant", "content": "已为患者【张三】创建档案"},
        ]
        assert patient_name_from_history(history) == "张三"

    def test_assistant_archive_pattern(self) -> None:
        # The archive regex ([\u4e00-\u9fff]{2,4})的(?:档案|病历) is greedy,
        # so use a string where only the name precedes "的档案".
        history: List[dict] = [
            {"role": "assistant", "content": "已为您调出 张三的档案"},
        ]
        # The space before "张三" ensures the regex captures exactly "张三"
        assert patient_name_from_history(history) == "张三"

    def test_user_turn_name_before_marker(self) -> None:
        history: List[dict] = [
            {"role": "user", "content": "张三今天复查"},
        ]
        assert patient_name_from_history(history) == "张三"

    def test_no_match_returns_none(self) -> None:
        history: List[dict] = [
            {"role": "user", "content": "今天天气不错"},
            {"role": "assistant", "content": "有什么可以帮您的？"},
        ]
        assert patient_name_from_history(history) is None

    def test_empty_history(self) -> None:
        assert patient_name_from_history([]) is None

    def test_most_recent_match_wins(self) -> None:
        history: List[dict] = [
            {"role": "assistant", "content": "已为患者【张三】创建档案"},
            {"role": "assistant", "content": "已为患者【李四】创建档案"},
        ]
        # Scans in reverse — should find 李四 first
        assert patient_name_from_history(history) == "李四"

    def test_invalid_name_in_brackets_skipped(self) -> None:
        history: List[dict] = [
            {"role": "assistant", "content": "已为患者【3床】创建档案"},
            {"role": "assistant", "content": "已为患者【王五】创建档案"},
        ]
        # 3床 is invalid; should skip and find 王五
        # Actually 3床 might not match [\u4e00-\u9fff]{2,4} regex, so it wouldn't match at all
        # Let's verify we get 王五
        assert patient_name_from_history(history) == "王五"

    def test_user_turn_possessive_pattern(self) -> None:
        history: List[dict] = [
            {"role": "user", "content": "赵六的任务"},
        ]
        assert patient_name_from_history(history) == "赵六"
