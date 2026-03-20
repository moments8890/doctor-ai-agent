"""P2 Diagnosis Pipeline integration tests — real DB (in-memory SQLite), mocked LLM."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.models import Doctor, MedicalRecordDB
from db.models.diagnosis_result import DiagnosisResult, DiagnosisStatus
from db.crud.diagnosis import (
    get_diagnosis_by_record,
    update_item_decision,
    confirm_diagnosis,
)


# ---------------------------------------------------------------------------
# Fixture LLM response — returned by the mocked _call_with_cloud_fallback
# ---------------------------------------------------------------------------

_FAKE_PROVIDER = {
    "base_url": "http://localhost:11434/v1",
    "api_key_env": "OLLAMA_API_KEY",
    "model": "qwen2.5:7b",
}

_FIXTURE_LLM_JSON = {
    "differentials": [
        {"condition": "脑膜瘤", "confidence": "高", "reasoning": "前额持续胀痛伴高血压"},
        {"condition": "偏头痛", "confidence": "中", "reasoning": "反复发作模式"},
        {"condition": "颅内高压", "confidence": "低", "reasoning": "需排除继发原因"},
    ],
    "workup": [
        {"test": "头颅MRI增强", "rationale": "鉴别占位病变", "urgency": "紧急"},
        {"test": "腰椎穿刺", "rationale": "排除脑脊液异常", "urgency": "常规"},
    ],
    "treatment": [
        {"drug_class": "甘露醇", "intervention": "药物", "description": "降低颅内压"},
    ],
    "red_flags": ["突发剧烈头痛", "视力下降", "意识改变"],
}


def _make_fake_completion(json_data: dict) -> object:
    """Build a minimal ChatCompletion-like object the parser expects."""
    msg = SimpleNamespace(content=json.dumps(json_data, ensure_ascii=False))
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


# ---------------------------------------------------------------------------
# Helpers: embed mock (same _fake_embed pattern as test_case_history.py)
# ---------------------------------------------------------------------------

def _fake_embed(text: str):
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    vec = [float(b) / 255.0 for b in h] * 32  # 32 × 32 = 1024
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec]


# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------

async def _seed_doctor(session, doctor_id: str = "test_doctor") -> str:
    session.add(Doctor(doctor_id=doctor_id, name="Dr. Test", specialty="神经外科"))
    await session.flush()
    return doctor_id


async def _seed_record(
    session,
    doctor_id: str,
    structured: dict | None = None,
) -> int:
    if structured is None:
        structured = {
            "chief_complaint": "头痛2周伴恶心呕吐",
            "present_illness": "患者2周前无明显诱因出现前额持续性胀痛",
            "past_history": "高血压病史5年",
        }
    rec = MedicalRecordDB(
        doctor_id=doctor_id,
        record_type="interview_summary",
        content="头痛2周",
        structured=json.dumps(structured, ensure_ascii=False),
    )
    session.add(rec)
    await session.flush()
    return rec.id


# ---------------------------------------------------------------------------
# Session patcher factory
#
# run_diagnosis() calls `async with AsyncSessionLocal() as session:` internally.
# We redirect that to the test session_factory so all DB writes go to the
# same in-memory SQLite used by the test assertions.
# ---------------------------------------------------------------------------

def _make_session_patch(session_factory):
    """Return a mock for domain.diagnosis.AsyncSessionLocal bound to test DB."""

    @asynccontextmanager
    async def _test_session():
        async with session_factory() as session:
            yield session

    mock_asl = MagicMock()
    mock_asl.return_value = _test_session()
    # Make mock_asl() return a fresh context manager each time it is called.
    mock_asl.side_effect = lambda: _test_session()
    return mock_asl


# ---------------------------------------------------------------------------
# Fake matched cases (returned by mocked match_cases)
# ---------------------------------------------------------------------------

_FAKE_MATCHED_CASES = [
    {
        "id": 1,
        "chief_complaint": "头痛伴恶心呕吐",
        "final_diagnosis": "脑膜瘤",
        "treatment": "手术切除",
        "outcome": "好转",
        "similarity": 0.92,
        "is_seed": False,
    }
]


# ---------------------------------------------------------------------------
# Test 1: run_diagnosis with a DB record → row saved as completed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_diagnosis_with_record(session_factory):
    """Seed record → run_diagnosis(record_id=N) → diagnosis_results row status=completed."""
    # Seed doctor + record in test DB
    async with session_factory() as session:
        did = await _seed_doctor(session)
        rid = await _seed_record(session, did)
        await session.commit()

    session_patch = _make_session_patch(session_factory)

    fake_completion = _make_fake_completion(_FIXTURE_LLM_JSON)

    with (
        patch("domain.diagnosis.AsyncSessionLocal", session_patch),
        patch("domain.diagnosis._resolve_provider", return_value=_FAKE_PROVIDER),
        patch("domain.diagnosis._call_with_cloud_fallback", new=AsyncMock(return_value=fake_completion)),
        patch("domain.diagnosis.match_cases", new=AsyncMock(return_value=_FAKE_MATCHED_CASES)),
        patch("domain.diagnosis.load_knowledge_context_for_prompt", new=AsyncMock(return_value="")),
        patch("domain.diagnosis.get_diagnosis_skill", return_value=""),
        patch("db.crud.case_history.embed", side_effect=_fake_embed),
        patch("db.crud.case_history.get_model_name", return_value="test-model"),
    ):
        from domain.diagnosis import run_diagnosis
        result = await run_diagnosis(doctor_id=did, record_id=rid)

    # Pipeline must report success
    assert result.get("status") == "completed", f"Unexpected status: {result}"
    assert "differentials" in result
    assert len(result["differentials"]) == 3
    assert result["differentials"][0]["condition"] == "脑膜瘤"

    # Verify the diagnosis_results row was persisted
    async with session_factory() as session:
        row = await get_diagnosis_by_record(session, rid, did)

    assert row is not None, "diagnosis_results row should exist after run_diagnosis"
    assert row.status == DiagnosisStatus.completed
    assert row.ai_output is not None

    ai = json.loads(row.ai_output)
    assert len(ai["differentials"]) == 3
    assert ai["differentials"][0]["condition"] == "脑膜瘤"
    assert len(ai["workup"]) == 2
    assert len(ai["treatment"]) == 1


# ---------------------------------------------------------------------------
# Test 2: run_diagnosis with clinical_text — returns results, no DB row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_diagnosis_with_clinical_text(session_factory):
    """clinical_text path → returns result dict without saving to DB."""
    async with session_factory() as session:
        did = await _seed_doctor(session)
        await session.commit()

    session_patch = _make_session_patch(session_factory)

    fake_completion = _make_fake_completion(_FIXTURE_LLM_JSON)

    # structure_medical_record must return an object with a .structured dict
    structured_result = SimpleNamespace(
        structured={
            "chief_complaint": "头痛2周伴恶心呕吐",
            "present_illness": "前额持续性胀痛",
        }
    )

    with (
        patch("domain.diagnosis.AsyncSessionLocal", session_patch),
        patch("domain.diagnosis._resolve_provider", return_value=_FAKE_PROVIDER),
        patch("domain.diagnosis._call_with_cloud_fallback", new=AsyncMock(return_value=fake_completion)),
        patch("domain.diagnosis.match_cases", new=AsyncMock(return_value=[])),
        patch("domain.diagnosis.load_knowledge_context_for_prompt", new=AsyncMock(return_value="")),
        patch("domain.diagnosis.get_diagnosis_skill", return_value=""),
        # The structuring import is done lazily inside _load_clinical_context_from_text
        patch(
            "domain.records.structuring.structure_medical_record",
            new=AsyncMock(return_value=structured_result),
        ),
        patch("db.crud.case_history.embed", side_effect=_fake_embed),
        patch("db.crud.case_history.get_model_name", return_value="test-model"),
    ):
        from domain.diagnosis import run_diagnosis
        result = await run_diagnosis(
            doctor_id=did,
            clinical_text="头痛2周伴恶心呕吐",
        )

    # Must return a result dict with the expected structure
    assert result.get("status") == "completed", f"Unexpected status: {result}"
    assert "differentials" in result
    assert len(result["differentials"]) > 0

    # Must NOT have saved anything to DB (no record_id was given)
    async with session_factory() as session:
        from sqlalchemy import select
        rows = (await session.execute(select(DiagnosisResult))).scalars().all()
    assert len(rows) == 0, "clinical_text path must not persist diagnosis_results"


# ---------------------------------------------------------------------------
# Test 3: confirm_diagnosis computes agreement_score correctly
#
# Scenario: 3 differentials + 2 workup + 1 treatment = 6 total items
# Doctor rejects 1 item (differentials[1]) → agreement_score = 5/6 ≈ 0.833
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_with_agreement_score(session_factory):
    """Manual rejection of one item → agreement_score = 5/6 after confirm."""
    async with session_factory() as session:
        did = await _seed_doctor(session)
        rid = await _seed_record(session, did)
        await session.commit()

    session_patch = _make_session_patch(session_factory)

    fake_completion = _make_fake_completion(_FIXTURE_LLM_JSON)

    with (
        patch("domain.diagnosis.AsyncSessionLocal", session_patch),
        patch("domain.diagnosis._resolve_provider", return_value=_FAKE_PROVIDER),
        patch("domain.diagnosis._call_with_cloud_fallback", new=AsyncMock(return_value=fake_completion)),
        patch("domain.diagnosis.match_cases", new=AsyncMock(return_value=[])),
        patch("domain.diagnosis.load_knowledge_context_for_prompt", new=AsyncMock(return_value="")),
        patch("domain.diagnosis.get_diagnosis_skill", return_value=""),
        patch("db.crud.case_history.embed", side_effect=_fake_embed),
        patch("db.crud.case_history.get_model_name", return_value="test-model"),
    ):
        from domain.diagnosis import run_diagnosis
        await run_diagnosis(doctor_id=did, record_id=rid)

    # Get the saved diagnosis row
    async with session_factory() as session:
        row = await get_diagnosis_by_record(session, rid, did)
        assert row is not None
        diagnosis_id = row.id

    # Reject differentials[1]
    async with session_factory() as session:
        updated = await update_item_decision(
            session, diagnosis_id, did, "differentials", 1, "rejected"
        )
        assert updated is not None
        await session.commit()

    # Confirm diagnosis
    async with session_factory() as session:
        confirmed = await confirm_diagnosis(session, diagnosis_id, did)
        assert confirmed is not None
        await session.commit()

    # Verify status + agreement_score
    async with session_factory() as session:
        row = await get_diagnosis_by_record(session, rid, did)

    assert row.status == DiagnosisStatus.confirmed
    assert row.agreement_score is not None
    # 5 accepted out of 6 total = 5/6
    expected = 5 / 6
    assert abs(row.agreement_score - expected) < 1e-6, (
        f"Expected agreement_score ≈ {expected:.4f}, got {row.agreement_score:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 4: graceful failure — LLM raises timeout → status=failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graceful_failure(session_factory):
    """LLM timeout → diagnosis_results row saved with status=failed."""
    import asyncio

    async with session_factory() as session:
        did = await _seed_doctor(session)
        rid = await _seed_record(session, did)
        await session.commit()

    session_patch = _make_session_patch(session_factory)

    with (
        patch("domain.diagnosis.AsyncSessionLocal", session_patch),
        patch("domain.diagnosis._resolve_provider", return_value=_FAKE_PROVIDER),
        patch(
            "domain.diagnosis._call_with_cloud_fallback",
            new=AsyncMock(side_effect=asyncio.TimeoutError("LLM request timed out")),
        ),
        patch("domain.diagnosis.match_cases", new=AsyncMock(return_value=[])),
        patch("domain.diagnosis.load_knowledge_context_for_prompt", new=AsyncMock(return_value="")),
        patch("domain.diagnosis.get_diagnosis_skill", return_value=""),
        patch("db.crud.case_history.embed", side_effect=_fake_embed),
        patch("db.crud.case_history.get_model_name", return_value="test-model"),
    ):
        from domain.diagnosis import run_diagnosis
        result = await run_diagnosis(doctor_id=did, record_id=rid)

    # Pipeline should return a failure dict (not raise)
    assert result.get("status") == "failed", f"Expected status=failed, got: {result}"
    assert "error" in result

    # Verify the DB row was persisted with status=failed
    async with session_factory() as session:
        row = await get_diagnosis_by_record(session, rid, did)

    assert row is not None, "diagnosis_results row must be saved even on failure"
    assert row.status == DiagnosisStatus.failed
    assert row.error_message is not None
    assert len(row.error_message) > 0
