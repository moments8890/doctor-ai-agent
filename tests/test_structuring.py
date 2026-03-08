"""Tests for services/structuring.py — LLM is mocked.

Verifies that:
- LLM JSON output is correctly parsed into MedicalRecord
- All 8 fields are mapped to the right Pydantic attributes
- Null chief_complaint triggers the hard fallback
- Optional fields remain None when absent
- Specialist content (cardiology vitals, oncology trends) lands in the right fields
- LLM is called with correct parameters (temperature=0, json mode, max_tokens=1500)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.ai.structuring import structure_medical_record
from models.medical_record import MedicalRecord


def _make_completion(json_dict: dict):
    msg = MagicMock()
    msg.content = json.dumps(json_dict, ensure_ascii=False)
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
    with patch("services.ai.structuring.AsyncOpenAI", return_value=mock_client):
        yield mock_create


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


async def test_structure_returns_medical_record_instance(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": "头痛两天",
        "history_of_present_illness": "持续性头痛两天，无发热",
    })
    record = await structure_medical_record("头痛两天")
    assert isinstance(record, MedicalRecord)


# ---------------------------------------------------------------------------
# All 8 fields populated
# ---------------------------------------------------------------------------


async def test_structure_all_8_fields_mapped_correctly(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": "劳力性胸闷一周",
        "history_of_present_illness": "一周前开始活动后胸闷，休息可缓解",
        "past_medical_history": "高血压十二年，服缬沙坦",
        "physical_examination": "BP 156/94，HR 78，律齐",
        "auxiliary_examinations": "心电图V4-V6 ST段压低0.5mm；LDL-C 3.2 mmol/L",
        "diagnosis": "不稳定型心绞痛；高血压3级，极高危",
        "treatment_plan": "阿司匹林100mg qd；阿托伐他汀40mg qn",
        "follow_up_plan": "一个月后复诊，复查血脂",
    })
    record = await structure_medical_record("贺志强，劳力性胸闷一周...")

    assert record.chief_complaint == "劳力性胸闷一周"
    assert "一周前" in record.history_of_present_illness
    assert record.past_medical_history == "高血压十二年，服缬沙坦"
    assert record.physical_examination == "BP 156/94，HR 78，律齐"
    assert "ST" in record.auxiliary_examinations
    assert record.diagnosis == "不稳定型心绞痛；高血压3级，极高危"
    assert "阿司匹林" in record.treatment_plan
    assert record.follow_up_plan == "一个月后复诊，复查血脂"


# ---------------------------------------------------------------------------
# Optional fields absent
# ---------------------------------------------------------------------------


async def test_structure_optional_fields_none_when_absent(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": "发烧两天",
        "history_of_present_illness": "两天前发热38.5度",
        "diagnosis": None,
        "treatment_plan": None,
        "past_medical_history": None,
        "physical_examination": None,
        "auxiliary_examinations": None,
        "follow_up_plan": None,
    })
    record = await structure_medical_record("发烧两天")

    assert record.chief_complaint == "发烧两天"
    assert record.diagnosis is None
    assert record.treatment_plan is None
    assert record.past_medical_history is None
    assert record.physical_examination is None
    assert record.auxiliary_examinations is None
    assert record.follow_up_plan is None


async def test_structure_missing_optional_keys_in_response_default_to_none(mock_llm):
    """LLM omits optional keys entirely — should not raise, fields default to None."""
    mock_llm.return_value = _make_completion({
        "chief_complaint": "咳嗽",
        "history_of_present_illness": "三天咳嗽",
    })
    record = await structure_medical_record("咳嗽三天")
    assert record.past_medical_history is None
    assert record.follow_up_plan is None


# ---------------------------------------------------------------------------
# chief_complaint null fallback
# ---------------------------------------------------------------------------


async def test_structure_null_chief_complaint_triggers_fallback(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": None,
        "history_of_present_illness": "患者胸痛发作",
    })
    record = await structure_medical_record("胸痛发作三小时，血压90/60")
    assert record.chief_complaint is not None
    assert len(record.chief_complaint) > 0


async def test_structure_empty_string_chief_complaint_triggers_fallback(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": "",
        "history_of_present_illness": "高烧不退",
    })
    record = await structure_medical_record("发热39度两天")
    assert record.chief_complaint is not None
    assert len(record.chief_complaint) > 0


# ---------------------------------------------------------------------------
# All field values are str or None
# ---------------------------------------------------------------------------


async def test_structure_all_field_values_are_str_or_none(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": "胸痛",
        "history_of_present_illness": "两小时胸痛",
        "diagnosis": "急性心肌梗死",
        "treatment_plan": "阿司匹林300mg",
        "past_medical_history": None,
        "physical_examination": None,
        "auxiliary_examinations": None,
        "follow_up_plan": None,
    })
    record = await structure_medical_record("胸痛两小时")
    for field, val in record.model_dump().items():
        assert val is None or isinstance(val, str), (
            f"Field '{field}' should be str or None, got {type(val)}: {val!r}"
        )


# ---------------------------------------------------------------------------
# Cardiology specialist content
# ---------------------------------------------------------------------------


async def test_structure_stemi_diagnosis_and_treatment(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": "突发胸痛2小时",
        "history_of_present_illness": "突发持续性胸骨后压榨性疼痛，大汗，血压90/60",
        "past_medical_history": None,
        "physical_examination": "BP 90/60，HR 110，大汗淋漓",
        "auxiliary_examinations": "心电图：II/III/aVF ST段抬高；cTnI：待回",
        "diagnosis": "急性下壁STEMI；血流动力学不稳定",
        "treatment_plan": "阿司匹林300mg咀嚼；替格瑞洛180mg负荷；急诊PCI绿色通道",
        "follow_up_plan": None,
    })
    record = await structure_medical_record(
        "韩伟，男，59，突发胸痛两小时，血压90/60，心电图下壁ST抬高，急诊PCI"
    )
    assert "STEMI" in record.diagnosis or "心肌梗死" in record.diagnosis
    assert "PCI" in record.treatment_plan or "阿司匹林" in record.treatment_plan
    assert "ST" in record.auxiliary_examinations
    assert "90/60" in record.physical_examination


async def test_structure_bnp_trend_lands_in_auxiliary_examinations(mock_llm):
    mock_llm.return_value = _make_completion({
        "chief_complaint": "慢性心衰急性加重三天",
        "history_of_present_illness": "气短加重，夜间不能平卧，双下肢水肿加重，近一周进食腌制食品较多",
        "past_medical_history": "冠心病十年，慢性心衰五年，PCI术后三年",
        "physical_examination": "BP 104/68，HR 102，双肺底湿啰音，双下肢中度凹陷性水肿",
        "auxiliary_examinations": "BNP 3820 pg/mL（上次348，明显升高）；EF 38%；Cr 148（上次102）",
        "diagnosis": "慢性心衰急性加重（NYHA IV级）；急性肾损伤AKI 1期",
        "treatment_plan": "呋塞米40mg iv bid；暂停沙库巴曲缬沙坦",
        "follow_up_plan": "48小时复查BNP、肾功、电解质",
    })
    record = await structure_medical_record("严国平，慢性心衰急性加重，BNP 3820上次348...")

    assert record.auxiliary_examinations is not None
    assert "BNP" in record.auxiliary_examinations
    assert "上次" in record.auxiliary_examinations or "升高" in record.auxiliary_examinations
    assert "心衰" in record.diagnosis
    assert "NYHA" in record.diagnosis or "IV" in record.diagnosis
    assert "呋塞米" in record.treatment_plan


async def test_structure_planned_tests_go_to_treatment_plan(mock_llm):
    """Tests ordered this visit go to treatment_plan, not auxiliary_examinations."""
    mock_llm.return_value = _make_completion({
        "chief_complaint": "劳力性胸闷一周",
        "history_of_present_illness": "活动后胸闷，休息可缓解，心电图轻度异常",
        "past_medical_history": "高血压八年",
        "physical_examination": "BP 148/88",
        "auxiliary_examinations": "心电图：V4V5轻度ST压低",
        "diagnosis": "不稳定型心绞痛待排",
        "treatment_plan": "安排冠脉CTA；安排运动平板试验；硝酸甘油备用",
        "follow_up_plan": "检查完成后复诊",
    })
    record = await structure_medical_record("方建国，胸闷一周，安排冠脉CTA和运动平板")

    assert "CTA" in record.treatment_plan or "运动" in record.treatment_plan
    assert record.auxiliary_examinations is not None
    assert "ST" in record.auxiliary_examinations


# ---------------------------------------------------------------------------
# LLM call parameters
# ---------------------------------------------------------------------------


async def test_structure_uses_temperature_0(mock_llm):
    mock_llm.return_value = _make_completion({"chief_complaint": "头痛", "history_of_present_illness": "两天"})
    await structure_medical_record("头痛")
    assert mock_llm.call_args.kwargs["temperature"] == 0


async def test_structure_uses_json_response_format(mock_llm):
    mock_llm.return_value = _make_completion({"chief_complaint": "头痛", "history_of_present_illness": "两天"})
    await structure_medical_record("头痛")
    assert mock_llm.call_args.kwargs["response_format"] == {"type": "json_object"}


async def test_structure_uses_max_tokens_1500(mock_llm):
    mock_llm.return_value = _make_completion({"chief_complaint": "头痛", "history_of_present_illness": "两天"})
    await structure_medical_record("头痛")
    assert mock_llm.call_args.kwargs["max_tokens"] == 1500


async def test_structure_system_prompt_contains_field_names(mock_llm):
    mock_llm.return_value = _make_completion({"chief_complaint": "头痛", "history_of_present_illness": "两天"})
    await structure_medical_record("头痛")
    messages = mock_llm.call_args.kwargs["messages"]
    system_content = messages[0]["content"]
    assert messages[0]["role"] == "system"
    for field in ["主诉", "现病史", "诊断", "治疗方案"]:
        assert field in system_content, f"System prompt missing field: {field}"


async def test_structure_user_message_is_input_text(mock_llm):
    mock_llm.return_value = _make_completion({"chief_complaint": "头痛", "history_of_present_illness": "两天"})
    await structure_medical_record("这是具体的输入文本")
    messages = mock_llm.call_args.kwargs["messages"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "这是具体的输入文本"


async def test_structure_consultation_mode_appends_suffix(mock_llm):
    """consultation_mode=True appends _CONSULTATION_SUFFIX to the system prompt."""
    from services.ai.structuring import _CONSULTATION_SUFFIX
    mock_llm.return_value = _make_completion({"chief_complaint": "胸痛", "history_of_present_illness": "问诊中"})
    await structure_medical_record("医患对话转写", consultation_mode=True)
    messages = mock_llm.call_args.kwargs["messages"]
    system_content = messages[0]["content"]
    assert _CONSULTATION_SUFFIX.strip() in system_content


async def test_get_system_prompt_logs_when_db_load_fails():
    import services.ai.structuring as struct_mod

    struct_mod._PROMPT_CACHE = None
    with patch("db.engine.AsyncSessionLocal", side_effect=RuntimeError("db down")), \
         patch("services.ai.structuring.log") as log_mock:
        prompt = await struct_mod._get_system_prompt()

    assert isinstance(prompt, str) and prompt
    assert "严禁虚构" in prompt
    assert log_mock.called


async def test_structure_consultation_mode_false_no_suffix(mock_llm):
    """consultation_mode=False (default) does NOT append _CONSULTATION_SUFFIX."""
    from services.ai.structuring import _CONSULTATION_SUFFIX
    mock_llm.return_value = _make_completion({"chief_complaint": "头晕"})
    await structure_medical_record("普通口述", consultation_mode=False)
    messages = mock_llm.call_args.kwargs["messages"]
    system_content = messages[0]["content"]
    assert "【问诊对话模式】" not in system_content


async def test_structure_strict_mode_blocks_missing_provider_key(monkeypatch):
    monkeypatch.setenv("STRUCTURING_LLM", "groq")
    monkeypatch.setenv("LLM_PROVIDER_STRICT_MODE", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with patch("services.ai.structuring.AsyncOpenAI") as mock_client_cls:
        with pytest.raises(RuntimeError, match="requires GROQ_API_KEY"):
            await structure_medical_record("头痛")
    mock_client_cls.assert_not_called()


async def test_structure_tencent_lkeap_provider_uses_tencent_env(monkeypatch):
    monkeypatch.setenv("STRUCTURING_LLM", "tencent_lkeap")
    monkeypatch.setenv("TENCENT_LKEAP_BASE_URL", "https://api.lkeap.cloud.tencent.com/v1")
    monkeypatch.setenv("TENCENT_LKEAP_MODEL", "deepseek-v3-1")
    monkeypatch.setenv("TENCENT_LKEAP_API_KEY", "tencent-key")
    monkeypatch.setenv("LLM_PROVIDER_STRICT_MODE", "true")

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_completion({"chief_complaint": "头痛", "history_of_present_illness": "两天"})
    )
    with patch("services.ai.structuring.AsyncOpenAI", return_value=mock_client) as mock_client_cls:
        record = await structure_medical_record("头痛两天")

    assert record.chief_complaint == "头痛"
    mock_client_cls.assert_called_once_with(
        base_url="https://api.lkeap.cloud.tencent.com/v1",
        api_key="tencent-key",
        timeout=30.0,
        max_retries=0,
        default_headers={},
    )
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v3-1"
