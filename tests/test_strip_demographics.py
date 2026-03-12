"""Tests for strip_leading_create_demographics — entity-based demographic stripping."""

import pytest
from services.domain.text_cleanup import strip_leading_create_demographics


class TestStripLeadingCreateDemographics:
    """Verifies that command prefixes and demographic segments are stripped while
    clinical content is preserved."""

    def test_full_compound_message(self):
        """帮我创建患者张三，男，52岁，胸闷两天 → 胸闷两天"""
        result = strip_leading_create_demographics(
            "帮我创建患者张三，男，52岁，胸闷两天",
            patient_name="张三", gender="男", age=52,
        )
        assert result == "胸闷两天"

    def test_verb_only_prefix(self):
        """新建病人王五，咳嗽一周 → 咳嗽一周"""
        result = strip_leading_create_demographics(
            "新建病人王五，咳嗽一周",
            patient_name="王五",
        )
        assert result == "咳嗽一周"

    def test_name_then_clinical(self):
        """张三 胸痛两小时 (no verb, just name + content)"""
        result = strip_leading_create_demographics(
            "张三 胸痛两小时",
            patient_name="张三",
        )
        assert result == "胸痛两小时"

    def test_name_gender_age_with_spaces(self):
        """录入新患者 李四 女 65岁 主诉头痛"""
        result = strip_leading_create_demographics(
            "录入新患者 李四 女 65岁 主诉头痛",
            patient_name="李四", gender="女", age=65,
        )
        assert result == "主诉头痛"

    def test_gender_suffix_xing(self):
        """创建患者赵六，男性，40岁，ST段抬高"""
        result = strip_leading_create_demographics(
            "创建患者赵六，男性，40岁，ST段抬高",
            patient_name="赵六", gender="男", age=40,
        )
        assert result == "ST段抬高"

    def test_no_entities_returns_text(self):
        """When no entities are provided, only command verbs are stripped."""
        result = strip_leading_create_demographics(
            "创建患者张三，男，52岁，胸闷两天",
        )
        # Name/gender/age stay since no entities were provided
        assert "张三" in result
        assert "胸闷两天" in result

    def test_empty_text(self):
        assert strip_leading_create_demographics("") == ""

    def test_none_text(self):
        assert strip_leading_create_demographics(None) == ""

    def test_clinical_only_text_unchanged(self):
        """If text starts with clinical content, nothing is stripped."""
        result = strip_leading_create_demographics(
            "胸闷两天，反复发作",
            patient_name="张三", gender="男", age=52,
        )
        assert result == "胸闷两天，反复发作"

    def test_please_prefix(self):
        """请录入患者刘七 女 38岁 发热三天 → 发热三天"""
        result = strip_leading_create_demographics(
            "请录入患者刘七 女 38岁 发热三天",
            patient_name="刘七", gender="女", age=38,
        )
        assert result == "发热三天"

    def test_add_verb(self):
        """添加患者陈八，男，70岁，BNP升高 → BNP升高"""
        result = strip_leading_create_demographics(
            "添加患者陈八，男，70岁，BNP升高",
            patient_name="陈八", gender="男", age=70,
        )
        assert result == "BNP升高"

    def test_partial_demographics_name_age_no_gender(self):
        """创建张三 52岁 心悸 → 心悸"""
        result = strip_leading_create_demographics(
            "创建张三 52岁 心悸",
            patient_name="张三", age=52,
        )
        assert result == "心悸"

    def test_period_separator_after_age(self):
        """创建患者张三，男，52岁。胸闷两天 → 胸闷两天"""
        result = strip_leading_create_demographics(
            "创建患者张三，男，52岁。胸闷两天",
            patient_name="张三", gender="男", age=52,
        )
        assert result == "胸闷两天"

    def test_intent_result_object(self):
        """Accepts an IntentResult-like object."""
        from services.ai.intent import IntentResult, Intent
        ir = IntentResult(
            intent=Intent.create_patient,
            patient_name="张三",
            gender="男",
            age=52,
        )
        result = strip_leading_create_demographics(
            "帮我创建患者张三，男，52岁，胸闷两天", ir,
        )
        assert result == "胸闷两天"

    def test_quantifier_yi_ge(self):
        """新建一个患者李四 咳嗽 → 咳嗽"""
        result = strip_leading_create_demographics(
            "新建一个患者李四 咳嗽",
            patient_name="李四",
        )
        assert result == "咳嗽"
