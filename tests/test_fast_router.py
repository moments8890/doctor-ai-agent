"""
Unit tests for services/fast_router.py — tier 1/2 intent routing without LLM.
"""

from __future__ import annotations

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
    # Clinical messages fast-route to add_record (Tier 3), not LLM
    assert fast_route_label("张三胸闷三天") == "fast:add_record"


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
