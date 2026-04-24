"""Neuro sim — happy path.

5-turn stroke-onset intake on ``medical_neuro_v1``. Patient volunteers
``chief_complaint`` + ``present_illness`` first, the model asks for
onset time, the patient answers, then the model asks for risk factors
and the patient answers. By the fifth turn every neuro-required field
is populated. On confirm the full patient-mode hook list (diagnosis +
doctor notification + safety screen) dispatches.

This is a sim scenario, not an HTTP integration test — it drives the
real ``InterviewEngine`` with a mocked ``structured_call`` so the
scenario is deterministic and fast. The post-confirm writer is mocked
too (we don't need to write a ``medical_records`` row to verify hook
dispatch). The real hooks run, with their side-effectful dependencies
(``send_doctor_notification`` + ``GenerateFollowupTasksHook`` internals +
the diagnosis pipeline trigger) patched one layer in.

Covers plan §Task 9 / §Step 3 scenario ``neuro_happy_path``.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from domain.interview.engine import InterviewEngine
from domain.interview.protocols import PersistRef
from domain.patients.interview_session import create_session, load_session


# ── helpers ──────────────────────────────────────────────────────────────


async def _seed_neuro_session(mode: str = "patient"):
    doc_id = f"doc_neuro_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    return await create_session(
        doctor_id=doc_id,
        patient_id=None,
        mode=mode,
        template_id="medical_neuro_v1",
        initial_fields={"_patient_name": "模拟老父亲"},
    )


def _mock_llm_response(reply: str, extracted: dict | None = None):
    """Build a fake structured_call return value shaped like TurnLLMResponse."""
    fake = MagicMock()
    fake.reply = reply
    inner = MagicMock()
    inner.model_dump = MagicMock(return_value=extracted or {})
    fake.extracted = inner
    fake.suggestions = []
    return fake


# ── scenario ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_neuro_happy_path_full_conversation_and_confirm():
    """End-to-end: 5 patient turns → can_complete=True → confirm fires
    all 3 patient-mode hooks (diagnosis, notify doctor, safety screen)."""

    session = await _seed_neuro_session(mode="patient")

    # Each entry is (user_input, mocked reply text, mocked extracted fields).
    # The patient volunteers cumulative info; the engine merges per-turn.
    turns: list[tuple[str, str, dict]] = [
        (
            "我父亲今天早上突然左边手脚没力气，说话也不清楚",
            "辛苦了，大约是什么时间开始出现的？",
            {
                "chief_complaint": "左侧肢体无力+言语不清",
                "present_illness": "今晨突发左侧肢体无力伴言语不清",
            },
        ),
        (
            "大概今早7点半吧，一开始以为睡醒没劲，后来发现越来越严重",
            "好的。他之前有没有高血压、糖尿病或者房颤这类的病史？",
            {
                "onset_time": "今晨7:30",
            },
        ),
        (
            "他有高血压十几年了，也有房颤",
            "明白了。请问他有没有药物过敏史？",
            {
                "past_history": "高血压>10年；房颤",
                "vascular_risk_factors": "高血压>10年；房颤",
            },
        ),
        (
            "没有药物过敏",
            "家里其他人有类似症状或者中风史吗？",
            {
                "allergy_history": "无",
            },
        ),
        (
            "家里没有类似的",
            "我已经整理好主要信息。请确认后提交给医生；"
            "如果还有补充，也可以继续补充。",
            {
                "family_history": "无",
                "personal_history": "无",
            },
        ),
    ]

    engine = InterviewEngine()
    for user_input, reply, extracted in turns:
        with patch(
            "domain.interview.engine.structured_call",
            new=AsyncMock(
                return_value=_mock_llm_response(reply, extracted),
            ),
        ):
            await engine.next_turn(session.id, user_input)

    loaded = await load_session(session.id)

    # Every required+recommended neuro field populated.
    assert loaded.collected.get("chief_complaint"), loaded.collected
    assert loaded.collected.get("present_illness")
    assert loaded.collected.get("onset_time") == "今晨7:30"
    assert "高血压" in loaded.collected.get("past_history", "")
    assert "高血压" in loaded.collected.get("vascular_risk_factors", "")

    # Patient-mode readiness has flipped — engine writes status=reviewing
    # whenever can_complete becomes True and the template requires review.
    assert loaded.status == "reviewing"

    # ── confirm → all 3 patient-mode hooks dispatch ──────────────────

    fake_ref = PersistRef(kind="medical_record", id=12345)

    with patch(
        "domain.interview.templates.medical_general.MedicalRecordWriter.persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "domain.interview.templates.medical_general.MedicalBatchExtractor.extract",
        # Batch re-extract returns the already-merged collected verbatim so
        # the final state equals what the per-turn extractor produced.
        new=AsyncMock(return_value=dict(loaded.collected)),
    ), patch(
        "domain.interview.hooks.medical.TriggerDiagnosisPipelineHook.run",
        new_callable=AsyncMock,
    ) as mock_dx, patch(
        "domain.interview.hooks.medical.NotifyDoctorHook.run",
        new_callable=AsyncMock,
    ) as mock_notify_hook, patch(
        "domain.interview.hooks.safety._send_doctor_notification",
        new_callable=AsyncMock,
    ) as mock_safety_notify:
        ref = await engine.confirm(session_id=session.id)

    assert ref == fake_ref

    # Diagnosis pipeline fires (patient-mode only for medical templates).
    mock_dx.assert_awaited_once()

    # Doctor-inbox notification hook fires.
    mock_notify_hook.assert_awaited_once()

    # SafetyScreenHook fires too — this "happy path" case clinically
    # presents with stroke-like red flags ("言语不清" is a literal keyword
    # in ``_DANGER_KEYWORDS``). A neuro happy-path E2E therefore SHOULD
    # produce a 【危险信号】 alert; the hook running correctly is part of
    # what "happy" means for medical_neuro_v1. Pins that the alert fires
    # exactly once and carries the right doctor + prefix + matched kw.
    mock_safety_notify.assert_awaited_once()
    (safety_doctor_id, body), _ = mock_safety_notify.call_args
    assert safety_doctor_id == session.doctor_id
    assert "【危险信号】" in body
    assert "言语不清" in body

    reloaded = await load_session(session.id)
    assert reloaded.status == "confirmed"
