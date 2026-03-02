"""Tests for services/agent.py — LLM function calling is mocked.

Verifies that:
- Each tool name maps to the correct Intent
- patient_name / gender / age are extracted from tool args
- is_emergency flag is correctly read
- Invalid age/gender are coerced to None
- No tool call → chat_reply is returned
- conversation history is forwarded to the LLM
- Malformed JSON args don't raise
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.intent import Intent
from services.agent import dispatch


def _make_tool_call(fn_name: str, args: dict):
    tc = MagicMock()
    tc.function.name = fn_name
    tc.function.arguments = json.dumps(args, ensure_ascii=False)
    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = None
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _make_chat_reply(content: str):
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-tests")
    mock_client = AsyncMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create
    with patch("services.agent.AsyncOpenAI", return_value=mock_client):
        yield mock_create


# ---------------------------------------------------------------------------
# Tool → Intent mapping
# ---------------------------------------------------------------------------


async def test_dispatch_add_medical_record_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {"patient_name": "张三"})
    result = await dispatch("张三今天胸痛...")
    assert result.intent == Intent.add_record


async def test_dispatch_create_patient_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("create_patient", {"name": "李明"})
    result = await dispatch("新患者李明")
    assert result.intent == Intent.create_patient


async def test_dispatch_query_records_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("query_records", {"patient_name": "王芳"})
    result = await dispatch("查一下王芳的病历")
    assert result.intent == Intent.query_records


async def test_dispatch_list_patients_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("list_patients", {})
    result = await dispatch("列出所有患者")
    assert result.intent == Intent.list_patients


async def test_dispatch_no_tool_call_returns_unknown(mock_llm):
    mock_llm.return_value = _make_chat_reply("您好！有什么可以帮您？")
    result = await dispatch("你好")
    assert result.intent == Intent.unknown


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


async def test_dispatch_extracts_patient_name_from_add_record(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {"patient_name": "贺志强", "age": 62, "gender": "男"})
    result = await dispatch("贺志强，62岁，胸闷...")
    assert result.patient_name == "贺志强"
    assert result.age == 62
    assert result.gender == "男"


async def test_dispatch_extracts_name_field_from_create_patient(mock_llm):
    """create_patient uses 'name' key, not 'patient_name'."""
    mock_llm.return_value = _make_tool_call("create_patient", {"name": "李小红", "gender": "女", "age": 42})
    result = await dispatch("新患者李小红，女，42岁")
    assert result.patient_name == "李小红"
    assert result.gender == "女"
    assert result.age == 42


async def test_dispatch_patient_name_none_when_not_in_args(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {})
    result = await dispatch("患者发烧两天")
    assert result.patient_name is None


async def test_dispatch_chat_reply_returned_when_no_tool(mock_llm):
    mock_llm.return_value = _make_chat_reply("您好，我是医生助手。")
    result = await dispatch("你好")
    assert result.chat_reply == "您好，我是医生助手。"


# ---------------------------------------------------------------------------
# is_emergency
# ---------------------------------------------------------------------------


async def test_dispatch_is_emergency_true_when_set(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {
        "patient_name": "韩伟",
        "is_emergency": True,
    })
    result = await dispatch("韩伟，STEMI，急诊PCI绿色通道")
    assert result.is_emergency is True


async def test_dispatch_is_emergency_defaults_false_when_absent(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {"patient_name": "张三"})
    result = await dispatch("张三头痛两天")
    assert result.is_emergency is False


async def test_dispatch_is_emergency_false_when_explicitly_false(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {
        "patient_name": "张三",
        "is_emergency": False,
    })
    result = await dispatch("张三头痛两天")
    assert result.is_emergency is False


# ---------------------------------------------------------------------------
# Field validation / coercion
# ---------------------------------------------------------------------------


async def test_dispatch_non_integer_age_coerced_to_none(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {"patient_name": "李明", "age": "四十岁"})
    result = await dispatch("李明四十岁，胸痛")
    assert result.age is None


async def test_dispatch_float_age_coerced_to_none(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {"patient_name": "李明", "age": 45.5})
    result = await dispatch("李明胸痛")
    assert result.age is None


async def test_dispatch_invalid_gender_coerced_to_none(mock_llm):
    mock_llm.return_value = _make_tool_call("create_patient", {"name": "王五", "gender": "male"})
    result = await dispatch("新患者王五")
    assert result.gender is None


async def test_dispatch_valid_gender_male_preserved(mock_llm):
    mock_llm.return_value = _make_tool_call("create_patient", {"name": "王五", "gender": "男"})
    result = await dispatch("新患者王五，男")
    assert result.gender == "男"


async def test_dispatch_valid_gender_female_preserved(mock_llm):
    mock_llm.return_value = _make_tool_call("create_patient", {"name": "李芳", "gender": "女"})
    result = await dispatch("新患者李芳，女")
    assert result.gender == "女"


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------


async def test_dispatch_passes_history_between_system_and_user(mock_llm):
    mock_llm.return_value = _make_chat_reply("OK")
    history = [
        {"role": "user", "content": "上一条消息"},
        {"role": "assistant", "content": "好的"},
    ]
    await dispatch("当前消息", history=history)
    messages = mock_llm.call_args.kwargs["messages"]
    # system + 2 history + 1 current = 4
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "上一条消息"
    assert messages[2]["content"] == "好的"
    assert messages[3]["content"] == "当前消息"


async def test_dispatch_no_history_sends_system_plus_user_only(mock_llm):
    mock_llm.return_value = _make_chat_reply("OK")
    await dispatch("你好")
    messages = mock_llm.call_args.kwargs["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


async def test_dispatch_empty_history_list_handled(mock_llm):
    mock_llm.return_value = _make_chat_reply("OK")
    await dispatch("你好", history=[])
    messages = mock_llm.call_args.kwargs["messages"]
    assert len(messages) == 2


# ---------------------------------------------------------------------------
# Malformed / edge-case LLM responses
# ---------------------------------------------------------------------------


async def test_dispatch_malformed_json_args_does_not_raise(mock_llm):
    tc = MagicMock()
    tc.function.name = "add_medical_record"
    tc.function.arguments = "{not: valid json"
    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = None
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    mock_llm.return_value = completion

    result = await dispatch("some input")
    assert result.intent == Intent.add_record
    assert result.patient_name is None


async def test_dispatch_unknown_tool_name_returns_unknown_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("nonexistent_tool", {})
    result = await dispatch("some input")
    assert result.intent == Intent.unknown


async def test_dispatch_empty_tool_calls_list_treated_as_no_tool(mock_llm):
    msg = MagicMock()
    msg.tool_calls = []
    msg.content = "fallback reply"
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    mock_llm.return_value = completion

    result = await dispatch("你好")
    assert result.intent == Intent.unknown
    assert result.chat_reply == "fallback reply"
