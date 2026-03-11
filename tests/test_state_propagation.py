"""State propagation tests: verify that intent handlers pin resolved patients to session.

These tests ensure that after resolving a patient, the handler calls
set_current_patient so follow-up turns can bind by ID instead of re-scanning.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from types import SimpleNamespace

from services.ai.intent import Intent, IntentResult
from services.session import get_session, set_current_patient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_patient(pid=42, name="张三", gender="男", year_of_birth=1990):
    return SimpleNamespace(id=pid, name=name, gender=gender, year_of_birth=year_of_birth)


def _clear_session(doctor_id: str):
    """Reset session to clean state."""
    sess = get_session(doctor_id)
    sess.current_patient_id = None
    sess.current_patient_name = None


DOCTOR = "unit_doc_state_prop"


# ── handle_add_record pins patient ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_record_pins_current_patient(session_factory):
    """After add_record resolves a patient, current_patient should be set in session."""
    _clear_session(DOCTOR)
    patient = _make_patient()

    intent_result = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
    )

    from db.models.medical_record import MedicalRecord
    fake_record = MedicalRecord(content="胸痛两小时", tags=["胸痛"])

    with patch("routers.records_intent_handlers.AsyncSessionLocal", session_factory), \
         patch("routers.records_intent_handlers.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.records_intent_handlers.hydrate_session_state", new=AsyncMock()), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(return_value=fake_record)), \
         patch("routers.records_intent_handlers.create_pending_record", new=AsyncMock()):
        from routers.records_intent_handlers import handle_add_record
        await handle_add_record("张三胸痛两小时伴大汗淋漓", DOCTOR, [], intent_result, None)

    sess = get_session(DOCTOR)
    assert sess.current_patient_id == 42
    assert sess.current_patient_name == "张三"


# ── _handle_schedule_appointment pins patient ─────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_appointment_pins_current_patient(session_factory):
    """After schedule_appointment resolves a patient, current_patient should be set."""
    _clear_session(DOCTOR)
    patient = _make_patient(pid=55, name="王五")
    fake_task = SimpleNamespace(id=99)

    intent_result = IntentResult(
        intent=Intent.schedule_appointment,
        patient_name="王五",
        extra_data={"appointment_time": "2026-03-15T14:00:00", "notes": "复查"},
    )

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("routers.records.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.records.create_appointment_task", new=AsyncMock(return_value=fake_task)):
        from routers.records import _handle_schedule_appointment
        await _handle_schedule_appointment(DOCTOR, intent_result)

    sess = get_session(DOCTOR)
    assert sess.current_patient_id == 55
    assert sess.current_patient_name == "王五"


# ── _handle_update_record pins patient ────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_record_pins_current_patient(session_factory):
    """After update_record resolves a patient, current_patient should be set."""
    _clear_session(DOCTOR)
    patient = _make_patient(pid=77, name="李四")
    fake_record = SimpleNamespace(id=10)

    intent_result = IntentResult(
        intent=Intent.update_record,
        patient_name="李四",
        structured_fields={"diagnosis": "高血压"},
    )

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("routers.records.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.records.update_latest_record_for_patient", new=AsyncMock(return_value=fake_record)):
        from routers.records import _handle_update_record
        await _handle_update_record("更正李四诊断", DOCTOR, intent_result)

    sess = get_session(DOCTOR)
    assert sess.current_patient_id == 77
    assert sess.current_patient_name == "李四"
