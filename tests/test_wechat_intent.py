"""Tests for the intent dispatch logic in routers/wechat.py.

All LLM calls and DB sessions are mocked — no network or disk I/O.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.intent import Intent, IntentResult
from services.session import set_current_patient, get_session


DOCTOR = "openid_doc_001"


def _intent(intent: Intent, name=None, gender=None, age=None) -> IntentResult:
    return IntentResult(intent=intent, patient_name=name, gender=gender, age=age)


# ---------------------------------------------------------------------------
# Helpers to import handler functions after patching
# ---------------------------------------------------------------------------


@pytest.fixture
def wechat(session_factory):
    """Import wechat module with DB patched to in-memory SQLite."""
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        import routers.wechat as mod
        yield mod


# ---------------------------------------------------------------------------
# _handle_intent — routing
# ---------------------------------------------------------------------------


async def test_handle_intent_routes_create_patient(wechat, session_factory):
    with patch("routers.wechat.detect_intent", new=AsyncMock(
        return_value=_intent(Intent.create_patient, name="李明", gender="男", age=45)
    )):
        reply = await wechat._handle_intent("帮我建个新患者，李明，45岁男性", DOCTOR)
    assert "李明" in reply
    assert "建档" in reply or "✅" in reply


async def test_handle_intent_routes_unknown_to_help_message(wechat):
    with patch("routers.wechat.detect_intent", new=AsyncMock(
        return_value=_intent(Intent.unknown)
    )):
        reply = await wechat._handle_intent("今天天气真好", DOCTOR)
    assert "病历" in reply or "患者" in reply or "查询" in reply


async def test_handle_intent_falls_back_on_detection_error(wechat):
    with patch("routers.wechat.detect_intent", side_effect=Exception("LLM down")), \
         patch("routers.wechat._build_reply", new=AsyncMock(return_value="fallback")) as mock_build:
        reply = await wechat._handle_intent("some text", DOCTOR)
    assert reply == "fallback"
    mock_build.assert_awaited_once()


# ---------------------------------------------------------------------------
# _handle_create_patient
# ---------------------------------------------------------------------------


async def test_create_patient_without_name_returns_error(wechat):
    reply = await wechat._handle_create_patient(DOCTOR, _intent(Intent.create_patient, name=None))
    assert "⚠️" in reply


async def test_create_patient_sets_session(wechat, session_factory):
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_create_patient(
            DOCTOR, _intent(Intent.create_patient, name="李明", gender="男", age=45)
        )
    assert "李明" in reply
    sess = get_session(DOCTOR)
    assert sess.current_patient_name == "李明"
    assert sess.current_patient_id is not None


async def test_create_patient_reply_includes_gender_age(wechat, session_factory):
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_create_patient(
            DOCTOR, _intent(Intent.create_patient, name="张三", gender="女", age=30)
        )
    assert "张三" in reply
    assert "女" in reply
    assert "30" in reply


# ---------------------------------------------------------------------------
# _handle_add_record
# ---------------------------------------------------------------------------


FAKE_RECORD_TEXT = "患者头痛两天，诊断紧张性头痛，布洛芬治疗"


async def test_add_record_uses_session_patient_when_no_name_in_message(wechat, session_factory):
    # Pre-set a current patient in session (via real DB row)
    async with session_factory() as s:
        from db.crud import create_patient
        p = await create_patient(s, DOCTOR, "李明", None, None)
    set_current_patient(DOCTOR, p.id, p.name)

    from models.medical_record import MedicalRecord
    fake_record = MedicalRecord(
        chief_complaint="头痛",
        history_of_present_illness="两天头痛",
        diagnosis="紧张性头痛",
        treatment_plan="布洛芬",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record(FAKE_RECORD_TEXT, DOCTOR, _intent(Intent.add_record))

    assert "李明" in reply
    assert "头痛" in reply


async def test_add_record_links_patient_from_message_name(wechat, session_factory):
    # Patient exists in DB
    async with session_factory() as s:
        from db.crud import create_patient
        await create_patient(s, DOCTOR, "张三", None, None)

    from models.medical_record import MedicalRecord
    fake_record = MedicalRecord(
        chief_complaint="咳嗽",
        history_of_present_illness="三天咳嗽",
        diagnosis="上呼吸道感染",
        treatment_plan="多休息",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record(
            "张三今天咳嗽", DOCTOR, _intent(Intent.add_record, name="张三")
        )

    assert "张三" in reply


async def test_add_record_works_without_patient(wechat, session_factory):
    """Records with no patient context are still saved (patient_id=None)."""
    from models.medical_record import MedicalRecord
    fake_record = MedicalRecord(
        chief_complaint="发烧",
        history_of_present_illness="发烧一天",
        diagnosis="病毒感染",
        treatment_plan="退烧药",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record(
            "患者发烧一天", DOCTOR, _intent(Intent.add_record)
        )

    assert "发烧" in reply or "诊断" in reply


# ---------------------------------------------------------------------------
# _handle_query_records
# ---------------------------------------------------------------------------


async def test_query_records_no_patient_returns_all_records_empty(wechat, session_factory):
    # No patient and no records at all → generic empty message
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(DOCTOR, _intent(Intent.query_records))
    assert "暂无" in reply


async def test_query_records_no_patient_returns_all_records(wechat, session_factory):
    from models.medical_record import MedicalRecord
    from db.crud import create_patient, save_record

    async with session_factory() as s:
        p1 = await create_patient(s, DOCTOR, "李明", None, None)
        p2 = await create_patient(s, DOCTOR, "王芳", None, None)
        await save_record(s, DOCTOR, MedicalRecord(
            chief_complaint="头痛", history_of_present_illness="两天", diagnosis="紧张性头痛", treatment_plan="布洛芬"
        ), p1.id)
        await save_record(s, DOCTOR, MedicalRecord(
            chief_complaint="咳嗽", history_of_present_illness="三天", diagnosis="上呼吸道感染", treatment_plan="多休息"
        ), p2.id)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(DOCTOR, _intent(Intent.query_records))

    assert "所有患者" in reply
    assert "李明" in reply
    assert "王芳" in reply


async def test_query_records_by_name_returns_list(wechat, session_factory):
    from models.medical_record import MedicalRecord
    from db.crud import create_patient, save_record

    async with session_factory() as s:
        p = await create_patient(s, DOCTOR, "李明", None, None)
        rec = MedicalRecord(
            chief_complaint="头痛",
            history_of_present_illness="两天头痛",
            diagnosis="紧张性头痛",
            treatment_plan="布洛芬",
        )
        await save_record(s, DOCTOR, rec, p.id)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(
            DOCTOR, _intent(Intent.query_records, name="李明")
        )

    assert "李明" in reply
    assert "头痛" in reply or "紧张性头痛" in reply


async def test_query_records_uses_session_patient_when_no_name(wechat, session_factory):
    from models.medical_record import MedicalRecord
    from db.crud import create_patient, save_record

    async with session_factory() as s:
        p = await create_patient(s, DOCTOR, "王五", None, None)
        rec = MedicalRecord(
            chief_complaint="腰痛",
            history_of_present_illness="腰痛一周",
            diagnosis="腰肌劳损",
            treatment_plan="理疗",
        )
        await save_record(s, DOCTOR, rec, p.id)

    set_current_patient(DOCTOR, p.id, p.name)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(DOCTOR, _intent(Intent.query_records))

    assert "王五" in reply
    assert "腰痛" in reply or "腰肌劳损" in reply


async def test_query_records_empty_history(wechat, session_factory):
    from db.crud import create_patient

    async with session_factory() as s:
        p = await create_patient(s, DOCTOR, "李明", None, None)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(
            DOCTOR, _intent(Intent.query_records, name="李明")
        )

    assert "暂无" in reply
