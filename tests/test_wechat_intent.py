"""微信意图派发测试：验证微信路由中创建患者、添加病历、查询记录、列出患者及删除患者等意图的处理逻辑，LLM 和数据库均使用模拟对象。"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.ai.intent import Intent, IntentResult
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
    # "帮我建个新患者，李明，45岁男性" is now handled by the fast router (no LLM call).
    # route_message mock is provided but won't be invoked for this fast-path message.
    with patch("services.ai.agent.dispatch", new=AsyncMock(
        return_value=_intent(Intent.create_patient, name="李明", gender="男", age=45)
    )), patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_intent("帮我建个新患者，李明，45岁男性", DOCTOR)
    assert "李明" in reply
    assert "创建" in reply or "✅" in reply or "已为" in reply


async def test_handle_intent_routes_unknown_to_help_message(wechat):
    from services.ai.intent import IntentResult
    with patch("services.ai.agent.dispatch", new=AsyncMock(
        return_value=IntentResult(intent=Intent.unknown, chat_reply="您好，有什么可以帮您？")
    )):
        reply = await wechat._handle_intent("今天天气真好", DOCTOR)
    assert reply  # any non-empty reply is acceptable for conversational fallback


async def test_handle_intent_falls_back_on_detection_error(wechat):
    from db.models.medical_record import MedicalRecord
    fake_record = MedicalRecord(content="发烧")
    with patch("services.ai.agent.dispatch", side_effect=Exception("LLM down")), \
         patch("routers.wechat.structure_medical_record", new=AsyncMock(return_value=fake_record)) as mock_struct:
        reply = await wechat._handle_intent("some text", DOCTOR)
    mock_struct.assert_awaited_once()
    assert reply  # non-empty reply (formatted record or short error)


async def test_handle_intent_logs_and_continues_when_knowledge_context_load_fails(wechat):
    from services.ai.intent import IntentResult

    with patch("routers.wechat.load_knowledge_context_for_prompt", new=AsyncMock(side_effect=RuntimeError("db busy"))), \
         patch("services.ai.agent.dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply="ok"))):
        reply = await wechat._handle_intent("今天天气", DOCTOR)
    assert reply == "ok"


async def test_handle_intent_structuring_fallback_unexpected_error_returns_generic_message(wechat):
    with patch("services.ai.agent.dispatch", side_effect=Exception("LLM down")), \
         patch("routers.wechat.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("boom"))):
        reply = await wechat._handle_intent("some text", DOCTOR)
    assert "不好意思" in reply


async def test_handle_intent_routes_delete_patient(wechat, session_factory):
    from db.crud import create_patient, get_all_patients

    async with session_factory() as s:
        await create_patient(s, DOCTOR, "章三", None, None)

    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(
            return_value=IntentResult(
                intent=Intent.delete_patient,
                patient_name="章三",
            )
        ),
    ), patch("routers.wechat.AsyncSessionLocal", session_factory):
        wechat._sync_wechat_domain_bindings()
        reply = await wechat._handle_intent("删除患者章三", DOCTOR)
    assert "已删除患者【章三】" in reply

    async with session_factory() as s:
        patients = await get_all_patients(s, DOCTOR)
    assert len([p for p in patients if p.name == "章三"]) == 0


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

    from db.models.medical_record import MedicalRecord
    fake_record = MedicalRecord(
        content="头痛 两天头痛 紧张性头痛 布洛芬",
        tags=["紧张性头痛"],
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record(FAKE_RECORD_TEXT, DOCTOR, _intent(Intent.add_record))

    assert "病历草稿" in reply or "李明" in reply  # draft created (name may be in header)


async def test_add_record_links_patient_from_message_name(wechat, session_factory):
    # Patient exists in DB
    async with session_factory() as s:
        from db.crud import create_patient
        await create_patient(s, DOCTOR, "张三", None, None)

    from db.models.medical_record import MedicalRecord
    fake_record = MedicalRecord(
        content="咳嗽 三天咳嗽 上呼吸道感染 多休息",
        tags=["上呼吸道感染"],
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record(
            "张三今天咳嗽", DOCTOR, _intent(Intent.add_record, name="张三")
        )

    assert "张三" in reply


async def test_add_record_auto_creates_patient_when_not_in_db(wechat, session_factory):
    """When a name is mentioned but patient doesn't exist, auto-create and link."""
    from db.models.medical_record import MedicalRecord
    fake_record = MedicalRecord(
        content="头疼 最近头疼很久 多喝热水",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record(
            "王芳，最近头疼很久，需要多喝热水", DOCTOR, _intent(Intent.add_record, name="王芳")
        )

    assert "王芳" in reply  # natural reply contains patient name
    # Patient should now exist in DB
    async with session_factory() as s:
        from db.crud import find_patient_by_name
        patient = await find_patient_by_name(s, DOCTOR, "王芳")
    assert patient is not None


async def test_add_record_works_without_patient(wechat, session_factory):
    """Records with no patient context are still saved (patient_id=None)."""
    from db.models.medical_record import MedicalRecord
    fake_record = MedicalRecord(
        content="发烧 发烧一天 病毒感染 退烧药",
        tags=["病毒感染"],
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record(
            "患者发烧一天", DOCTOR, _intent(Intent.add_record)
        )

    assert "病历" in reply  # natural fallback reply


# ---------------------------------------------------------------------------
# _handle_query_records
# ---------------------------------------------------------------------------


async def test_query_records_no_patient_returns_all_records_empty(wechat, session_factory):
    # No patient and no records at all → generic empty message
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(DOCTOR, _intent(Intent.query_records))
    assert "暂无" in reply


async def test_query_records_no_patient_returns_all_records(wechat, session_factory):
    from db.models.medical_record import MedicalRecord
    from db.crud import create_patient, save_record

    async with session_factory() as s:
        p1 = await create_patient(s, DOCTOR, "李明", None, None)
        p2 = await create_patient(s, DOCTOR, "王芳", None, None)
        await save_record(s, DOCTOR, MedicalRecord(
            content="头痛 两天 紧张性头痛 布洛芬", tags=["紧张性头痛"]
        ), p1.id)
        await save_record(s, DOCTOR, MedicalRecord(
            content="咳嗽 三天 上呼吸道感染 多休息", tags=["上呼吸道感染"]
        ), p2.id)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(DOCTOR, _intent(Intent.query_records))

    assert "所有患者" in reply
    assert "李明" in reply
    assert "王芳" in reply


async def test_query_records_by_name_returns_list(wechat, session_factory):
    from db.models.medical_record import MedicalRecord
    from db.crud import create_patient, save_record

    async with session_factory() as s:
        p = await create_patient(s, DOCTOR, "李明", None, None)
        rec = MedicalRecord(
            content="头痛 两天头痛 紧张性头痛 布洛芬",
            tags=["紧张性头痛"],
        )
        await save_record(s, DOCTOR, rec, p.id)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_query_records(
            DOCTOR, _intent(Intent.query_records, name="李明")
        )

    assert "李明" in reply
    assert "头痛" in reply or "紧张性头痛" in reply


async def test_query_records_uses_session_patient_when_no_name(wechat, session_factory):
    from db.models.medical_record import MedicalRecord
    from db.crud import create_patient, save_record

    async with session_factory() as s:
        p = await create_patient(s, DOCTOR, "王五", None, None)
        rec = MedicalRecord(
            content="腰痛 腰痛一周 腰肌劳损 理疗",
            tags=["腰肌劳损"],
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


# ---------------------------------------------------------------------------
# Emergency flag
# ---------------------------------------------------------------------------


async def test_add_record_emergency_reply_has_prefix(wechat, session_factory):
    from db.models.medical_record import MedicalRecord
    from services.ai.intent import IntentResult

    fake_record = MedicalRecord(
        content="室颤 突发室颤 立即除颤",
        tags=["室颤"],
    )
    emergency_intent = IntentResult(
        intent=Intent.add_record,
        patient_name=None,
        is_emergency=True,
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record("3床室颤，立即除颤", DOCTOR, emergency_intent)

    assert "🚨" in reply  # emergency prefix always present


# ---------------------------------------------------------------------------
# list_patients intent
# ---------------------------------------------------------------------------


async def test_handle_intent_routes_list_patients(wechat, session_factory):
    from services.ai.intent import IntentResult

    with patch("services.ai.agent.dispatch", new=AsyncMock(
        return_value=IntentResult(intent=Intent.list_patients)
    )), patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_intent("所有患者", DOCTOR)

    # Empty DB → helpful prompt
    assert "患者" in reply


async def test_handle_all_patients_empty(wechat, session_factory):
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_all_patients(DOCTOR)
    assert "暂无" in reply
    assert "新患者" in reply or "创建" in reply or "发送" in reply


async def test_handle_all_patients_shows_numbered_list(wechat, session_factory):
    from db.crud import create_patient
    async with session_factory() as s:
        await create_patient(s, DOCTOR, "李明", "男", 45)
        await create_patient(s, DOCTOR, "王芳", "女", 30)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_all_patients(DOCTOR)

    assert "李明" in reply
    assert "王芳" in reply
    assert "2" in reply  # total count or numbering


# ---------------------------------------------------------------------------
# _format_record edge cases
# ---------------------------------------------------------------------------


def test_format_record_all_fields(wechat):
    from db.models.medical_record import MedicalRecord
    rec = MedicalRecord(
        content="胸痛持续两小时，高血压病史，血压160/100，心电图ST段抬高，诊断急性心肌梗死，阿司匹林＋溶栓，一周后复查。",
        tags=["急性心肌梗死"],
    )
    text = wechat._format_record(rec)
    assert "病历记录" in text
    assert "胸痛" in text


def test_format_record_optional_fields_absent(wechat):
    from db.models.medical_record import MedicalRecord
    rec = MedicalRecord(
        content="头疼 最近头疼很久",
    )
    text = wechat._format_record(rec)
    assert "头疼" in text


def test_format_record_minimal(wechat):
    """Only content — should not crash."""
    from db.models.medical_record import MedicalRecord
    rec = MedicalRecord(content="发烧")
    text = wechat._format_record(rec)
    assert "发烧" in text


# ---------------------------------------------------------------------------
# _split_message
# ---------------------------------------------------------------------------


def test_split_message_short_returns_single_chunk(wechat):
    chunks = wechat._split_message("短消息")
    assert chunks == ["短消息"]


def test_split_message_long_splits_at_section_header(wechat):
    # Build a message just over the limit that has a 【 marker inside
    body = "A" * 400
    section = "【诊断】\n急性心肌梗死"
    text = body + section + "B" * 300
    chunks = wechat._split_message(text, limit=600)
    assert len(chunks) > 1
    # The second chunk should start at the 【 boundary
    assert chunks[1].startswith("【")


def test_split_message_no_header_splits_at_limit(wechat):
    text = "X" * 1300
    chunks = wechat._split_message(text, limit=600)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 600
