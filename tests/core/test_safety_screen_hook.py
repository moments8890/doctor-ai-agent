"""SafetyScreenHook — keyword-based danger-signal screener for neuro records.

Runs on both patient-mode and doctor-mode. Notification is best-effort —
failures are logged and swallowed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.hooks.safety import SafetyScreenHook
from domain.intake.protocols import PersistRef, SessionState


def _session(mode: str = "patient") -> SessionState:
    return SessionState(
        id="s1",
        doctor_id="d1",
        patient_id=42,
        mode=mode,
        status="confirmed",
        template_id="medical_neuro_v1",
        collected={},
        conversation=[],
        turn_count=5,
    )


def _ref(rid: int = 99) -> PersistRef:
    return PersistRef(kind="medical_record", id=rid)


@pytest.mark.asyncio
async def test_no_keywords_no_notification_no_log():
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "头晕一周",
        "present_illness": "偶有恶心",
        "neuro_exam": "GCS 15，肌力正常",
        "_patient_name": "王五",
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_notify, patch(
        "domain.intake.hooks.safety.log",
    ) as mock_log:
        await hook.run(_session(), _ref(), collected)

    mock_notify.assert_not_called()
    mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_single_keyword_in_chief_complaint_triggers_notification():
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "患者出现剧烈头痛2小时",
        "_patient_name": "王五",
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_notify, patch(
        "domain.intake.hooks.safety.log",
    ) as mock_log:
        await hook.run(_session(), _ref(), collected)

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert args[0] == "d1"
    assert "【危险信号】" in args[1]
    assert "剧烈头痛" in args[1]
    assert "王五" in args[1]
    assert "99" in args[1]

    # Log line fires when hits exist; includes field name.
    assert mock_log.called
    log_msg = mock_log.call_args_list[0].args[0]
    assert "chief_complaint" in log_msg
    assert "剧烈头痛" in log_msg


@pytest.mark.asyncio
async def test_keyword_in_neuro_exam_triggers_notification():
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "查体异常",
        "neuro_exam": "查体发现颈项强直",
        "_patient_name": "张三",
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        await hook.run(_session(), _ref(), collected)

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert "颈项强直" in args[1]


@pytest.mark.asyncio
async def test_multiple_keywords_across_fields_single_notification():
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "突发剧烈头痛",
        "present_illness": "伴随喷射性呕吐",
        "neuro_exam": "检查时出现抽搐",
        "_patient_name": "李四",
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_notify, patch(
        "domain.intake.hooks.safety.log",
    ) as mock_log:
        await hook.run(_session(), _ref(), collected)

    # Single dedup'd notification covering every distinct keyword.
    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    body = args[1]
    # Keywords joined by "、"
    assert "、" in body
    # "突发剧烈头痛" contains "剧烈头痛" so both match chief_complaint.
    for kw in ("突发剧烈头痛", "剧烈头痛", "喷射性呕吐", "抽搐"):
        assert kw in body

    # Log line includes all raw hits (field+keyword tuples).
    assert mock_log.called
    log_msg = mock_log.call_args_list[0].args[0]
    assert "chief_complaint" in log_msg
    assert "present_illness" in log_msg
    assert "neuro_exam" in log_msg


@pytest.mark.asyncio
async def test_negation_currently_false_positives_documented_limitation():
    """v1 keyword matcher does NOT understand negation.

    "无剧烈头痛" still contains the substring "剧烈头痛". Documented as a
    known limitation in the plan's risk notes (mitigation: monitor FP
    rate over first 2 weeks; add negation check or LLM classifier later
    if noise is unacceptable). This test pins current behavior so the
    day we add negation handling, we break this test intentionally.
    """
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "患者自述无剧烈头痛，无意识障碍",
        "_patient_name": "王五",
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        await hook.run(_session(), _ref(), collected)

    # Current v1 behavior: negation NOT detected → false positive fires.
    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert "剧烈头痛" in args[1]
    assert "意识障碍" in args[1]


@pytest.mark.asyncio
async def test_notification_backend_failure_is_swallowed():
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "剧烈头痛",
        "_patient_name": "王五",
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ), patch(
        "domain.intake.hooks.safety.log",
    ) as mock_log:
        # Must NOT raise.
        await hook.run(_session(), _ref(), collected)

    # First log = danger-signal detection; last log = warning for failure.
    assert mock_log.call_count >= 2
    warning_calls = [
        c for c in mock_log.call_args_list
        if c.kwargs.get("level") == "warning"
    ]
    assert len(warning_calls) == 1
    warning_msg = warning_calls[0].args[0]
    assert "notification failed" in warning_msg
    assert "boom" in warning_msg


@pytest.mark.asyncio
async def test_missing_patient_name_uses_fallback():
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "剧烈头痛",
        # _patient_name intentionally omitted
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        await hook.run(_session(), _ref(), collected)

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert "【患者】" in args[1]


@pytest.mark.asyncio
async def test_doctor_mode_same_behavior_as_patient_mode():
    """Hook is mode-agnostic — runs identically regardless of session.mode."""
    hook = SafetyScreenHook()
    collected = {
        "chief_complaint": "剧烈头痛",
        "_patient_name": "王五",
    }
    with patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        await hook.run(_session(mode="doctor"), _ref(), collected)

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert args[0] == "d1"
    assert "【危险信号】" in args[1]
    assert "剧烈头痛" in args[1]
    assert "王五" in args[1]
