"""Neuro sim — patient can't recall onset time.

Edge case: the patient answers "不清楚" / "记不清" when asked about
``onset_time``. The extractor must accept that value as a non-empty
string and the required-tier completeness check must be satisfied so
the session can reach ``reviewing``. Otherwise the patient would be
stuck — their best-effort answer can't be forced into a precise
thrombolysis-window timestamp.

This is a sim scenario, not an HTTP integration test. The real
``IntakeEngine`` + ``GeneralNeuroExtractor.completeness`` run;
``structured_call`` is mocked to deliver canned extractions.

Covers plan §Task 9 / §Step 3 scenario ``neuro_no_onset_time_recall``.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from domain.intake.engine import IntakeEngine
from domain.intake.protocols import CompletenessState
from domain.intake.templates.medical_neuro import GeneralNeuroExtractor
from domain.patients.intake_session import create_session, load_session


async def _seed_neuro_session(mode: str = "patient"):
    doc_id = f"doc_neuro_nor_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()
    return await create_session(
        doctor_id=doc_id,
        patient_id=None,
        mode=mode,
        template_id="medical_neuro_v1",
        initial_fields={"_patient_name": "模拟老伴"},
    )


def _mock_llm_response(reply: str, extracted: dict | None = None):
    fake = MagicMock()
    fake.reply = reply
    inner = MagicMock()
    inner.model_dump = MagicMock(return_value=extracted or {})
    fake.extracted = inner
    fake.suggestions = []
    return fake


# ── unit-level assertion on the extractor contract ────────────────────


def test_neuro_completeness_accepts_unclear_onset_time_as_satisfied():
    """GeneralNeuroExtractor.completeness(patient mode) must treat a
    non-empty ``onset_time`` — even "不清楚" — as satisfying the
    required tier. Empty/None must still fail it."""
    extractor = GeneralNeuroExtractor()

    # Common "not sure" phrases a patient/family member would use.
    for unclear in ("不清楚", "记不清", "不知道具体时间", "大概早上吧"):
        collected = {
            "chief_complaint": "左侧无力",
            "present_illness": "早上起床发现左侧无力",
            "past_history": "无",
            "allergy_history": "无",
            "family_history": "无",
            "personal_history": "无",
            "onset_time": unclear,
        }
        state: CompletenessState = extractor.completeness(
            collected, mode="patient",
        )
        assert state.can_complete is True, (
            f"extractor must accept unclear onset_time '{unclear}' "
            f"as satisfying required tier; got {state!r}"
        )
        assert "onset_time" not in state.required_missing

    # Empty / missing onset_time still fails the required check —
    # pins the inverse behavior so we don't silently accept nothing.
    collected["onset_time"] = ""
    state = extractor.completeness(collected, mode="patient")
    assert state.can_complete is False
    assert "onset_time" in state.required_missing


# ── end-to-end engine flow ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_neuro_session_reaches_reviewing_when_patient_cannot_recall_onset():
    session = await _seed_neuro_session(mode="patient")

    # Two turns: first the patient describes the symptom, then answers
    # the onset-time question with "不清楚". The extractor records the
    # literal answer.
    turns: list[tuple[str, str, dict]] = [
        (
            "我老伴早上起来左侧手脚不太好使",
            "方便告诉我他大概是什么时候开始这样的吗？",
            {
                "chief_complaint": "左侧肢体活动不利",
                "present_illness": "晨起发现左侧肢体活动不灵便",
            },
        ),
        (
            "不清楚，他醒来就这样了",
            "我已经整理好主要信息。请确认后提交给医生；"
            "如果还有补充，也可以继续补充。",
            {
                "onset_time": "不清楚",
                "past_history": "无",
                "allergy_history": "无",
                "family_history": "无",
                "personal_history": "无",
            },
        ),
    ]

    engine = IntakeEngine()
    for user_input, reply, extracted in turns:
        with patch(
            "domain.intake.engine.structured_call",
            new=AsyncMock(
                return_value=_mock_llm_response(reply, extracted),
            ),
        ):
            await engine.next_turn(session.id, user_input)

    loaded = await load_session(session.id)

    # The patient's literal "不清楚" survived the merge.
    assert loaded.collected.get("onset_time") == "不清楚"
    # can_complete flipped → engine transitioned status to reviewing.
    assert loaded.status == "reviewing"
