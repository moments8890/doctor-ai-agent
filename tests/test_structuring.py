"""Tests for services/structuring.py — LLM is mocked.

Verifies that:
- LLM JSON output is correctly parsed into MedicalRecord
- content and tags fields are mapped correctly
- Empty/null content triggers fallback (uses input text)
- Optional tags remain empty list when absent
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
        "content": "头痛两天，持续性头痛，无发热",
        "tags": ["头痛"],
    })
    record = await structure_medical_record("头痛两天")
    assert isinstance(record, MedicalRecord)


# ---------------------------------------------------------------------------
# All fields populated
# ---------------------------------------------------------------------------


async def test_structure_all_8_fields_mapped_correctly(mock_llm):
    mock_llm.return_value = _make_completion({
        "content": "劳力性胸闷一周。一周前开始活动后胸闷，休息可缓解。高血压十二年，服缬沙坦。BP 156/94，HR 78，律齐。心电图V4-V6 ST段压低0.5mm；LDL-C 3.2 mmol/L。不稳定型心绞痛；高血压3级，极高危。阿司匹林100mg qd；阿托伐他汀40mg qn。一个月后复诊，复查血脂。",
        "tags": ["不稳定型心绞痛", "高血压3级", "阿司匹林100mg", "一个月后复诊"],
    })
    record = await structure_medical_record("贺志强，劳力性胸闷一周...")

    assert "劳力性胸闷" in record.content
    assert "高血压" in record.content
    assert "ST" in record.content
    assert "阿司匹林" in record.content
    assert "复诊" in record.content
    assert len(record.tags) > 0


# ---------------------------------------------------------------------------
# Optional fields absent
# ---------------------------------------------------------------------------


async def test_structure_optional_fields_none_when_absent(mock_llm):
    mock_llm.return_value = _make_completion({
        "content": "发烧两天。两天前发热38.5度。",
        "tags": [],
    })
    record = await structure_medical_record("发烧两天")

    assert "发烧" in record.content
    assert record.tags == []


async def test_structure_missing_optional_keys_in_response_default_to_none(mock_llm):
    """LLM omits tags key entirely — should not raise, tags defaults to []."""
    mock_llm.return_value = _make_completion({
        "content": "咳嗽三天。",
    })
    record = await structure_medical_record("咳嗽三天")
    assert record.tags == []


# ---------------------------------------------------------------------------
# null/empty content fallback
# ---------------------------------------------------------------------------


async def test_structure_null_chief_complaint_triggers_fallback(mock_llm):
    mock_llm.return_value = _make_completion({
        "content": None,
        "tags": [],
    })
    record = await structure_medical_record("胸痛发作三小时，血压90/60")
    assert record.content is not None
    assert len(record.content) > 0


async def test_structure_empty_string_chief_complaint_triggers_fallback(mock_llm):
    mock_llm.return_value = _make_completion({
        "content": "",
        "tags": [],
    })
    record = await structure_medical_record("发热39度两天")
    assert record.content is not None
    assert len(record.content) > 0


# ---------------------------------------------------------------------------
# All field values are str or list
# ---------------------------------------------------------------------------


async def test_structure_all_field_values_are_str_or_none(mock_llm):
    mock_llm.return_value = _make_completion({
        "content": "胸痛两小时，急性心肌梗死，阿司匹林300mg。",
        "tags": ["急性心肌梗死", "阿司匹林300mg"],
    })
    record = await structure_medical_record("胸痛两小时")
    for field, val in record.model_dump().items():
        if field in ("tags", "specialty_scores"):
            assert isinstance(val, list)
        else:
            assert val is None or isinstance(val, str), (
                f"Field '{field}' should be str or None, got {type(val)}: {val!r}"
            )


# ---------------------------------------------------------------------------
# Cardiology specialist content
# ---------------------------------------------------------------------------


async def test_structure_stemi_diagnosis_and_treatment(mock_llm):
    mock_llm.return_value = _make_completion({
        "content": "突发胸痛2小时，突发持续性胸骨后压榨性疼痛，大汗，血压90/60。BP 90/60，HR 110，大汗淋漓。心电图：II/III/aVF ST段抬高；cTnI：待回。急性下壁STEMI；血流动力学不稳定。阿司匹林300mg咀嚼；替格瑞洛180mg负荷；急诊PCI绿色通道。",
        "tags": ["急性下壁STEMI", "阿司匹林300mg", "PCI"],
    })
    record = await structure_medical_record(
        "韩伟，男，59，突发胸痛两小时，血压90/60，心电图下壁ST抬高，急诊PCI"
    )
    assert "STEMI" in record.content or "心肌梗死" in record.content
    assert "PCI" in record.content or "阿司匹林" in record.content
    assert "ST" in record.content
    assert "90/60" in record.content


async def test_structure_bnp_trend_lands_in_auxiliary_examinations(mock_llm):
    mock_llm.return_value = _make_completion({
        "content": "慢性心衰急性加重三天。气短加重，夜间不能平卧，双下肢水肿加重。BP 104/68，HR 102，双肺底湿啰音，双下肢中度凹陷性水肿。BNP 3820 pg/mL（上次348，明显升高）；EF 38%；Cr 148（上次102）。慢性心衰急性加重（NYHA IV级）；急性肾损伤AKI 1期。呋塞米40mg iv bid；暂停沙库巴曲缬沙坦。48小时复查BNP、肾功、电解质。",
        "tags": ["慢性心衰", "NYHA IV级", "呋塞米40mg", "48小时复查"],
    })
    record = await structure_medical_record("严国平，慢性心衰急性加重，BNP 3820上次348...")

    assert "BNP" in record.content
    assert "上次" in record.content or "升高" in record.content
    assert "心衰" in record.content
    assert "NYHA" in record.content or "IV" in record.content
    assert "呋塞米" in record.content


async def test_structure_planned_tests_go_to_treatment_plan(mock_llm):
    """Tests ordered this visit should be included in content."""
    mock_llm.return_value = _make_completion({
        "content": "劳力性胸闷一周。活动后胸闷，休息可缓解，心电图轻度异常。BP 148/88。心电图：V4V5轻度ST压低。不稳定型心绞痛待排。安排冠脉CTA；安排运动平板试验；硝酸甘油备用。检查完成后复诊。",
        "tags": ["不稳定型心绞痛待排", "冠脉CTA"],
    })
    record = await structure_medical_record("方建国，胸闷一周，安排冠脉CTA和运动平板")

    assert "CTA" in record.content or "运动" in record.content
    assert "ST" in record.content


# ---------------------------------------------------------------------------
# LLM call parameters
# ---------------------------------------------------------------------------


async def test_structure_uses_temperature_0(mock_llm):
    mock_llm.return_value = _make_completion({"content": "头痛两天。", "tags": []})
    await structure_medical_record("头痛")
    assert mock_llm.call_args.kwargs["temperature"] == 0


async def test_structure_uses_json_response_format(mock_llm):
    mock_llm.return_value = _make_completion({"content": "头痛两天。", "tags": []})
    await structure_medical_record("头痛")
    assert mock_llm.call_args.kwargs["response_format"] == {"type": "json_object"}


async def test_structure_uses_max_tokens_1500(mock_llm):
    mock_llm.return_value = _make_completion({"content": "头痛两天。", "tags": []})
    await structure_medical_record("头痛")
    assert mock_llm.call_args.kwargs["max_tokens"] == 1500


async def test_structure_system_prompt_contains_field_names(mock_llm):
    import services.ai.structuring as struct_mod
    struct_mod._PROMPT_CACHE = None  # force reload
    mock_llm.return_value = _make_completion({"content": "头痛两天。", "tags": []})
    # Patch _get_system_prompt to return the seed prompt (new schema)
    with patch("services.ai.structuring._get_system_prompt", new=AsyncMock(return_value=struct_mod._SEED_PROMPT)):
        await structure_medical_record("头痛")
    messages = mock_llm.call_args.kwargs["messages"]
    system_content = messages[0]["content"]
    assert messages[0]["role"] == "system"
    # New schema: seed prompt mentions content and tags fields
    assert "content" in system_content, f"System prompt should mention content field"
    assert "tags" in system_content, f"System prompt should mention tags field"


async def test_structure_user_message_is_input_text(mock_llm):
    mock_llm.return_value = _make_completion({"content": "这是具体的输入文本。", "tags": []})
    await structure_medical_record("这是具体的输入文本")
    messages = mock_llm.call_args.kwargs["messages"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "这是具体的输入文本"


async def test_structure_consultation_mode_appends_suffix(mock_llm):
    """consultation_mode=True appends _CONSULTATION_SUFFIX to the system prompt."""
    from services.ai.structuring import _CONSULTATION_SUFFIX
    mock_llm.return_value = _make_completion({"content": "胸痛问诊记录。", "tags": []})
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
    mock_llm.return_value = _make_completion({"content": "头晕。", "tags": []})
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
        return_value=_make_completion({"content": "头痛两天。", "tags": []})
    )
    with patch("services.ai.structuring.AsyncOpenAI", return_value=mock_client) as mock_client_cls:
        record = await structure_medical_record("头痛两天")

    assert "头痛" in record.content
    mock_client_cls.assert_called_once_with(
        base_url="https://api.lkeap.cloud.tencent.com/v1",
        api_key="tencent-key",
        timeout=30.0,
        max_retries=0,
        default_headers={},
    )
    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v3-1"
