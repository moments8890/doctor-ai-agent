"""InterviewEngine.confirm — mode-aware orchestration.

Spec §5d. Patient mode fires diagnosis + notify; doctor mode fires only
follow-up tasks (asymmetric — see §8 open question).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.interview.engine import InterviewEngine
from domain.interview.protocols import PersistRef, SessionState


def _session(mode="doctor", patient_id=42):
    return SessionState(
        id="s1", doctor_id="d1", patient_id=patient_id, mode=mode,
        status="interviewing", template_id="medical_general_v1",
        collected={"_patient_name": "张三", "chief_complaint": "头痛"},
        conversation=[{"role": "user", "content": "头痛"}],
        turn_count=3,
    )


@pytest.fixture
def engine():
    return InterviewEngine()


@pytest.mark.asyncio
async def test_confirm_runs_batch_extract_when_template_has_one(engine):
    sess = _session()
    fake_ref = PersistRef(kind="medical_record", id=99)

    with patch(
        "domain.interview.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.interview.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.interview.engine._release_session_lock",
    ), patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value={"chief_complaint": "头痛 (batch)"}),
    ) as mock_batch, patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ) as mock_persist, patch(
        "domain.interview.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ) as mock_hook:
        ref = await engine.confirm(session_id="s1")

    assert ref == fake_ref
    mock_batch.assert_awaited_once()
    mock_persist.assert_awaited_once()
    # Doctor-mode hooks: only the follow-up tasks hook
    mock_hook.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_patient_mode_fires_diagnosis_and_notify(engine):
    sess = _session(mode="patient")
    fake_ref = PersistRef(kind="medical_record", id=100)

    with patch(
        "domain.interview.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.interview.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.interview.engine._release_session_lock",
    ), patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value=None),
    ), patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.interview.hooks.medical.TriggerDiagnosisPipelineHook.run",
        new=AsyncMock(),
    ) as mock_diag, patch(
        "domain.interview.hooks.medical.NotifyDoctorHook.run",
        new=AsyncMock(),
    ) as mock_notify, patch(
        "domain.interview.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ) as mock_followup:
        await engine.confirm("s1")

    mock_diag.assert_awaited_once()
    mock_notify.assert_awaited_once()
    mock_followup.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_preserves_underscore_metadata_across_batch_extract(engine):
    """Per confirm.py:64-67 — underscore-prefixed metadata fields must
    survive the re-extraction."""
    sess = _session()
    sess.collected["_patient_gender"] = "男"
    sess.collected["_patient_age"] = "45岁"

    fake_ref = PersistRef(kind="medical_record", id=77)
    persist_called_with: dict = {}

    async def _capture_persist(self, session, collected):
        persist_called_with["collected"] = dict(collected)
        return fake_ref

    with patch(
        "domain.interview.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.interview.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.interview.engine._release_session_lock",
    ), patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value={"chief_complaint": "NEW"}),
    ), patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        _capture_persist,
    ), patch(
        "domain.interview.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ):
        await engine.confirm("s1")

    assert persist_called_with["collected"]["_patient_name"] == "张三"
    assert persist_called_with["collected"]["_patient_gender"] == "男"
    assert persist_called_with["collected"]["_patient_age"] == "45岁"
    assert persist_called_with["collected"]["chief_complaint"] == "NEW"


@pytest.mark.asyncio
async def test_confirm_hook_failure_does_not_unwind_persist(engine):
    """Per spec §5d: post-confirm hooks are best-effort. A failing hook
    logs a warning and the confirm still returns the PersistRef."""
    sess = _session()
    fake_ref = PersistRef(kind="medical_record", id=88)

    with patch(
        "domain.interview.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.interview.engine._save_session_state",
        new=AsyncMock(),
    ), patch(
        "domain.interview.engine._release_session_lock",
    ), patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value=None),
    ), patch.object(
        __import__("domain.interview.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.interview.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        # Must NOT raise
        ref = await engine.confirm("s1")

    assert ref == fake_ref
