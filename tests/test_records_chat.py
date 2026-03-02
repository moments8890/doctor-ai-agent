"""Unit tests for /api/records/chat fallback logic.

These tests mock LLM routing and structuring, and patch DB session factory to
an in-memory SQLite session so no external I/O is required.
"""
import pytest
from unittest.mock import AsyncMock, patch

from models.medical_record import MedicalRecord
from routers.records import ChatInput, HistoryMessage, chat
from services.intent import Intent, IntentResult


DOCTOR = "unit_doc_records_chat"


def _record() -> MedicalRecord:
    return MedicalRecord(
        chief_complaint="突发胸痛两小时",
        history_of_present_illness="伴大汗",
        diagnosis="急性冠脉综合征待排",
        treatment_plan=None,
    )


@pytest.mark.asyncio
async def test_name_followup_overrides_create_patient_and_saves_record(session_factory):
    history = [
        HistoryMessage(role="user", content="突发胸痛两小时，伴大汗"),
        HistoryMessage(role="assistant", content="请问这位患者叫什么名字？"),
    ]

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch(
             "routers.records.agent_dispatch",
             new=AsyncMock(
                 return_value=IntentResult(
                     intent=Intent.create_patient,
                     patient_name="陈明",
                 )
             ),
         ), \
         patch(
             "routers.records.structure_medical_record",
             new=AsyncMock(return_value=_record()),
         ) as mock_structure:
        response = await chat(ChatInput(text="陈明", history=history, doctor_id=DOCTOR))

    assert response.record is not None
    assert "陈明" in response.reply
    # The follow-up name turn must not be used as clinical content.
    assert mock_structure.await_args.args[0] == "突发胸痛两小时，伴大汗"


@pytest.mark.asyncio
async def test_name_followup_overrides_unknown_and_saves_record(session_factory):
    history = [
        HistoryMessage(role="user", content="突发胸痛两小时，伴大汗"),
        HistoryMessage(role="assistant", content="请问这位患者叫什么名字？"),
    ]

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch(
             "routers.records.agent_dispatch",
             new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply="好的")),
         ), \
         patch(
             "routers.records.structure_medical_record",
             new=AsyncMock(return_value=_record()),
         ):
        response = await chat(ChatInput(text="陈明", history=history, doctor_id=DOCTOR))

    assert response.record is not None
    assert "保存病历" in response.reply


@pytest.mark.asyncio
async def test_name_followup_fills_missing_name_when_intent_is_add_record(session_factory):
    history = [
        HistoryMessage(role="user", content="突发胸痛两小时，伴大汗"),
        HistoryMessage(role="assistant", content="请问这位患者叫什么名字？"),
    ]

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch(
             "routers.records.agent_dispatch",
             new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
         ), \
         patch(
             "routers.records.structure_medical_record",
             new=AsyncMock(return_value=_record()),
         ):
        response = await chat(ChatInput(text="陈明", history=history, doctor_id=DOCTOR))

    assert response.record is not None
    assert "陈明" in response.reply
