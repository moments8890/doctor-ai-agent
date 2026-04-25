"""InterviewEngine.next_turn — Phase 2.5: inlined turn loop, no legacy forwarder."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uuid

from db.engine import AsyncSessionLocal
from db.models.doctor import Doctor
from domain.interview.engine import InterviewEngine
from domain.interview.protocols import CompletenessState, TurnResult
from domain.patients.interview_session import create_session, load_session


@pytest.fixture
def engine():
    return InterviewEngine()


async def _seed_session(mode="patient", template_id="medical_general_v1"):
    """Helper: creates doctor + session, returns session."""
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(Doctor(doctor_id=doc_id))
        await db.commit()

    session = await create_session(
        doctor_id=doc_id,
        patient_id=None,
        mode=mode,
        template_id=template_id,
    )
    return session


def _mock_llm_response(reply="你好", extracted_fields=None, suggestions=None):
    """Build a fake structured_call return value shaped like TurnLLMResponse."""
    fake = MagicMock()
    fake.reply = reply

    inner = MagicMock()
    extracted_fields = extracted_fields or {}
    inner.model_dump = MagicMock(return_value=extracted_fields)
    fake.extracted = inner

    fake.suggestions = suggestions or []
    return fake


@pytest.mark.asyncio
async def test_next_turn_returns_turnresult(engine):
    """Smoke test — engine.next_turn orchestrates and returns a TurnResult."""
    session = await _seed_session(mode="patient")

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            reply="了解，还有其他症状吗？",
            extracted_fields={"chief_complaint": "头痛"},
            suggestions=["是", "没有"],
        )),
    ):
        result = await engine.next_turn(session.id, "我头痛")

    assert isinstance(result, TurnResult)
    assert result.reply == "了解，还有其他症状吗？"
    assert "是" in result.suggestions
    assert isinstance(result.state, CompletenessState)


@pytest.mark.asyncio
async def test_next_turn_appends_user_and_assistant_messages(engine):
    session = await _seed_session(mode="patient")

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            reply="收到",
            extracted_fields={},
        )),
    ):
        await engine.next_turn(session.id, "我头痛")

    loaded = await load_session(session.id)
    roles = [t.get("role") for t in loaded.conversation]
    assert "user" in roles
    assert "assistant" in roles
    # User message should carry the input text
    user_msg = next(t for t in loaded.conversation if t["role"] == "user")
    assert user_msg["content"] == "我头痛"


@pytest.mark.asyncio
async def test_next_turn_persists_extracted_fields_via_merge(engine):
    session = await _seed_session(mode="patient")

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            extracted_fields={"chief_complaint": "头痛", "present_illness": "三天"},
        )),
    ):
        await engine.next_turn(session.id, "我头痛三天")

    loaded = await load_session(session.id)
    assert loaded.collected.get("chief_complaint") == "头痛"
    assert "三天" in loaded.collected.get("present_illness", "")


@pytest.mark.asyncio
async def test_next_turn_persists_patient_metadata_underscore_prefixed(engine):
    session = await _seed_session(mode="patient")

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            extracted_fields={
                "patient_name": "张三",
                "patient_gender": "男",
                "patient_age": "45",
                "chief_complaint": "头痛",
            },
        )),
    ):
        await engine.next_turn(session.id, "我叫张三")

    loaded = await load_session(session.id)
    assert loaded.collected.get("_patient_name") == "张三"
    assert loaded.collected.get("_patient_gender") == "男"
    assert loaded.collected.get("_patient_age") == "45"
    # patient_* should NOT appear as clinical fields (they're metadata)
    assert "patient_name" not in loaded.collected


@pytest.mark.asyncio
async def test_next_turn_increments_turn_count(engine):
    session = await _seed_session(mode="patient")

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response()),
    ):
        await engine.next_turn(session.id, "第一轮")

    loaded = await load_session(session.id)
    assert loaded.turn_count >= 1


@pytest.mark.asyncio
async def test_next_turn_safety_cap_transitions_to_reviewing(engine):
    session = await _seed_session(mode="patient")

    # Pump turn_count close to MAX_TURNS using the save_session CRUD
    from domain.patients.interview_session import save_session
    session.turn_count = 29  # one below the 30-turn cap
    await save_session(session)

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response()),
    ):
        # The 30th turn should trigger the cap (turn_count becomes 30)
        result = await engine.next_turn(session.id, "last turn")

    loaded = await load_session(session.id)
    assert loaded.status == "reviewing"


@pytest.mark.asyncio
async def test_next_turn_retries_on_infra_error(engine):
    session = await _seed_session(mode="patient")

    call_count = {"n": 0}

    async def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ConnectionError("simulated infra error")
        return _mock_llm_response(reply="recovered", extracted_fields={})

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(side_effect=flaky),
    ), patch(
        "domain.interview.engine.asyncio.sleep",
        new=AsyncMock(),  # skip real sleep
    ):
        result = await engine.next_turn(session.id, "hi")

    assert call_count["n"] == 2  # retried once, succeeded
    assert result.reply == "recovered"


@pytest.mark.asyncio
async def test_next_turn_parse_error_returns_canned_reply(engine):
    session = await _seed_session(mode="patient")

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(side_effect=ValueError("bad JSON")),
    ):
        result = await engine.next_turn(session.id, "hi")

    # Parse errors get a non-retryable fallback reply
    assert "没有理解" in result.reply or "请再说" in result.reply


@pytest.mark.asyncio
async def test_next_turn_applies_post_process_softening(engine):
    """When can_complete=True (patient mode), the engine applies the
    extractor's post_process_reply which softens blocking language."""
    session = await _seed_session(mode="patient")

    # Seed every subjective field so patient-mode can_complete=True after merge.
    from domain.patients.interview_session import save_session
    session.collected = {
        "chief_complaint": "头痛", "present_illness": "三天",
        "past_history": "无", "allergy_history": "无",
        "family_history": "无", "personal_history": "无",
        "marital_reproductive": "无",
    }
    await save_session(session)

    with patch(
        "domain.interview.engine.structured_call",
        new=AsyncMock(return_value=_mock_llm_response(
            reply="还需要补充家族史。",
            extracted_fields={},
        )),
    ):
        result = await engine.next_turn(session.id, "补充")

    assert "还需要" not in result.reply  # softened
