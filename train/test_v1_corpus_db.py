"""Tests for v1 corpus behaviour: minimal single-sentence inputs → DB.

Contract (from clinic_raw_cases_cardiology_v1.md):
- chief_complaint      non-null  (extractable from the sentence)
- history_of_present_illness  non-null  (inferred from symptom description)
- past_medical_history  non-null or null  (only if explicitly mentioned)
- physical_examination  NULL  — no vitals in input
- auxiliary_examinations  NULL  — no test results in input (Case 007 partial exception)
- diagnosis            NULL  — must NOT be guessed from symptoms alone
- treatment_plan       NULL  — must NOT be inferred without a full clinical picture
- follow_up_plan       NULL  — no follow-up info given

All tests write through the real CRUD layer to an in-memory SQLite DB to verify
that null fields are stored as NULL (not as empty strings or placeholder text).
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.engine import Base
import db.models  # noqa: F401

from services.structuring import structure_medical_record
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


def _struct_llm_response(fields: dict):
    """Build a mock LLM completion that returns the given field dict as JSON."""
    msg = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    msg.content = json.dumps(fields, ensure_ascii=False)
    choice = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    choice.message = msg
    completion = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    completion.choices = [choice]
    return completion


async def _structure_and_save(input_text: str, patient_name: str, llm_fields: dict, db_factory):
    """Run structure_medical_record (mocked) then save_record to in-memory DB.
    Returns the saved MedicalRecordDB row.
    """
    mock_create = AsyncMock(return_value=_struct_llm_response(llm_fields))
    with patch("services.structuring.AsyncOpenAI", return_value=__import__(
        "unittest.mock", fromlist=["MagicMock"]
    ).MagicMock(chat=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(
        completions=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(create=mock_create)
    ))):
        record = await structure_medical_record(input_text)

    async with db_factory() as session:
        patient = await create_patient(session, DOCTOR_ID, patient_name, None, None)
        db_record = await save_record(session, DOCTOR_ID, record, patient.id)
        return db_record


# ---------------------------------------------------------------------------
# Parametrised v1 cases — (input_text, patient_name, expected_llm_fields)
# Each llm_fields reflects what a well-behaved model SHOULD return for v1 input.
# ---------------------------------------------------------------------------

V1_CASES = [
    # Case 001 — hypertension, no diagnosis/treatment possible from this input
    (
        "张建国，男，58岁，高血压十年，最近血压控制不好，最高到160/95，偶尔头晕，没有胸痛。",
        "张建国",
        {
            "chief_complaint": "血压控制不佳，偶有头晕",
            "history_of_present_illness": "近期血压最高160/95，无胸痛",
            "past_medical_history": "高血压十年",
            "physical_examination": None,
            "auxiliary_examinations": None,
            "diagnosis": None,
            "treatment_plan": None,
            "follow_up_plan": None,
        },
    ),
    # Case 002 — chest tightness on exertion, no workup results, no diagnosis
    (
        "陈美玲，女，63岁，反复胸闷半年，活动后加重，休息能缓解，有糖尿病史。",
        "陈美玲",
        {
            "chief_complaint": "反复胸闷半年，活动后加重，休息缓解",
            "history_of_present_illness": "活动诱发胸闷，休息缓解，持续半年",
            "past_medical_history": "糖尿病",
            "physical_examination": None,
            "auxiliary_examinations": None,
            "diagnosis": None,
            "treatment_plan": None,
            "follow_up_plan": None,
        },
    ),
    # Case 009 — chest pain, no ECG, no labs → diagnosis NULL
    (
        "高峰，男，50岁，胸痛发作一周，压榨样疼痛，持续10分钟左右。",
        "高峰",
        {
            "chief_complaint": "胸痛一周，压榨样，每次持续约10分钟",
            "history_of_present_illness": "反复发作压榨样胸痛，持续约十分钟",
            "past_medical_history": None,
            "physical_examination": None,
            "auxiliary_examinations": None,
            "diagnosis": None,
            "treatment_plan": None,
            "follow_up_plan": None,
        },
    ),
    # Case 016 — acute chest pain + diaphoresis (possible STEMI) — even here,
    # diagnosis must be NULL because there are no ECG or troponin results
    (
        "韩伟，男，59岁，突发胸痛两小时来诊，伴大汗。",
        "韩伟",
        {
            "chief_complaint": "突发胸痛两小时，伴大汗",
            "history_of_present_illness": "突发持续性胸痛两小时，伴大汗",
            "past_medical_history": None,
            "physical_examination": None,
            "auxiliary_examinations": None,
            "diagnosis": None,
            "treatment_plan": None,
            "follow_up_plan": None,
        },
    ),
    # Case 015 — AF, poor rate control — treatment NULL: no current meds listed
    (
        "郭建华，男，72岁，房颤五年，近期心率控制不佳。",
        "郭建华",
        {
            "chief_complaint": "房颤心率控制不佳",
            "history_of_present_illness": "近期心率控制不佳",
            "past_medical_history": "房颤五年",
            "physical_examination": None,
            "auxiliary_examinations": None,
            "diagnosis": None,
            "treatment_plan": None,
            "follow_up_plan": None,
        },
    ),
]


@pytest.mark.parametrize("text,patient_name,fields", V1_CASES,
                          ids=[c[1] for c in V1_CASES])
async def test_v1_null_fields_stored_as_null_in_db(text, patient_name, fields, db):
    """diagnosis and treatment_plan must be NULL in DB for all v1 cases."""
    row = await _structure_and_save(text, patient_name, fields, db)
    assert row.diagnosis is None, (
        f"[{patient_name}] diagnosis should be NULL in DB, got: {row.diagnosis!r}"
    )
    assert row.treatment_plan is None, (
        f"[{patient_name}] treatment_plan should be NULL in DB, got: {row.treatment_plan!r}"
    )
    assert row.follow_up_plan is None, (
        f"[{patient_name}] follow_up_plan should be NULL in DB, got: {row.follow_up_plan!r}"
    )
    assert row.physical_examination is None, (
        f"[{patient_name}] physical_examination should be NULL in DB, got: {row.physical_examination!r}"
    )


@pytest.mark.parametrize("text,patient_name,fields", V1_CASES,
                          ids=[c[1] for c in V1_CASES])
async def test_v1_chief_complaint_stored_non_null(text, patient_name, fields, db):
    """chief_complaint must be non-null and non-empty for all v1 cases."""
    row = await _structure_and_save(text, patient_name, fields, db)
    assert row.chief_complaint is not None, (
        f"[{patient_name}] chief_complaint should not be NULL"
    )
    assert row.chief_complaint.strip() != "", (
        f"[{patient_name}] chief_complaint should not be empty string"
    )


@pytest.mark.parametrize("text,patient_name,fields", V1_CASES,
                          ids=[c[1] for c in V1_CASES])
async def test_v1_history_of_present_illness_stored_non_null(text, patient_name, fields, db):
    """history_of_present_illness must be populated for all v1 cases."""
    row = await _structure_and_save(text, patient_name, fields, db)
    assert row.history_of_present_illness is not None, (
        f"[{patient_name}] history_of_present_illness should not be NULL"
    )


# ---------------------------------------------------------------------------
# Verify DB stores exactly what structure_medical_record returned (no mutation)
# ---------------------------------------------------------------------------

async def test_v1_db_stores_exact_chief_complaint(db):
    text = "张建国，男，58岁，高血压十年，最近血压控制不好，最高到160/95，偶尔头晕，没有胸痛。"
    fields = {
        "chief_complaint": "血压控制不佳，偶有头晕",
        "history_of_present_illness": "近期血压最高160/95，无胸痛",
        "past_medical_history": "高血压十年",
        "physical_examination": None,
        "auxiliary_examinations": None,
        "diagnosis": None,
        "treatment_plan": None,
        "follow_up_plan": None,
    }
    row = await _structure_and_save(text, "张建国", fields, db)
    assert row.chief_complaint == "血压控制不佳，偶有头晕"
    assert row.past_medical_history == "高血压十年"


async def test_v1_record_linked_to_patient_in_db(db):
    """The saved record must be linked to the patient row via patient_id."""
    text = "高峰，男，50岁，胸痛发作一周，压榨样疼痛，持续10分钟左右。"
    fields = {
        "chief_complaint": "胸痛一周",
        "history_of_present_illness": "压榨样胸痛",
        "past_medical_history": None,
        "physical_examination": None,
        "auxiliary_examinations": None,
        "diagnosis": None,
        "treatment_plan": None,
        "follow_up_plan": None,
    }
    row = await _structure_and_save(text, "高峰", fields, db)
    assert row.patient_id is not None

    async with db() as session:
        patient = await find_patient_by_name(session, DOCTOR_ID, "高峰")
        records = await get_records_for_patient(session, DOCTOR_ID, patient.id)

    assert len(records) == 1
    assert records[0].patient_id == patient.id


async def test_v1_auxiliary_examinations_null_no_ecg_result(db):
    """Case 007 mentions 'ECG abnormality' but no specific values → still NULL."""
    text = "何志远，男，39岁，体检发现心电图异常，无明显症状。"
    # A well-behaved model: no numeric result mentioned → auxiliary_examinations null
    fields = {
        "chief_complaint": "体检发现心电图异常，无症状",
        "history_of_present_illness": "体检心电图异常，无明显自觉症状",
        "past_medical_history": None,
        "physical_examination": None,
        "auxiliary_examinations": None,   # "abnormal ECG" with no values → null
        "diagnosis": None,
        "treatment_plan": None,
        "follow_up_plan": None,
    }
    row = await _structure_and_save(text, "何志远", fields, db)
    assert row.auxiliary_examinations is None
    assert row.diagnosis is None


async def test_v1_acute_chest_pain_diagnosis_still_null_without_ecg(db):
    """Case 016: acute chest pain + diaphoresis.
    Even though this pattern suggests ACS, diagnosis MUST be NULL because
    the input contains no ECG findings or troponin — the model must not guess.
    """
    text = "韩伟，男，59岁，突发胸痛两小时来诊，伴大汗。"
    fields = {
        "chief_complaint": "突发胸痛两小时，伴大汗",
        "history_of_present_illness": "突发持续性胸痛两小时，伴大汗",
        "past_medical_history": None,
        "physical_examination": None,
        "auxiliary_examinations": None,
        "diagnosis": None,       # no ECG result → must not guess STEMI
        "treatment_plan": None,  # no confirmed diagnosis → must not prescribe
        "follow_up_plan": None,
    }
    row = await _structure_and_save(text, "韩伟", fields, db)
    assert row.diagnosis is None, (
        "diagnosis must be NULL for Case 016: no ECG/troponin data to confirm any diagnosis"
    )
    assert row.treatment_plan is None, (
        "treatment_plan must be NULL when diagnosis is not confirmed"
    )
