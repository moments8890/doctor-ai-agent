"""
Unit tests for services/fast_router.py — tier 1/2 intent routing without LLM.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from services.ai.fast_router import fast_route, fast_route_label
from services.ai.intent import Intent


# ── list_patients ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "患者列表",
    "所有患者",
    "全部患者",
    "患者名单",
    "病人列表",
    "我的患者",
    "列出患者",
    "患者",
    "病人",
])
def test_list_patients_exact(text):
    r = fast_route(text)
    assert r is not None
    assert r.intent == Intent.list_patients


# ── list_tasks ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "待办任务",
    "任务列表",
    "我的任务",
    "查看任务",
    "待处理",
    "待办",
    "任务",
])
def test_list_tasks_exact(text):
    r = fast_route(text)
    assert r is not None
    assert r.intent == Intent.list_tasks


# ── query_records ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name", [
    ("查张三", "张三"),
    ("查询张三", "张三"),
    ("查看李明", "李明"),
    ("查张三病历", "张三"),
    ("查询李明记录", "李明"),
    ("张三的病历", "张三"),
    ("李明的记录", "李明"),
    ("王五的情况", "王五"),
    ("张三病历", "张三"),
    ("张三情况", "张三"),
    # New prefix variants
    ("帮我查张三", "张三"),
    ("查一下李明", "李明"),
    ("看一下王五的情况", "王五"),
    ("帮我查张三病历", "张三"),
])
def test_query_records_patterns(text, expected_name):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.query_records
    assert r.patient_name == expected_name


# ── create_patient ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name", [
    ("新患者张三", "张三"),
    ("新病人李明", "李明"),
    ("建档王五", "王五"),
    ("张三建档", "张三"),
    ("添加患者赵六", "赵六"),
])
def test_create_patient_patterns(text, expected_name):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.create_patient
    assert r.patient_name == expected_name


def test_create_patient_with_demographics():
    r = fast_route("新患者张三，男，45岁")
    assert r is not None
    assert r.intent == Intent.create_patient
    assert r.patient_name == "张三"
    assert r.gender == "男"
    assert r.age == 45


def test_create_patient_female():
    r = fast_route("新病人李红，女，30岁")
    assert r is not None
    assert r.intent == Intent.create_patient
    assert r.gender == "女"
    assert r.age == 30


# ── delete_patient ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name", [
    ("删除张三", "张三"),
    ("删除患者李明", "李明"),
    ("删掉王五", "王五"),
    # Trailing-keyword variants
    ("把张三删了", "张三"),
    ("张三删掉", "张三"),
    ("把李明删除", "李明"),
])
def test_delete_patient_patterns(text, expected_name):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.delete_patient
    assert r.patient_name == expected_name


# ── complete_task ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected_id", [
    ("完成任务1", 1),
    ("完成1", 1),
    ("完成任务三", 3),
    ("任务2完成", 2),
    ("标记完成3", 3),
    ("任务5做好了", 5),
    ("搞定任务二", 2),
])
def test_complete_task_patterns(text, expected_id):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.complete_task
    assert r.extra_data.get("task_id") == expected_id


# ── normalisation (polite particles) ───────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "帮我列出患者",
    "给我看看患者",
    "有哪些患者",
    "请列出患者",
])
def test_list_patients_normalised(text):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.list_patients


@pytest.mark.parametrize("text", [
    "有哪些任务",
    "显示待办",
    "请查看任务",
    "所有任务",
])
def test_list_tasks_normalised(text):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.list_tasks


# ── should NOT match (LLM fallback) ───────────────────────────────────────────

@pytest.mark.parametrize("text, expected_intent", [
    # Clinical notes → Tier 3 fast-routes directly to add_record
    ("张三，男，58岁，胸闷气促3天，BNP 980，EF 50%，心衰III级", Intent.add_record),
    ("李明发烧三天，体温38.5，给予退烧药", Intent.add_record),
    ("王五腹痛，排除阑尾炎，建议观察", Intent.add_record),
    # Ambiguous / conversational — still falls through to LLM
    ("你好", None),
    ("有问题", None),
    ("帮我一下", None),
    ("张三怎么样", None),
    # Empty / whitespace
    ("", None),
    ("  ", None),
])
def test_clinical_and_llm_cases(text, expected_intent):
    r = fast_route(text)
    if expected_intent is None:
        assert r is None, f"fast_route({text!r}) should return None, got {r}"
    else:
        assert r is not None, f"fast_route({text!r}) should match Tier 3 add_record"
        assert r.intent == expected_intent


def test_empty_returns_none():
    assert fast_route("") is None
    assert fast_route("  ") is None


# ── fast_route_label ───────────────────────────────────────────────────────────

def test_fast_route_label_hit():
    assert fast_route_label("患者列表") == "fast:list_patients"
    assert fast_route_label("待办") == "fast:list_tasks"
    assert fast_route_label("查张三") == "fast:query_records"


def test_fast_route_label_miss():
    # Ambiguous messages without clinical keywords still fall through to LLM
    assert fast_route_label("张三怎么样了") == "llm"
    assert fast_route_label("你好") == "llm"


def test_fast_route_label_tier3():
    # Clinical messages fast-route to add_record (Tier 3), not LLM.
    # Messages with a doctor anchor (name+gender+age, 给予, 患者…) are fast-routed.
    # Ambiguous short notes without anchor (e.g. bare "张三胸闷三天") fall to LLM
    # since the TF-IDF classifier cannot distinguish them from patient symptom reports.
    assert fast_route_label("张三，男，42岁，胸闷三天") == "fast:add_record"
    assert fast_route_label("李明胸闷三天，给予扩冠治疗") == "fast:add_record"


# ── Benchmark: coverage measurement ───────────────────────────────────────────

_SAMPLE_CLINICAL_INPUTS = [
    # Expected fast-route hits — Tier 1/2
    ("患者列表", Intent.list_patients),
    ("所有患者", Intent.list_patients),
    ("待办任务", Intent.list_tasks),
    ("任务", Intent.list_tasks),
    ("查张三", Intent.query_records),
    ("张三的病历", Intent.query_records),
    ("新患者李明", Intent.create_patient),
    ("删除王五", Intent.delete_patient),
    # Expected fast-route hits — Tier 3 (clinical keywords)
    ("张三心悸三天，给予倍他乐克", Intent.add_record),
    # Expected LLM fallback (no strong clinical keyword)
    ("李明血压160/100，建议调整降压药", None),
    ("你好", None),
]


def test_fast_route_hit_rate():
    """Measure and log fast-route hit rate on sample inputs."""
    hits = 0
    for text, expected_intent in _SAMPLE_CLINICAL_INPUTS:
        result = fast_route(text)
        if expected_intent is not None:
            assert result is not None, f"Expected fast-route for {text!r}"
            assert result.intent == expected_intent
            hits += 1
        else:
            assert result is None, f"Expected LLM fallback for {text!r}, got {result}"

    expected_hits = sum(1 for _, ei in _SAMPLE_CLINICAL_INPUTS if ei is not None)
    rate = hits / len(_SAMPLE_CLINICAL_INPUTS) * 100
    print(f"\nFast-route hit rate: {hits}/{len(_SAMPLE_CLINICAL_INPUTS)} = {rate:.0f}%")
    assert hits == expected_hits


# ── Tier 2.5: update_record correction ─────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name", [
    ("刚才李波的主诉写错了，应该是胸痛不是胸闷", "李波"),
    ("刚才陈刚的诊断写错了，应更正为STEMI", "陈刚"),
    ("上一条张三的病历有误，主诉改为头痛", "张三"),
    ("刚才写错了，主诉应该是心悸", None),        # no name → name=None, still update_record
    ("病历写错了，诊断改为高血压", None),
])
def test_correction_update_record(text, expected_name):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.update_record
    assert r.patient_name == expected_name


# ── Tier 2: update_patient demographics ────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name, expected_gender, expected_age", [
    ("修改王明的年龄为50岁", "王明", None, 50),
    ("更新李华的性别为女", "李华", "女", None),
    ("把张三的年龄改成40岁", "张三", None, 40),
    ("王明的年龄应该是50岁", "王明", None, 50),
    ("李华的性别改为男", "李华", "男", None),
])
def test_update_patient_demographics(text, expected_name, expected_gender, expected_age):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.update_patient
    assert r.patient_name == expected_name
    if expected_gender is not None:
        assert r.gender == expected_gender
    if expected_age is not None:
        assert r.age == expected_age


# ── Tier 2: supplement / record continuation ────────────────────────────────────

@pytest.mark.parametrize("text", [
    "补充：建议随访两周",
    "补一句：患者否认过敏史",
    "再补充建议复查心电图",
    "加上：既往高血压病史",
])
def test_supplement_routes_add_record(text):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.add_record


# ── False-positive guards ───────────────────────────────────────────────────────

def test_create_not_triggered_by_jiandanbing_bao():
    """'建档并保存本次病历' must NOT extract '并保' as patient name."""
    r = fast_route("请建档并保存本次病历")
    # Should fall through (None) or route as something other than create_patient
    if r is not None:
        assert r.intent != Intent.create_patient, (
            "False positive: '建档并保存' should not match create_patient"
        )


def test_update_patient_not_triggered_by_domain_keywords():
    """'修改病历的年龄' should not extract '病历' as patient name."""
    r = fast_route("修改病历的年龄为50岁")
    # Either falls through (None) or doesn't route as update_patient with '病历' as name
    if r is not None and r.intent == Intent.update_patient:
        assert r.patient_name != "病历"


def test_correction_name_not_domain_keyword():
    """'上一条病历的诊断有误' should not extract '病历' as patient name."""
    r = fast_route("上一条病历的诊断有误，应更正")
    if r is not None:
        assert r.intent == Intent.update_record
        assert r.patient_name != "病历"


# ── export_records ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name", [
    ("导出张三的病历", "张三"),
    ("帮我导出李明的记录", "李明"),
    ("打印王五的报告", "王五"),
    ("下载陈刚的病历PDF", "陈刚"),
])
def test_export_records_with_name(text, expected_name):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.export_records
    assert r.patient_name == expected_name


@pytest.mark.parametrize("text", [
    "导出当前患者的病历",
    "帮我导出这位患者的记录",
    "下载病历",
])
def test_export_records_no_name(text):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.export_records


# ── export_outpatient_report ───────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name", [
    ("生成张三的标准门诊病历", "张三"),
    ("帮我生成李明的门诊病历", "李明"),
    ("导出王五的卫生部病历", "王五"),
    ("打印陈刚的正式病历", "陈刚"),
])
def test_export_outpatient_report_with_name(text, expected_name):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.export_outpatient_report
    assert r.patient_name == expected_name


@pytest.mark.parametrize("text", [
    "生成门诊病历",
    "帮我生成标准门诊病历",
    "导出当前患者的标准病历",
])
def test_export_outpatient_report_no_name(text):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.export_outpatient_report


# ── Tier 3 edge cases ──────────────────────────────────────────────────────────

def test_tier3_fucha_with_reminder_falls_through():
    """'帮我设今天18:00复查提醒' — 复查 alone with reminder context → LLM fallback."""
    r = fast_route("帮我设今天18:00复查提醒")
    assert r is None, "复查 + 提醒 should fall through to LLM, not Tier 3 add_record"


def test_tier3_clinical_keyword_routes_add_record():
    """A message with high-specificity clinical keywords → add_record via Tier 3."""
    r = fast_route("患者心悸3天，BNP升高，考虑心衰")
    assert r is not None
    assert r.intent == Intent.add_record


def test_tier3_stemi_correction_routes_update_record_not_add():
    """A correction message containing STEMI keyword must route update_record, not add_record."""
    r = fast_route("刚才陈刚的诊断写错了，应更正诊断为STEMI，请更正上一条病历")
    assert r is not None
    assert r.intent == Intent.update_record, (
        "Correction message with clinical keyword must be update_record, not add_record"
    )
    assert r.patient_name == "陈刚"


# ── delete_patient with occurrence index ────────────────────────────────────────

@pytest.mark.parametrize("text, expected_name, expected_occurrence", [
    ("删除第2个患者张三", "张三", 2),
    ("删除第一个患者李明", "李明", 1),
    ("如果有重复名字，删除第二个患者王五", "王五", 2),
])
def test_delete_patient_occurrence_index(text, expected_name, expected_occurrence):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.delete_patient
    assert r.patient_name == expected_name
    assert r.extra_data.get("occurrence_index") == expected_occurrence


# ── Fix 1: hot-reload accumulation bug ─────────────────────────────────────────

def test_reload_extra_keywords_does_not_accumulate():
    """Calling reload_extra_keywords() twice must not grow _CLINICAL_KW_TIER3.

    The bug: line 499 merged _EXTRA_KW_TIER3 into _CLINICAL_KW_TIER3 each call,
    so removed keywords persisted across hot-reloads.
    """
    import services.ai.fast_router as fr

    # Save ALL module globals that load_extra_keywords() may modify
    saved = {
        "_EXTRA_KW_TIER3": fr._EXTRA_KW_TIER3,
        "_IMPORT_KEYWORDS": fr._IMPORT_KEYWORDS,
        "_LIST_PATIENTS_EXACT": fr._LIST_PATIENTS_EXACT,
        "_LIST_PATIENTS_SHORT": fr._LIST_PATIENTS_SHORT,
        "_LIST_TASKS_EXACT": fr._LIST_TASKS_EXACT,
        "_LIST_TASKS_SHORT": fr._LIST_TASKS_SHORT,
        "_NON_NAME_KEYWORDS": fr._NON_NAME_KEYWORDS,
        "_CLINICAL_KW_TIER3": fr._CLINICAL_KW_TIER3,
        "_TIER3_BAD_NAME": fr._TIER3_BAD_NAME,
    }

    kw_data = {
        "tier3": {
            "test_cat": {"keywords": ["独特临床术语A", "独特临床术语B"]}
        }
    }
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(kw_data, f, ensure_ascii=False)
            tmp_path = f.name

        # Capture the baseline before any test-specific load
        baseline_size = len(fr._CLINICAL_KW_TIER3)

        # Load once — adds test keywords
        fr.load_extra_keywords(tmp_path)
        assert "独特临床术语A" in fr._EXTRA_KW_TIER3
        size_after_first = len(fr._CLINICAL_KW_TIER3)

        # Load again with same file — _CLINICAL_KW_TIER3 must NOT grow
        fr.load_extra_keywords(tmp_path)
        assert len(fr._CLINICAL_KW_TIER3) == size_after_first, (
            "_CLINICAL_KW_TIER3 grew on second reload — accumulation bug present"
        )

        # Swap to a smaller keyword set — old keywords must NOT persist in _EXTRA_KW_TIER3
        kw_data2 = {"tier3": {"test_cat": {"keywords": ["独特临床术语C"]}}}
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(kw_data2, f, ensure_ascii=False)

        fr.load_extra_keywords(tmp_path)
        assert "独特临床术语A" not in fr._EXTRA_KW_TIER3, (
            "Removed keyword still in _EXTRA_KW_TIER3 after hot-reload"
        )
        assert "独特临床术语C" in fr._EXTRA_KW_TIER3

        # _is_clinical_tier3 must reflect the new set (A gone, C present)
        from services.ai.fast_router import _is_clinical_tier3
        # C is present — clinical check should pass on a clearly clinical message containing C
        assert _is_clinical_tier3("患者独特临床术语C三天，给予治疗")
    finally:
        # Restore all module globals to prevent state leakage between tests
        for attr, val in saved.items():
            setattr(fr, attr, val)
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


# ── Fix 2: query_records name extraction consistent with update_record ──────────

def test_query_records_rejects_tier3_bad_name():
    """Names in _TIER3_BAD_NAME must be rejected in query_records, not just update_record."""
    import services.ai.fast_router as fr
    original = fr._TIER3_BAD_NAME
    try:
        fr._TIER3_BAD_NAME = frozenset({"病历", "记录"})
        # "查病历" — '病历' is a bad name, should fall through or not extract '病历' as name
        r = fast_route("查病历")
        if r is not None and r.intent == Intent.query_records:
            assert r.patient_name != "病历", "Bad name '病历' should not be extracted in query_records"
    finally:
        fr._TIER3_BAD_NAME = original


# ── Fix 3: mined_rules structured extraction ────────────────────────────────────

def test_mined_rules_patient_name_group_extraction():
    """patient_name_group in a mined rule extracts name from the regex capture group."""
    import services.ai.fast_router as fr
    rules_json = json.dumps([
        {
            "intent": "query_records",
            "patterns": [r"^找(?P<dummy>.{0,5})?(\S{2,3})的资料$"],
            "patient_name_group": 2,
            "enabled": True,
        }
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(rules_json)
        tmp = f.name

    original_rules = fr._MINED_RULES
    try:
        fr.load_mined_rules(tmp)
        r = fast_route("找张三的资料")
        assert r is not None, "Mined rule should have matched"
        assert r.intent == Intent.query_records
        assert r.patient_name == "张三"
    finally:
        fr._MINED_RULES = original_rules
        Path(tmp).unlink(missing_ok=True)


def test_mined_rules_extra_data_static():
    """extra_data dict from mined rule is included in IntentResult."""
    import services.ai.fast_router as fr
    rules_json = json.dumps([
        {
            "intent": "add_record",
            "patterns": [r"^【紧急】"],
            "extra_data": {"source": "mined", "priority": "high"},
            "enabled": True,
        }
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(rules_json)
        tmp = f.name

    original_rules = fr._MINED_RULES
    try:
        fr.load_mined_rules(tmp)
        r = fast_route("【紧急】患者心跳骤停")
        assert r is not None
        assert r.extra_data.get("source") == "mined"
        assert r.extra_data.get("priority") == "high"
    finally:
        fr._MINED_RULES = original_rules
        Path(tmp).unlink(missing_ok=True)


def test_mined_rules_confidence_field():
    """confidence field from mined rule propagates to IntentResult."""
    import services.ai.fast_router as fr
    rules_json = json.dumps([
        {
            "intent": "add_record",
            "patterns": [r"^医嘱[：:]"],
            "confidence": 0.85,
            "enabled": True,
        }
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(rules_json)
        tmp = f.name

    original_rules = fr._MINED_RULES
    try:
        fr.load_mined_rules(tmp)
        r = fast_route("医嘱：阿司匹林100mg qd")
        assert r is not None
        assert r.intent == Intent.add_record
        assert abs(r.confidence - 0.85) < 0.001
    finally:
        fr._MINED_RULES = original_rules
        Path(tmp).unlink(missing_ok=True)


# ── Fix 4: mined_rules error logging (not silent) ──────────────────────────────

def test_mined_rules_logs_unknown_intent(caplog):
    """Rules with unknown intent values must be logged and skipped, not silently dropped."""
    import logging
    import services.ai.fast_router as fr

    rules_json = json.dumps([
        {"intent": "not_a_real_intent", "patterns": [r"^test"], "enabled": True},
        {"intent": "add_record", "patterns": [r"^valid_test_prefix_xyz"], "enabled": True},
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(rules_json)
        tmp = f.name

    original_rules = fr._MINED_RULES
    log_messages: list[str] = []
    import utils.log as log_mod
    original_log_fn = log_mod.log

    def capturing_log(msg, *args, **kwargs):
        log_messages.append(str(msg))
        original_log_fn(msg, *args, **kwargs)

    try:
        log_mod.log = capturing_log
        fr.load_mined_rules(tmp)
        # Valid rule should still be loaded
        assert len(fr._MINED_RULES) == 1
        assert fr._MINED_RULES[0]["intent"] == "add_record"
        # Unknown intent should have been logged
        assert any("not_a_real_intent" in m for m in log_messages), (
            "Expected log message about unknown intent, got: " + str(log_messages)
        )
    finally:
        fr._MINED_RULES = original_rules
        log_mod.log = original_log_fn
        Path(tmp).unlink(missing_ok=True)


def test_mined_rules_logs_invalid_regex(caplog):
    """Rules with invalid regex patterns must be logged and skipped."""
    import services.ai.fast_router as fr
    import utils.log as log_mod

    rules_json = json.dumps([
        {"intent": "add_record", "patterns": [r"[invalid(regex"], "enabled": True},
        {"intent": "add_record", "patterns": [r"^valid_xyz_prefix"], "enabled": True},
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(rules_json)
        tmp = f.name

    original_rules = fr._MINED_RULES
    log_messages = []
    original_log_fn = log_mod.log

    def capturing_log(msg, *args, **kwargs):
        log_messages.append(msg)
        original_log_fn(msg, *args, **kwargs)

    try:
        log_mod.log = capturing_log
        fr.load_mined_rules(tmp)
        # Valid rule still loaded
        assert len(fr._MINED_RULES) == 1
        # Invalid regex should have been logged
        assert any("invalid" in m.lower() or "pattern" in m.lower() for m in log_messages), (
            "Expected log about invalid pattern, got: " + str(log_messages)
        )
    finally:
        fr._MINED_RULES = original_rules
        log_mod.log = original_log_fn
        Path(tmp).unlink(missing_ok=True)


# ── Question guard decomposition: _is_patient_question sub-groups ──────────────

def test_qg_colloquial_blocks_basic_questions():
    """_QG_COLLOQUIAL_RE should block common lay question phrases."""
    from services.ai.fast_router import _is_patient_question
    assert _is_patient_question("胸痛怎么办")
    assert _is_patient_question("会不会有心脏病")
    assert _is_patient_question("正常吗")
    assert _is_patient_question("能否服用阿司匹林")
    assert _is_patient_question("是不是高血压")


def test_qg_ending_particle_blocks_question_marks():
    """_QG_ENDING_PARTICLE_RE should block messages ending with ？ or soft particles."""
    from services.ai.fast_router import _is_patient_question
    assert _is_patient_question("血压高吗？")
    assert _is_patient_question("这是什么病呢")
    assert _is_patient_question("需要手术吗")
    assert _is_patient_question("引起的？")


def test_qg_consult_opener_blocks_consultation_phrases():
    """_QG_CONSULT_OPENER_RE should block patient consultation-seeking openers."""
    from services.ai.fast_router import _is_patient_question
    assert _is_patient_question("请问医生，我头痛")
    assert _is_patient_question("想咨询一下高血压的问题")
    assert _is_patient_question("谢谢医生")


def test_qg_mcq_stem_blocks_exam_question_words():
    """_QG_MCQ_STEM_RE should block messages with MCQ question words."""
    from services.ai.fast_router import _is_patient_question
    assert _is_patient_question("下列哪项不符合心肌梗死")
    assert _is_patient_question("哪种药物首选")
    assert _is_patient_question("何药治疗")


def test_qg_knowledge_query_blocks_disease_lookups():
    """_QG_KNOWLEDGE_QUERY_RE should block disease knowledge queries."""
    from services.ai.fast_router import _is_patient_question
    assert _is_patient_question("高血压的治疗方法")
    assert _is_patient_question("心衰的并发症有哪些")
    assert _is_patient_question("糖尿病的危害")


def test_qg_family_ref_blocks_family_descriptions():
    """_QG_FAMILY_REF_RE should block messages describing family members' conditions."""
    from services.ai.fast_router import _is_patient_question
    assert _is_patient_question("我妈最近血压高")
    assert _is_patient_question("我老公心悸三天")


def test_is_patient_question_does_not_block_clinical_note():
    """Doctor clinical notes should NOT be flagged as patient questions."""
    from services.ai.fast_router import _is_patient_question
    assert not _is_patient_question("患者张三，男，58岁，劳力性胸闷3天，BNP 1200")
    assert not _is_patient_question("给予阿司匹林100mg qd，倍他乐克25mg bid")
    assert not _is_patient_question("诊断：不稳定型心绞痛，建议住院")


# ── Multi-turn context: session patient_name backfill ─────────────────────────

class _FakeSession:
    """Minimal session stub for testing."""
    def __init__(self, name=None, patient_id=None):
        self.current_patient_name = name
        self.current_patient_id = patient_id


def test_session_backfills_name_for_supplement():
    """'补充：…' routes add_record with no name; session should fill in patient_name."""
    sess = _FakeSession(name="张三")
    r = fast_route("补充：建议复查心电图", session=sess)
    assert r is not None
    assert r.intent == Intent.add_record
    assert r.patient_name == "张三"


def test_session_does_not_override_explicit_name():
    """When the message already has a name, session must NOT override it."""
    sess = _FakeSession(name="李明")
    r = fast_route("查张三的病历", session=sess)
    assert r is not None
    assert r.intent == Intent.query_records
    assert r.patient_name == "张三"  # explicitly extracted, not overridden by session


def test_session_not_applied_to_non_patient_intents():
    """list_patients / list_tasks do not need a patient name — session must not inject one."""
    sess = _FakeSession(name="张三")
    r = fast_route("患者列表", session=sess)
    assert r is not None
    assert r.intent == Intent.list_patients
    assert r.patient_name is None


def test_no_session_still_works():
    """fast_route without session parameter (default None) must be unchanged."""
    r = fast_route("补充：血压稳定")
    assert r is not None
    assert r.intent == Intent.add_record
    assert r.patient_name is None  # no session, no backfill


def test_session_with_none_name_does_not_inject():
    """Session with current_patient_name=None must not inject patient_name."""
    sess = _FakeSession(name=None)
    r = fast_route("补充：建议随访", session=sess)
    assert r is not None
    assert r.patient_name is None


def test_session_backfills_outpatient_report():
    """export_outpatient_report with no name should get session patient_name."""
    sess = _FakeSession(name="王五")
    r = fast_route("生成门诊病历", session=sess)
    assert r is not None
    assert r.intent == Intent.export_outpatient_report
    assert r.patient_name == "王五"
