"""Tests for services.domain.compound_normalizer — residual-text detection,
same-turn correction detection, and secondary-intent signal patterns.
"""

from __future__ import annotations

import pytest

from services.domain.compound_normalizer import (
    CONJUNCTION_RE,
    QUERY_VERB_RE,
    WRITE_VERB_RE,
    detect_same_turn_correction,
    has_residual_clinical_content,
)


# ── has_residual_clinical_content ────────────────────────────────────────────


class TestResidualClinicalContent:
    """Residual-text approach must work across all specialties — not just
    cardiology keywords."""

    def test_create_with_clinical_text_cardiology(self):
        has, residual = has_residual_clinical_content(
            "创建张三，男，45岁，胸痛2小时",
            patient_name="张三", gender="男", age=45,
        )
        assert has is True
        assert "胸痛" in residual

    def test_create_with_clinical_text_dermatology(self):
        """Non-cardiology specialty: dermatology."""
        has, residual = has_residual_clinical_content(
            "新建患者李明，女，32岁，皮疹3天伴瘙痒",
            patient_name="李明", gender="女", age=32,
        )
        assert has is True
        assert "皮疹" in residual

    def test_create_with_clinical_text_orthopedics(self):
        """Non-cardiology specialty: orthopedics."""
        has, residual = has_residual_clinical_content(
            "帮我录入新患者王伟，男，60岁，腰椎间盘突出复查",
            patient_name="王伟", gender="男", age=60,
        )
        assert has is True
        assert "腰椎" in residual

    def test_create_with_clinical_text_neurology(self):
        """Non-cardiology specialty: neurology."""
        has, residual = has_residual_clinical_content(
            "创建赵六，男，70岁，头晕伴右侧肢体麻木",
            patient_name="赵六", gender="男", age=70,
        )
        assert has is True
        assert "头晕" in residual

    def test_create_with_clinical_text_oncology(self):
        """Oncology with English abbreviation."""
        has, residual = has_residual_clinical_content(
            "新建陈七，女，55岁，HER2阳性乳腺癌术后化疗",
            patient_name="陈七", gender="女", age=55,
        )
        assert has is True
        assert "HER2" in residual

    def test_create_plain_no_clinical(self):
        """Pure demographics — no clinical content."""
        has, residual = has_residual_clinical_content(
            "创建张三，男，45岁",
            patient_name="张三", gender="男", age=45,
        )
        assert has is False

    def test_create_only_name(self):
        has, residual = has_residual_clinical_content(
            "创建李四",
            patient_name="李四",
        )
        assert has is False

    def test_empty_text(self):
        has, residual = has_residual_clinical_content("")
        assert has is False
        assert residual == ""

    def test_clinical_text_without_create_prefix(self):
        """Plain clinical text (add_record style) passes through."""
        has, residual = has_residual_clinical_content(
            "张三，STEMI，急诊PCI术后2天",
            patient_name="张三",
        )
        assert has is True
        assert "STEMI" in residual


# ── detect_same_turn_correction ──────────────────────────────────────────────


class TestSameTurnCorrection:
    def test_correction_explicit(self):
        assert detect_same_turn_correction("胸痛，说错了，头痛") is True

    def test_correction_negation(self):
        assert detect_same_turn_correction("不对，应该是高血压") is True

    def test_correction_rewrite(self):
        assert detect_same_turn_correction("诊断改为高血压") is True

    def test_correction_update_verb(self):
        assert detect_same_turn_correction("主诉更正为头痛3天") is True

    def test_no_correction_normal_text(self):
        assert detect_same_turn_correction("张三，胸痛2小时") is False

    def test_no_correction_empty(self):
        assert detect_same_turn_correction("") is False


# ── Signal regexes ───────────────────────────────────────────────────────────


class TestSignalRegexes:
    def test_conjunction_with_separator(self):
        """Conjunction must be preceded by a separator to fire."""
        assert CONJUNCTION_RE.search("查一下张三，然后录入新记录")
        assert CONJUNCTION_RE.search("删除张三；再创建李四")

    def test_conjunction_without_separator_does_not_match(self):
        """Clinical narrative with '然后' should NOT match (no separator)."""
        assert CONJUNCTION_RE.search("胸痛然后做了PCI") is None

    def test_write_verb(self):
        assert WRITE_VERB_RE.search("录入新记录")
        assert WRITE_VERB_RE.search("创建患者")

    def test_query_verb(self):
        assert QUERY_VERB_RE.search("查看病历")
        assert QUERY_VERB_RE.search("查一下张三")
