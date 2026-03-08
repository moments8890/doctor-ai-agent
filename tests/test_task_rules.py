"""
Tests for rule-based auto task detection (services/notify/task_rules.py).
"""
from __future__ import annotations

import pytest
from services.notify.task_rules import detect_auto_tasks, refine_due_days, AutoTaskSpec


# ---------------------------------------------------------------------------
# detect_auto_tasks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content, expected_types", [
    # lab_review triggers
    ("已开化验单，等检验结果。", {"lab_review"}),
    ("查血、血常规、肝功，5天后复查。", {"lab_review"}),
    ("BNP 980，等待结果。", {"lab_review"}),
    # referral
    ("建议转诊至心内科。", {"referral"}),
    ("请外科会诊，已写介绍信。", {"referral"}),
    # imaging
    ("3天后复查CT。", {"imaging"}),
    ("待影像结果后调整方案。", {"imaging"}),
    # medication
    ("新开药：氨氯地平 5mg qd，定期服药。", {"medication"}),
    ("换药，调整用药，bid给药。", {"medication"}),
    # multiple signals
    ("已开化验单，同时建议转诊至上级医院，复查CT。", {"lab_review", "referral", "imaging"}),
    # no signal
    ("血压 130/80，病情稳定，继续观察。", set()),
    ("", set()),
])
def test_detect_auto_tasks_types(content, expected_types):
    specs = detect_auto_tasks(content, "张三")
    actual_types = {s.task_type for s in specs}
    assert actual_types == expected_types, f"content={content!r}: expected {expected_types}, got {actual_types}"


def test_detect_auto_tasks_title_contains_patient_name():
    specs = detect_auto_tasks("化验单已开。", "李明")
    assert specs
    assert "李明" in specs[0].title


def test_detect_auto_tasks_suppressed():
    """If suppression keyword present, rule should not fire."""
    specs = detect_auto_tasks("化验单已回，结果正常。", "张三")
    types = {s.task_type for s in specs}
    assert "lab_review" not in types


def test_detect_auto_tasks_empty_patient_name():
    specs = detect_auto_tasks("化验单已开。", "")
    assert specs
    assert specs[0].task_type == "lab_review"


# ---------------------------------------------------------------------------
# refine_due_days
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content, default, expected", [
    ("5天后复查", 7, 5),
    ("三天后复查CT", 7, 3),
    ("两周后随访", 7, 14),
    ("一个月后复查", 30, 30),
    ("病情稳定", 5, 5),   # no time mention → use default
    ("", 3, 3),
    # relative time expressions
    ("下周复查", 5, 7),
    ("下个月随访", 5, 30),
    ("下个周复查", 5, 7),
])
def test_refine_due_days(content, default, expected):
    assert refine_due_days(content, default) == expected


# ---------------------------------------------------------------------------
# fast_router integration
# ---------------------------------------------------------------------------

from services.ai.fast_router import fast_route
from services.ai.intent import Intent


@pytest.mark.parametrize("text, expected_intent, expected_name", [
    ("给张三设3个月后随访提醒", Intent.schedule_follow_up, "张三"),
    ("给李明设下周随访", Intent.schedule_follow_up, "李明"),
    ("3个月后随访王五", Intent.schedule_follow_up, "王五"),
])
def test_fast_route_schedule_follow_up(text, expected_intent, expected_name):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == expected_intent
    assert r.patient_name == expected_name


@pytest.mark.parametrize("text, expected_task_id", [
    ("取消任务3", 3),
    ("任务5取消", 5),
    ("取消第2个任务", 2),
])
def test_fast_route_cancel_task(text, expected_task_id):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.cancel_task
    assert r.extra_data.get("task_id") == expected_task_id


@pytest.mark.parametrize("text, expected_task_id, expected_days", [
    ("推迟任务3一周", 3, 7),
    ("推迟任务2三天", 2, 3),
    ("任务4延后两天", 4, 2),
])
def test_fast_route_postpone_task(text, expected_task_id, expected_days):
    r = fast_route(text)
    assert r is not None, f"fast_route({text!r}) returned None"
    assert r.intent == Intent.postpone_task
    assert r.extra_data.get("task_id") == expected_task_id
    assert r.extra_data.get("delta_days") == expected_days
