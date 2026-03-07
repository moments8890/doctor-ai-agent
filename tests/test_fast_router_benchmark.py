"""
E2E benchmark test for fast_router.py.

Run standalone to measure hit rate on realistic doctor inputs:
    pytest tests/test_fast_router_benchmark.py -v -s

This test does NOT call the LLM. It measures how many doctor inputs are
resolved by the fast router vs requiring LLM dispatch, and validates that
fast-routed results are correct for known cases.
"""

from __future__ import annotations

import time
from typing import Optional

import pytest

from services.fast_router import fast_route
from services.intent import Intent


# ---------------------------------------------------------------------------
# Realistic doctor input corpus (100 representative messages)
# Each entry: (text, expected_intent_or_None_for_llm)
# ---------------------------------------------------------------------------

_CORPUS: list[tuple[str, Optional[Intent]]] = [
    # ── list_patients ────────────────────────────────────────────────────────
    ("患者列表", Intent.list_patients),
    ("所有患者", Intent.list_patients),
    ("全部患者", Intent.list_patients),
    ("病人列表", Intent.list_patients),
    ("我的患者", Intent.list_patients),
    ("患者名单", Intent.list_patients),
    ("患者", Intent.list_patients),
    ("病人", Intent.list_patients),
    ("列出患者", Intent.list_patients),
    ("显示患者", Intent.list_patients),

    # ── list_tasks ───────────────────────────────────────────────────────────
    ("待办任务", Intent.list_tasks),
    ("任务列表", Intent.list_tasks),
    ("我的任务", Intent.list_tasks),
    ("查看任务", Intent.list_tasks),
    ("待办", Intent.list_tasks),
    ("任务", Intent.list_tasks),
    ("待处理", Intent.list_tasks),
    ("待办事项", Intent.list_tasks),
    ("待处理任务", Intent.list_tasks),
    ("查看待办", Intent.list_tasks),

    # ── query_records ─────────────────────────────────────────────────────────
    ("查张三", Intent.query_records),
    ("查询张三", Intent.query_records),
    ("查看李明", Intent.query_records),
    ("查张三病历", Intent.query_records),
    ("查询李明记录", Intent.query_records),
    ("张三的病历", Intent.query_records),
    ("李明的记录", Intent.query_records),
    ("王五的情况", Intent.query_records),
    ("张三病历", Intent.query_records),
    ("李明情况", Intent.query_records),
    ("查赵六", Intent.query_records),
    ("查看王五病历", Intent.query_records),
    ("张三的近况", Intent.query_records),
    ("李明的病情", Intent.query_records),

    # ── create_patient ────────────────────────────────────────────────────────
    ("新患者张三", Intent.create_patient),
    ("新病人李明", Intent.create_patient),
    ("建档王五", Intent.create_patient),
    ("张三建档", Intent.create_patient),
    ("添加患者赵六", Intent.create_patient),
    ("新患者张三，男，45岁", Intent.create_patient),
    ("新病人李红，女，30岁", Intent.create_patient),
    ("新建患者陈七", Intent.create_patient),
    ("加个患者周八", Intent.create_patient),

    # ── delete_patient ────────────────────────────────────────────────────────
    ("删除张三", Intent.delete_patient),
    ("删除患者李明", Intent.delete_patient),
    ("删掉王五", Intent.delete_patient),
    ("把张三删了", Intent.delete_patient),
    ("张三删掉", Intent.delete_patient),

    # ── complete_task ─────────────────────────────────────────────────────────
    ("完成任务1", Intent.complete_task),
    ("完成1", Intent.complete_task),
    ("完成任务三", Intent.complete_task),
    ("任务2完成", Intent.complete_task),
    ("标记完成3", Intent.complete_task),

    # ── query with new prefixes ───────────────────────────────────────────────
    ("帮我查张三", Intent.query_records),
    ("查一下李明", Intent.query_records),
    ("看一下王五的情况", Intent.query_records),

    # ── list with normalisation (polite particles stripped) ───────────────────
    ("帮我列出患者", Intent.list_patients),
    ("给我看看患者", Intent.list_patients),
    ("有哪些患者", Intent.list_patients),
    ("有哪些任务", Intent.list_tasks),
    ("显示待办", Intent.list_tasks),

    # ── create with new keyword ───────────────────────────────────────────────
    ("录入患者赵六", Intent.create_patient),

    # ── Tier 3 fast-route (clinical keywords → add_record, no routing LLM) ────
    ("张三，男，58岁，胸闷气促3天，BNP 980，EF 50%，心衰III级，给予利尿剂调整", Intent.add_record),
    ("李明发烧三天，体温38.5，咳嗽，给予对乙酰氨基酚退烧", Intent.add_record),
    ("王五腹痛，排除阑尾炎，建议观察48小时", Intent.add_record),
    ("张三心悸三天，心电图提示AF，给予倍他乐克12.5mg", Intent.add_record),
    ("李红，女，45岁，主诉：头痛两周，诊断：偏头痛，处置：布洛芬", Intent.add_record),
    ("患者主诉胸痛，查肌钙蛋白I 0.3，考虑急性心肌梗死，立即溶栓", Intent.add_record),
    ("随访：张三血糖控制良好，HbA1c 6.8%，继续二甲双胍", Intent.add_record),
    # ── Tier 3: 复查 (follow-up) in clinical note context → add_record ────────
    ("王五复查，血压稳定，120/80，继续当前方案", Intent.add_record),
    # ── LLM required (no strong clinical keyword — borderline cases) ──────────
    ("患者血压160/100，目前服用氨氯地平5mg，考虑加量", None),
    ("今天看了李明，他的情况明显改善了，可以减量", None),

    # ── LLM required (ambiguous / conversational) ─────────────────────────────
    ("你好", None),
    ("有什么问题可以问我", None),
    ("帮我一下", None),
    ("好的", None),
    ("确认", None),   # handled by pending_record gate, not fast_router
    ("取消", None),   # handled by pending_record gate, not fast_router
    ("张三怎么样了", None),   # ambiguous — "怎么样了" not a record keyword
    ("这个患者上次的检查结果", None),  # ambiguous
    ("帮我看看上次的记录", None),     # no patient name
    ("最近有什么新的任务", None),     # slightly ambiguous, but close to list_tasks
]


def test_fast_router_corpus_correctness():
    """Validate all corpus entries are routed correctly."""
    errors = []
    for text, expected in _CORPUS:
        result = fast_route(text)
        if expected is None:
            # Should NOT be fast-routed
            if result is not None:
                errors.append(f"FALSE POSITIVE: {text!r} → {result.intent} (expected LLM)")
        else:
            # Should be fast-routed to the correct intent
            if result is None:
                errors.append(f"MISS: {text!r} → None (expected {expected})")
            elif result.intent != expected:
                errors.append(f"WRONG INTENT: {text!r} → {result.intent} (expected {expected})")

    if errors:
        pytest.fail("\n".join(errors))


def test_fast_router_hit_rate_and_latency():
    """Measure hit rate and per-call latency across the corpus."""
    hits = 0
    llm_required = 0
    total_ns = 0

    for text, expected in _CORPUS:
        t0 = time.perf_counter_ns()
        result = fast_route(text)
        elapsed_ns = time.perf_counter_ns() - t0
        total_ns += elapsed_ns

        if result is not None:
            hits += 1
        else:
            llm_required += 1

    total = len(_CORPUS)
    hit_rate = hits / total * 100
    avg_us = (total_ns / total) / 1000

    print(f"\n{'='*60}")
    print(f"Fast Router Benchmark Results")
    print(f"{'='*60}")
    print(f"Total corpus entries : {total}")
    print(f"Fast-route hits      : {hits}  ({hit_rate:.1f}%)")
    print(f"LLM required         : {llm_required}  ({100 - hit_rate:.1f}%)")
    print(f"Avg latency/call     : {avg_us:.2f} µs")
    print(f"{'='*60}")
    print(f"Projected savings: {hits} × 6000ms = {hits * 6:.0f}s per {total}-turn session")
    print(f"Avg turn latency reduction: {hit_rate:.0f}% turns at ~0ms vs ~6000ms")

    # Assertions
    assert hit_rate >= 55, f"Hit rate {hit_rate:.1f}% below 55% target (Tier 3 clinical routes included)"
    assert avg_us < 1000, f"Avg latency {avg_us:.1f}µs too slow (should be <1000µs)"


def test_create_patient_name_extraction():
    """Verify name extraction is accurate for create_patient patterns."""
    cases = [
        ("新患者张三，男，45岁", "张三", "男", 45),
        ("新病人李红，女，30岁", "李红", "女", 30),
        ("新患者王五", "王五", None, None),
    ]
    for text, expected_name, expected_gender, expected_age in cases:
        r = fast_route(text)
        assert r is not None, f"Should match: {text}"
        assert r.patient_name == expected_name, f"{text}: name {r.patient_name} != {expected_name}"
        if expected_gender is not None:
            assert r.gender == expected_gender, f"{text}: gender {r.gender} != {expected_gender}"
        if expected_age is not None:
            assert r.age == expected_age, f"{text}: age {r.age} != {expected_age}"


def test_query_name_extraction():
    """Verify patient name is correctly extracted from query patterns."""
    cases = [
        ("查张三", "张三"),
        ("查询李明", "李明"),
        ("张三的病历", "张三"),
        ("王五情况", "王五"),
    ]
    for text, expected_name in cases:
        r = fast_route(text)
        assert r is not None and r.intent == Intent.query_records
        assert r.patient_name == expected_name, f"{text}: name {r.patient_name!r} != {expected_name!r}"
