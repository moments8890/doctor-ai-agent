"""Neuro sim — danger-signal triggered.

Patient volunteers a neuro signal-flag phrase ("突发剧烈头痛") as the chief
complaint. On confirm the ``SafetyScreenHook`` must fire a doctor
notification prefixed with ``【危险信号】`` and listing the matched
keyword.

This is a sim scenario, not an HTTP integration test — it drives the
real ``IntakeEngine`` with a mocked ``structured_call`` and a mocked
writer / batch extractor so the scenario is deterministic. The real
``SafetyScreenHook`` runs; only its downstream
``send_doctor_notification`` is stubbed to capture the alert.

Covers plan §Task 9 / §Step 3 scenario ``neuro_danger_signal_triggered``.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from domain.intake.engine import IntakeEngine
from domain.intake.protocols import PersistRef
from domain.patients.intake_session import create_session, load_session


async def _seed_neuro_session(mode: str = "patient"):
    doc_id = f"doc_neuro_dng_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()
    return await create_session(
        doctor_id=doc_id,
        patient_id=None,
        mode=mode,
        template_id="medical_neuro_v1",
        initial_fields={"_patient_name": "模拟母亲"},
    )


def _mock_llm_response(reply: str, extracted: dict | None = None):
    fake = MagicMock()
    fake.reply = reply
    inner = MagicMock()
    inner.model_dump = MagicMock(return_value=extracted or {})
    fake.extracted = inner
    fake.suggestions = []
    return fake


@pytest.mark.asyncio
async def test_safety_screen_fires_on_danger_signal_in_chief_complaint():
    """Red-flag phrase in chief_complaint → SafetyScreenHook sends a
    【危险信号】 doctor notification on confirm."""

    session = await _seed_neuro_session(mode="patient")

    # Single turn: patient describes a thunderclap headache. The mocked
    # extractor fills every required patient-mode neuro field in one go
    # so ``can_complete`` flips True and the session moves to reviewing.
    one_shot_extracted = {
        "chief_complaint": "突发剧烈头痛2小时",
        "present_illness": "今天下午剧烈头痛发作，伴恶心",
        "past_history": "无",
        "allergy_history": "无",
        "family_history": "无",
        "personal_history": "无",
        "onset_time": "今日14:00，约2小时前",
    }

    engine = IntakeEngine()
    with patch(
        "domain.intake.engine.structured_call",
        new=AsyncMock(
            return_value=_mock_llm_response(
                "明白了，请稍等，我已记录主要信息。",
                one_shot_extracted,
            ),
        ),
    ):
        await engine.next_turn(session.id, "我妈妈今天突然剧烈头痛，感觉要裂开")

    loaded = await load_session(session.id)
    # Sanity — the signal-flag phrase landed in chief_complaint.
    assert "剧烈头痛" in loaded.collected.get("chief_complaint", "")
    # can_complete flipped; status is reviewing (patient-mode auto-transition).
    assert loaded.status == "reviewing"

    fake_ref = PersistRef(kind="medical_record", id=7777)

    with patch(
        "domain.intake.templates.medical_general.MedicalRecordWriter.persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.intake.templates.medical_general.MedicalBatchExtractor.extract",
        new=AsyncMock(return_value=dict(loaded.collected)),
    ), patch(
        "domain.intake.hooks.medical.TriggerDiagnosisPipelineHook.run",
        new_callable=AsyncMock,
    ), patch(
        "domain.intake.hooks.medical.NotifyDoctorHook.run",
        new_callable=AsyncMock,
    ), patch(
        "domain.intake.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_safety_notify:
        await engine.confirm(session_id=session.id)

    # Safety hook fired exactly one doctor notification.
    mock_safety_notify.assert_awaited_once()
    (doctor_id, body), _ = mock_safety_notify.call_args

    assert doctor_id == session.doctor_id
    assert "【危险信号】" in body
    # The matched keyword(s) surface in the alert body. "突发剧烈头痛"
    # is a literal keyword in the hook's _DANGER_KEYWORDS tuple; so is
    # the substring "剧烈头痛". Both must appear because the hook joins
    # the distinct hit set with "、".
    assert "突发剧烈头痛" in body
    assert "剧烈头痛" in body
    # Patient name shown for triage context.
    assert "模拟母亲" in body
    # Record id echoed so the doctor can jump straight to the record.
    assert str(fake_ref.id) in body
