"""Post-confirm hooks — all three are thin forwards to existing codepaths.

Each must swallow exceptions and log (engine expects best-effort semantics).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)
from domain.intake.protocols import PersistRef, SessionState


def _session() -> SessionState:
    return SessionState(
        id="s1", doctor_id="d1", patient_id=42, mode="patient",
        status="confirmed", template_id="medical_general_v1",
        collected={}, conversation=[], turn_count=5,
    )


@pytest.mark.asyncio
async def test_trigger_diagnosis_calls_safe_create_task():
    hook = TriggerDiagnosisPipelineHook()
    with patch(
        "domain.intake.hooks.medical._safe_create_task",
    ) as mock_safe, patch(
        "domain.intake.hooks.medical._run_diagnosis",
    ) as mock_run:
        mock_run.return_value = "coro-sentinel"
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})

    mock_run.assert_called_once_with(doctor_id="d1", record_id=99)
    mock_safe.assert_called_once()
    # safe_create_task wraps the coroutine with a name
    _, kwargs = mock_safe.call_args
    assert kwargs.get("name") == "diagnosis-99"


@pytest.mark.asyncio
async def test_trigger_diagnosis_swallows_exceptions():
    hook = TriggerDiagnosisPipelineHook()
    with patch(
        "domain.intake.hooks.medical._safe_create_task",
        side_effect=RuntimeError("boom"),
    ):
        # Must NOT raise
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})


@pytest.mark.asyncio
async def test_notify_doctor_sends_notification():
    hook = NotifyDoctorHook()
    with patch(
        "domain.intake.hooks.medical._send_doctor_notification",
        new=AsyncMock(),
    ) as mock_notify:
        collected = {"_patient_name": "王五"}
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), collected)

    mock_notify.assert_called_once()
    args, _ = mock_notify.call_args
    assert args[0] == "d1"
    assert "王五" in args[1]


@pytest.mark.asyncio
async def test_notify_doctor_swallows_exceptions():
    hook = NotifyDoctorHook()
    with patch(
        "domain.intake.hooks.medical._send_doctor_notification",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})


@pytest.mark.asyncio
async def test_generate_followup_tasks_calls_generator():
    hook = GenerateFollowupTasksHook()
    with patch(
        "domain.intake.hooks.medical._get_patient_for_doctor",
        new=AsyncMock(return_value=type("P", (), {"name": "赵六"})()),
    ), patch(
        "domain.intake.hooks.medical._generate_tasks_from_record",
        new=AsyncMock(return_value=[1, 2, 3]),
    ) as mock_gen:
        collected = {
            "orders_followup": "1周复诊",
            "treatment_plan": "布洛芬",
        }
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), collected)

    mock_gen.assert_called_once()
    _, kwargs = mock_gen.call_args
    assert kwargs["doctor_id"] == "d1"
    assert kwargs["record_id"] == 99
    assert kwargs["orders_followup"] == "1周复诊"
    assert kwargs["treatment_plan"] == "布洛芬"


@pytest.mark.asyncio
async def test_generate_followup_tasks_swallows_exceptions():
    hook = GenerateFollowupTasksHook()
    with patch(
        "domain.intake.hooks.medical._get_patient_for_doctor",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await hook.run(_session(), PersistRef(kind="medical_record", id=99), {})
