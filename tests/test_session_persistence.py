"""Persistence tests for services/session.py."""
from unittest.mock import patch

from db.crud import create_patient
from services import session as sess_mod


DOCTOR = "persist_doc"


async def test_persist_and_hydrate_session_state(session_factory):
    async with session_factory() as db:
        patient = await create_patient(db, DOCTOR, "张三", "男", 30)

    with patch("services.session.AsyncSessionLocal", session_factory):
        sess_mod.set_current_patient(DOCTOR, patient.id, patient.name, persist=False)
        sess_mod.set_pending_create(DOCTOR, "李四", persist=False)
        await sess_mod.persist_session_state(DOCTOR)

        # Simulate a redeploy/process restart by clearing in-memory cache.
        sess_mod._sessions.clear()
        sess_mod._loaded_from_db.clear()

        restored = await sess_mod.hydrate_session_state(DOCTOR)

    assert restored.current_patient_id == patient.id
    assert restored.current_patient_name == "张三"
    assert restored.pending_create_name == "李四"


async def test_hydrate_clears_stale_patient_name_if_patient_missing(session_factory):
    with patch("services.session.AsyncSessionLocal", session_factory):
        # Write a state that points to a non-existent patient id.
        sess_mod.set_current_patient(DOCTOR, 9999, "不存在", persist=False)
        sess_mod.clear_pending_create(DOCTOR, persist=False)
        await sess_mod.persist_session_state(DOCTOR)

        sess_mod._sessions.clear()
        sess_mod._loaded_from_db.clear()
        restored = await sess_mod.hydrate_session_state(DOCTOR)

    assert restored.current_patient_id == 9999
    assert restored.current_patient_name is None
