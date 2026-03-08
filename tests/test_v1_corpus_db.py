"""Tests for v1 corpus behaviour: minimal single-sentence inputs → DB.

Contract (updated for content-first schema):
- content  non-null and non-empty (the LLM-cleaned prose note)
- tags  list (may be empty)
- record_type  defaults to "visit"

All tests write through the real CRUD layer to an in-memory SQLite DB to verify
that the content field is properly stored and linked to patients.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.engine import Base
import db.models  # noqa: F401

from models.medical_record import MedicalRecord
from db.crud import save_record, find_patient_by_name, create_patient, get_records_for_patient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOCTOR_ID = "v1_test_doctor"


@pytest_asyncio.fixture
async def db(monkeypatch):
    """Fresh in-memory SQLite for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _structure_and_save(input_text: str, patient_name: str, record: MedicalRecord, db_factory):
    """Save a pre-built MedicalRecord to in-memory DB.
    Returns the saved MedicalRecordDB row.
    """
    async with db_factory() as session:
        patient = await create_patient(session, DOCTOR_ID, patient_name, None, None)
        db_record = await save_record(session, DOCTOR_ID, record, patient.id)
        return db_record


# ---------------------------------------------------------------------------
# Parametrised v1 cases — (input_text, patient_name, MedicalRecord)
# Each record reflects what a well-behaved model SHOULD return for v1 input.
# ---------------------------------------------------------------------------

V1_CASES = [
    # Case 001 — hypertension, blood pressure control
    (
        "张建国，男，58岁，高血压十年，最近血压控制不好，最高到160/95，偶尔头晕，没有胸痛。",
        "张建国",
        MedicalRecord(
            content="血压控制不佳，偶有头晕。高血压病史十年，近期血压最高160/95，无胸痛。",
            tags=["高血压"],
        ),
    ),
    # Case 002 — chest tightness on exertion
    (
        "陈美玲，女，63岁，反复胸闷半年，活动后加重，休息能缓解，有糖尿病史。",
        "陈美玲",
        MedicalRecord(
            content="反复胸闷半年，活动后加重，休息缓解。既往糖尿病史。",
            tags=["胸闷", "糖尿病"],
        ),
    ),
    # Case 009 — chest pain, no ECG
    (
        "高峰，男，50岁，胸痛发作一周，压榨样疼痛，持续10分钟左右。",
        "高峰",
        MedicalRecord(
            content="胸痛一周，压榨样，每次持续约10分钟。",
            tags=["胸痛"],
        ),
    ),
    # Case 016 — acute chest pain + diaphoresis
    (
        "韩伟，男，59岁，突发胸痛两小时来诊，伴大汗。",
        "韩伟",
        MedicalRecord(
            content="突发胸痛两小时，伴大汗。",
            tags=["胸痛"],
        ),
    ),
    # Case 015 — AF, poor rate control
    (
        "郭建华，男，72岁，房颤五年，近期心率控制不佳。",
        "郭建华",
        MedicalRecord(
            content="房颤五年，近期心率控制不佳。",
            tags=["房颤"],
        ),
    ),
]


@pytest.mark.parametrize("text,patient_name,record", V1_CASES,
                          ids=[c[1] for c in V1_CASES])
async def test_v1_content_stored_non_null(text, patient_name, record, db):
    """content must be non-null and non-empty for all v1 cases."""
    row = await _structure_and_save(text, patient_name, record, db)
    assert row.content is not None, (
        f"[{patient_name}] content should not be NULL"
    )
    assert row.content.strip() != "", (
        f"[{patient_name}] content should not be empty string"
    )


@pytest.mark.parametrize("text,patient_name,record", V1_CASES,
                          ids=[c[1] for c in V1_CASES])
async def test_v1_record_linked_to_patient(text, patient_name, record, db):
    """Each saved record must be linked to the patient row via patient_id."""
    row = await _structure_and_save(text, patient_name, record, db)
    assert row.patient_id is not None, (
        f"[{patient_name}] record should be linked to a patient"
    )


# ---------------------------------------------------------------------------
# Verify DB stores exactly what was passed (no mutation)
# ---------------------------------------------------------------------------

async def test_v1_db_stores_exact_content(db):
    record = MedicalRecord(
        content="血压控制不佳，偶有头晕。高血压病史十年，近期血压最高160/95，无胸痛。",
        tags=["高血压"],
    )
    row = await _structure_and_save(
        "张建国，男，58岁，高血压十年，最近血压控制不好，最高到160/95，偶尔头晕，没有胸痛。",
        "张建国",
        record,
        db,
    )
    assert "血压控制不佳" in row.content
    assert "高血压" in row.content


async def test_v1_record_linked_to_patient_in_db(db):
    """The saved record must be linked to the patient row via patient_id."""
    record = MedicalRecord(
        content="胸痛一周，压榨样，每次持续约10分钟。",
        tags=["胸痛"],
    )
    row = await _structure_and_save(
        "高峰，男，50岁，胸痛发作一周，压榨样疼痛，持续10分钟左右。",
        "高峰",
        record,
        db,
    )
    assert row.patient_id is not None

    async with db() as session:
        patient = await find_patient_by_name(session, DOCTOR_ID, "高峰")
        records = await get_records_for_patient(session, DOCTOR_ID, patient.id)

    assert len(records) == 1
    assert records[0].patient_id == patient.id


async def test_v1_tags_stored_as_list(db):
    """Tags should be stored and retrievable."""
    record = MedicalRecord(
        content="体检发现心电图异常，无明显自觉症状。",
        tags=["心电图异常"],
    )
    row = await _structure_and_save(
        "何志远，男，39岁，体检发现心电图异常，无明显症状。",
        "何志远",
        record,
        db,
    )
    assert row.content is not None
    assert "心电图异常" in row.content


async def test_v1_acute_chest_pain_content_stored(db):
    """Case 016: acute chest pain + diaphoresis — content is stored correctly."""
    record = MedicalRecord(
        content="突发胸痛两小时，伴大汗。",
        tags=["胸痛"],
    )
    row = await _structure_and_save(
        "韩伟，男，59岁，突发胸痛两小时来诊，伴大汗。",
        "韩伟",
        record,
        db,
    )
    assert row.content is not None
    assert row.content.strip() != ""
    assert "胸痛" in row.content
