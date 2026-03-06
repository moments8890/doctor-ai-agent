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
import services.agent as agent


def _make_tool_call(fn_name: str, args: dict, content: str = None):
    tc = MagicMock()
    tc.function.name = fn_name
    tc.function.arguments = json.dumps(args, ensure_ascii=False)
    msg = MagicMock()
    msg.tool_calls = [tc]
    msg.content = content
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


async def test_dispatch_delete_patient_intent(mock_llm):
    mock_llm.return_value = _make_tool_call("delete_patient", {"patient_name": "章三", "occurrence_index": 2})
    result = await dispatch("删除第二个患者章三")
    assert result.intent == Intent.delete_patient
    assert result.patient_name == "章三"
    assert result.extra_data.get("occurrence_index") == 2


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


async def test_dispatch_injects_knowledge_context_as_system_message(mock_llm):
    mock_llm.return_value = _make_chat_reply("OK")
    await dispatch("当前消息", history=[{"role": "user", "content": "上一条"}], knowledge_context="【医生知识库】\n1. 胸痛先排除ACS")
    messages = mock_llm.call_args.kwargs["messages"]
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert "医生助手" in messages[0]["content"]
    assert messages[1]["role"] == "system"
    assert "医生知识库" in messages[1]["content"]
    assert messages[2]["content"] == "上一条"
    assert messages[3]["content"] == "当前消息"


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


# ---------------------------------------------------------------------------
# structured_fields and chat_reply (single-LLM path)
# ---------------------------------------------------------------------------


async def test_add_record_populates_structured_fields(mock_llm):
    mock_llm.return_value = _make_tool_call("add_medical_record", {
        "patient_name": "张三",
        "chief_complaint": "头痛两天",
        "diagnosis": "紧张性头痛",
        "treatment_plan": "布洛芬",
        "follow_up_plan": "两周后复查",
    })
    result = await dispatch("张三头痛两天，布洛芬，两周后复查")
    assert result.structured_fields is not None
    assert result.structured_fields["chief_complaint"] == "头痛两天"
    assert result.structured_fields["diagnosis"] == "紧张性头痛"
    assert result.structured_fields["treatment_plan"] == "布洛芬"
    assert result.structured_fields["follow_up_plan"] == "两周后复查"


async def test_add_record_chat_reply_populated(mock_llm):
    mock_llm.return_value = _make_tool_call(
        "add_medical_record",
        {"patient_name": "张三", "chief_complaint": "头痛两天"},
        content="好的，张三头痛两天的情况记下来了。",
    )
    result = await dispatch("张三头痛两天")
    assert result.chat_reply == "好的，张三头痛两天的情况记下来了。"


async def test_non_add_record_has_no_structured_fields(mock_llm):
    mock_llm.return_value = _make_tool_call("create_patient", {"name": "李明"})
    result = await dispatch("新患者李明")
    assert result.structured_fields is None

    mock_llm.return_value = _make_tool_call("query_records", {"patient_name": "王芳"})
    result2 = await dispatch("查一下王芳的病历")
    assert result2.structured_fields is None


async def test_empty_clinical_fields_gives_none_structured_fields(mock_llm):
    """add_medical_record with no clinical keys → structured_fields is None."""
    mock_llm.return_value = _make_tool_call("add_medical_record", {
        "patient_name": "张三",
        "is_emergency": False,
    })
    result = await dispatch("张三发烧")
    assert result.structured_fields is None


async def test_add_record_null_clinical_fields_excluded(mock_llm):
    """null values in clinical fields should not appear in structured_fields."""
    mock_llm.return_value = _make_tool_call("add_medical_record", {
        "patient_name": "李明",
        "chief_complaint": "胸痛",
        "diagnosis": None,
        "treatment_plan": None,
    })
    result = await dispatch("李明胸痛")
    assert result.structured_fields is not None
    assert "diagnosis" not in result.structured_fields
    assert "treatment_plan" not in result.structured_fields
    assert result.structured_fields["chief_complaint"] == "胸痛"


# ---------------------------------------------------------------------------
# Ollama fallback parser coverage
# ---------------------------------------------------------------------------


def test_fallback_extract_name_gender_age_with_clinical_keywords():
    out = agent._fallback_intent_from_text("患者张三男62岁，胸痛两小时，考虑STEMI")
    assert out.intent == Intent.add_record
    assert out.patient_name == "张三"
    assert out.gender == "男"
    assert out.age == 62


def test_fallback_list_patients_branch():
    out = agent._fallback_intent_from_text("请给我所有患者")
    assert out.intent == Intent.list_patients


def test_fallback_delete_patient_branch():
    out = agent._fallback_intent_from_text("删除第二个患者章三")
    assert out.intent == Intent.delete_patient
    assert out.patient_name == "章三"
    assert out.extra_data.get("occurrence_index") == 2


def test_fallback_list_tasks_branch():
    out = agent._fallback_intent_from_text("看一下我的待办任务")
    assert out.intent == Intent.list_tasks


def test_fallback_complete_task_branch():
    out = agent._fallback_intent_from_text("完成 12")
    assert out.intent == Intent.complete_task
    assert out.extra_data.get("task_id") == 12


def test_fallback_query_records_branch():
    out = agent._fallback_intent_from_text("查询王芳历史病历")
    assert out.intent == Intent.query_records
    assert out.patient_name is not None
    assert out.patient_name.startswith("王芳")


def test_fallback_create_patient_branch():
    out = agent._fallback_intent_from_text("新患者 李明 女 43岁")
    assert out.intent == Intent.create_patient
    assert out.patient_name == "李明"
    assert out.gender == "女"
    assert out.age == 43


def test_fallback_greeting_branch():
    out = agent._fallback_intent_from_text("hello")
    assert out.intent == Intent.unknown
    assert out.chat_reply is not None


def test_fallback_unknown_branch_keeps_extracted_demographics():
    out = agent._fallback_intent_from_text("陈明 男 28岁")
    assert out.intent == Intent.unknown
    assert out.patient_name is not None
    assert out.gender == "男"
    assert out.age == 28


async def test_dispatch_ollama_exception_uses_local_fallback(monkeypatch):
    monkeypatch.setenv("ROUTING_LLM", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("timeout"))
    with patch("services.agent.AsyncOpenAI", return_value=mock_client):
        out = await dispatch("张三胸痛两小时")
    assert out.intent == Intent.add_record


async def test_dispatch_strict_mode_blocks_missing_provider_key(monkeypatch):
    monkeypatch.setenv("ROUTING_LLM", "groq")
    monkeypatch.setenv("LLM_PROVIDER_STRICT_MODE", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch("services.agent.AsyncOpenAI") as mock_client_cls:
        with pytest.raises(RuntimeError, match="requires GROQ_API_KEY"):
            await dispatch("张三胸痛两小时")
    mock_client_cls.assert_not_called()


async def test_dispatch_tencent_lkeap_provider_uses_tencent_env(monkeypatch):
    monkeypatch.setenv("ROUTING_LLM", "tencent_lkeap")
    monkeypatch.setenv("TENCENT_LKEAP_BASE_URL", "https://api.lkeap.cloud.tencent.com/v1")
    monkeypatch.setenv("TENCENT_LKEAP_MODEL", "deepseek-v3-1")
    monkeypatch.setenv("TENCENT_LKEAP_API_KEY", "tencent-key")
    monkeypatch.setenv("LLM_PROVIDER_STRICT_MODE", "true")

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_chat_reply("您好，我是医生助手。"))
    with patch("services.agent.AsyncOpenAI", return_value=mock_client) as mock_client_cls:
        result = await dispatch("你好")

    assert result.intent == Intent.unknown
    assert result.chat_reply == "您好，我是医生助手。"
    mock_client_cls.assert_called_once_with(
        base_url="https://api.lkeap.cloud.tencent.com/v1",
        api_key="tencent-key",
        timeout=45.0,
        max_retries=1,
    )
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v3-1"


def test_extract_embedded_tool_call_parses_object_and_args():
    content = '_tool_call_ {"name":"query_records","arguments":{"patient_name":"钱芳"}} </tool_call>'
    fn, args = agent._extract_embedded_tool_call(content)
    assert fn == "query_records"
    assert args == {"patient_name": "钱芳"}


def test_extract_embedded_tool_call_parses_stringified_args():
    content = '{"name":"add_medical_record","arguments":"{\\"patient_name\\":\\"张三\\",\\"chief_complaint\\":\\"胸痛\\"}"}'
    fn, args = agent._extract_embedded_tool_call(content)
    assert fn == "add_medical_record"
    assert args["patient_name"] == "张三"
    assert args["chief_complaint"] == "胸痛"


def test_extract_embedded_tool_call_parses_icall_function_markup():
    content = '_icall_function("add_medical_record", {"patient_name":"林烁","gender":"男","age":68})\n记录下来了'
    fn, args = agent._extract_embedded_tool_call(content)
    assert fn == "add_medical_record"
    assert args["patient_name"] == "林烁"
    assert args["age"] == 68


def test_extract_embedded_tool_call_handles_invalid_payload():
    fn, args = agent._extract_embedded_tool_call("hello world")
    assert fn is None
    assert args == {}


def test_looks_like_tool_markup_variants():
    assert agent._looks_like_tool_markup('_tool_call_ {"name":"x","arguments":{}}')
    assert agent._looks_like_tool_markup('{"name":"x","arguments":{}}')
    assert agent._looks_like_tool_markup('_icall_function("query_records", {"patient_name":"李明"})')
    assert not agent._looks_like_tool_markup("您好，我是医生助手。")


def test_selected_tools_compact_removes_descriptions(monkeypatch):
    monkeypatch.setenv("AGENT_TOOL_SCHEMA_MODE", "compact")
    tools = agent._selected_tools()
    assert isinstance(tools, list)
    first_fn = tools[0]["function"]
    assert "description" not in first_fn


def test_selected_system_prompt_compact(monkeypatch):
    monkeypatch.setenv("AGENT_ROUTING_PROMPT_MODE", "compact")
    prompt = agent._selected_system_prompt()
    assert "根据当前消息选择工具" in prompt


async def test_dispatch_embedded_tool_call_content_is_parsed(mock_llm):
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = '_tool_call_ {"name":"query_records","arguments":{"patient_name":"钱芳"}} </tool_call>'
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    mock_llm.return_value = completion

    result = await dispatch("查询钱芳")
    assert result.intent == Intent.query_records
    assert result.patient_name == "钱芳"
    assert result.chat_reply is None
