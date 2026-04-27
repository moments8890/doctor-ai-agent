"""Clinical signals channel — buffered on intake session, materialized on confirm.

Why this exists: the patient-intake LLM was leaking persona-driven clinical
thoughts ("做完检查发给我", "建议做B超") into the patient-facing reply,
ending intake early. We can't disable persona — the clinical instinct is
valuable signal, just routed wrong. These tests cover the routing fix:
clinical_signals[] field on the LLM response, session-level buffer with
dedup + truncation, reply gate replacing leaked clinical text with a
defer-and-continue line, and inline materialization to ai_suggestions on
confirm (with re-raise on failure so retries are safe).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from domain.intake.engine import IntakeEngine
from domain.intake.protocols import PersistRef, SessionState
from domain.patients.intake_session import create_session, load_session


@pytest.fixture
def engine():
    return IntakeEngine()


async def _seed_session(mode="patient", template_id="medical_general_v1"):
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()
    session = await create_session(
        doctor_id=doc_id, patient_id=None, mode=mode, template_id=template_id,
    )
    return session


def _mock_llm_response(
    reply="收到",
    extracted_fields=None,
    suggestions=None,
    clinical_signals=None,
):
    fake = MagicMock()
    fake.reply = reply

    inner = MagicMock()
    inner.model_dump = MagicMock(return_value=extracted_fields or {})
    fake.extracted = inner

    fake.suggestions = suggestions or []

    # clinical_signals is a list of pydantic-like objects with attribute access
    sigs = []
    for s in (clinical_signals or []):
        sig = MagicMock()
        sig.section = s["section"]
        sig.content = s["content"]
        sig.detail = s.get("detail")
        sig.urgency = s.get("urgency")
        sig.evidence = s.get("evidence", [])
        sig.risk_signals = s.get("risk_signals", [])
        sigs.append(sig)
    fake.clinical_signals = sigs
    return fake


# ── Buffer / dedup / truncation ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clinical_signals_buffered_on_session(engine):
    session = await _seed_session(mode="patient")

    with patch(
        "domain.intake.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            reply="好的，记录了。",
            clinical_signals=[{
                "section": "workup", "content": "腹部B超",
                "detail": "rule out appendicitis", "urgency": "high",
                "evidence": ["右下腹阵发性疼痛"],
                "risk_signals": ["acute_abdomen_pattern"],
            }],
        )),
    ):
        await engine.next_turn(session.id, "右下腹疼痛")

    loaded = await load_session(session.id)
    pending = loaded.collected.get("_pending_ai_suggestions", [])
    assert len(pending) == 1
    entry = pending[0]
    assert entry["section"] == "workup"
    assert entry["content"] == "腹部B超"
    assert entry["urgency"] == "high"
    assert entry["evidence"] == ["右下腹阵发性疼痛"]
    assert entry["risk_signals"] == ["acute_abdomen_pattern"]
    assert "turn_index" in entry
    assert "created_at" in entry
    assert "prompt_hash" in entry and len(entry["prompt_hash"]) == 16


@pytest.mark.asyncio
async def test_clinical_signals_dedup(engine):
    session = await _seed_session(mode="patient")

    same_signal = {
        "section": "workup", "content": "腹部B超", "urgency": "high",
    }

    with patch(
        "domain.intake.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            clinical_signals=[same_signal],
        )),
    ):
        await engine.next_turn(session.id, "右下腹疼痛")
        await engine.next_turn(session.id, "还是这里疼")

    loaded = await load_session(session.id)
    pending = loaded.collected.get("_pending_ai_suggestions", [])
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_clinical_signals_truncation(engine):
    session = await _seed_session(mode="patient")

    five_signals = [
        {"section": "workup", "content": f"检查{i}", "urgency": "low"}
        for i in range(5)
    ]

    with patch(
        "domain.intake.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            clinical_signals=five_signals,
        )),
    ):
        await engine.next_turn(session.id, "肚子疼")

    loaded = await load_session(session.id)
    pending = loaded.collected.get("_pending_ai_suggestions", [])
    assert len(pending) == 3


# ── Reply gate ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reply_gate_fires_on_banned_phrase(engine):
    session = await _seed_session(mode="patient")
    # Need at least one required_missing for a phase-2 question
    from domain.patients.intake_session import save_session
    session.collected = {"chief_complaint": "腹痛", "present_illness": "三天"}
    await save_session(session)

    with patch(
        "domain.intake.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            reply="建议去医院做B超看看。",
            clinical_signals=[],
        )),
    ):
        result = await engine.next_turn(session.id, "肚子疼")

    assert "建议去医院" not in result.reply
    assert "已记录您的情况" in result.reply
    # Should append a phase-2 question (one of the field_questions)
    assert any(
        q in result.reply for q in (
            "慢性病", "过敏", "遗传病", "抽烟", "婚姻",
        )
    )


@pytest.mark.asyncio
async def test_reply_gate_does_not_fire_when_only_signals_present(engine):
    """Clinical_signals being non-empty is NOT a leak — the channel exists
    so the LLM has a place to put clinical thoughts WITHOUT polluting reply.
    A clean reply with non-empty signals should pass through unchanged."""
    session = await _seed_session(mode="patient")
    from domain.patients.intake_session import save_session
    session.collected = {"chief_complaint": "腹痛", "present_illness": "三天"}
    await save_session(session)

    clean_reply = "好的，记下来了。多久了？"
    with patch(
        "domain.intake.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            reply=clean_reply,
            clinical_signals=[{
                "section": "workup", "content": "腹部B超", "urgency": "high",
            }],
        )),
    ):
        result = await engine.next_turn(session.id, "右下腹剧痛")

    assert result.reply == clean_reply


# ── Materialize on confirm ──────────────────────────────────────────────────

def _confirm_session_with_buffer(buffer_entries):
    return SessionState(
        id="s1", doctor_id="d1", patient_id=42, mode="patient",
        status="active", template_id="medical_general_v1",
        collected={
            "_patient_name": "张三",
            "chief_complaint": "腹痛",
            "_pending_ai_suggestions": buffer_entries,
        },
        conversation=[{"role": "user", "content": "腹痛"}],
        turn_count=3,
    )


@pytest.mark.asyncio
async def test_confirm_does_not_write_ai_suggestions_and_preserves_buffer(engine):
    # Per current product call (2026-04-26): intake-side clinical_signals are
    # NOT materialized as ai_suggestions rows. Diagnosis pipeline is the sole
    # writer. The buffer stays on the session for potential later use.
    buffer = [
        {
            "section": "workup", "content": "腹部B超",
            "detail": "rule out appendicitis", "urgency": "high",
            "evidence": ["右下腹阵发性疼痛"],
            "risk_signals": ["acute_abdomen_pattern"],
            "turn_index": 1, "created_at": "2026-04-26T00:00:00+00:00",
            "prompt_hash": "abc123def4567890",
        },
        {
            "section": "differential", "content": "急性阑尾炎",
            "detail": None, "urgency": "high",
            "evidence": [], "risk_signals": [],
            "turn_index": 2, "created_at": "2026-04-26T00:01:00+00:00",
            "prompt_hash": "abc123def4567890",
        },
    ]
    sess = _confirm_session_with_buffer(buffer)
    fake_ref = PersistRef(kind="medical_record", id=99)

    create_calls = []

    async def fake_create(session_arg, **kwargs):
        create_calls.append(kwargs)
        return MagicMock(id=len(create_calls))

    save_mock = AsyncMock()

    with patch(
        "domain.intake.engine._load_session_state",
        new=AsyncMock(return_value=sess),
    ), patch(
        "domain.intake.engine._save_session_state",
        new=save_mock,
    ), patch(
        "domain.intake.engine._release_session_lock",
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalBatchExtractor"]).MedicalBatchExtractor,
        "extract",
        new=AsyncMock(return_value=None),
    ), patch.object(
        __import__("domain.intake.templates.medical_general",
                   fromlist=["MedicalRecordWriter"]).MedicalRecordWriter,
        "persist",
        new=AsyncMock(return_value=fake_ref),
    ), patch(
        "db.crud.suggestions.create_suggestion",
        new=fake_create,
    ), patch(
        "domain.intake.engine.AsyncSessionLocal",
    ), patch(
        "domain.intake.hooks.medical.TriggerDiagnosisPipelineHook.run",
        new=AsyncMock(),
    ), patch(
        "domain.intake.hooks.medical.NotifyDoctorHook.run",
        new=AsyncMock(),
    ), patch(
        "domain.intake.hooks.medical.GenerateFollowupTasksHook.run",
        new=AsyncMock(),
    ):
        ref = await engine.confirm("s1")

    assert ref == fake_ref
    assert create_calls == [], (
        "intake confirm() must not write ai_suggestions rows — "
        "diagnosis pipeline is the sole writer"
    )

    # Buffer preserved on the saved session for any future backfill.
    saved_states = [call.args[0] for call in save_mock.await_args_list]
    assert saved_states, "expected _save_session_state to be called"
    assert all(
        s.collected.get("_pending_ai_suggestions") == buffer
        for s in saved_states
    )
