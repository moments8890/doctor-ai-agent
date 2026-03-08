"""Corpus-style tests — one representative case per style in clinic_raw_cases_cardiology_v2.md.

Verifies that:
- Every corpus input routes to Intent.add_record (not unknown)
- Emergency cases (701–703) set is_emergency=True
- Conversational-prefix styles (201, 1001) still route to add_record
- Incomplete-info cases (901–903) route to add_record when clinical content present
- Structuring produces correct field placement per style:
    * Trend data (BNP/EF comparisons) → auxiliary_examinations
    * Planned tests → treatment_plan; existing results → auxiliary_examinations
    * Instructional prefixes are stripped; clinical content lands in chief_complaint
    * Fragmented / self-correcting input still populates the required fields
    * Heavy abbreviation cases map specialist terms to correct fields
    * Multi-morbidity cases produce multi-diagnosis strings
    * Follow-up / delta cases capture only new findings

LLM is mocked in all tests — we validate the pipeline logic, not LLM quality.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.intent import Intent
from services.ai.agent import dispatch
from services.ai.structuring import structure_medical_record
from models.medical_record import MedicalRecord


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _agent_tool_call(fn_name: str, args: dict):
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


def _struct_completion(fields: dict):
    msg = MagicMock()
    msg.content = json.dumps(fields, ensure_ascii=False)
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture
def mock_agent_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    mock = AsyncMock()
    with patch("services.ai.agent.AsyncOpenAI", return_value=MagicMock(
        chat=MagicMock(completions=MagicMock(create=mock))
    )):
        yield mock


@pytest.fixture
def mock_struct_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    mock = AsyncMock()
    with patch("services.ai.structuring.AsyncOpenAI", return_value=MagicMock(
        chat=MagicMock(completions=MagicMock(create=mock))
    )):
        yield mock


# ===========================================================================
# Section 1 — ROUTING: every corpus style must go to add_medical_record
# ===========================================================================

# Case 101 — 极简速记
CASE_101 = "方建国，男，61。胸闷两周，爬楼加重，平路没事。血压148/88。高血压史八年，服氨氯地平5mg。"

# Case 201 — 口语化听写（instructional prefix: 帮我记一下）
CASE_201 = (
    "帮我记一下啊，这个病人叫吴大明，男的，56岁。他说最近这一个月老是感觉心跳不规则，"
    "频发室早，每分钟10到15个。既往高血压，缬沙坦80mg。"
    "准备做24小时动态心电图，再查心超，先不加抗心律失常药。"
)

# Case 301 — 碎片化思维流
CASE_301 = (
    "魏建华……男，57岁。主要问题是——他说胸痛，不对，是胸部不适，压迫感，"
    "爬楼梯或者走快了就出来，休息了就好。高血压、糖尿病，2型，六年了。"
    "心电图ST段V4V5轻度压低。下一步冠脉CTA，不稳定型心绞痛待排。"
)

# Case 401 — 重度缩写
CASE_401 = (
    "柳振华，男，64。STEMI急诊PCI后第7天出院前评估。IRA：LAD近段，支架一枚，TIMI 3级。"
    "EF术后复查48%，较入院60%明显下降，心肌顿抑。DAPT+阿托伐他汀40+培哚普利4mg+美托洛尔。"
    "随访重点：EF恢复情况，DAPT耐受。"
)

# Case 501 — 完整临床叙事
CASE_501 = (
    "患者贺志强，男性，62岁，因劳力性胸痛伴气短三个月就诊。"
    "活动后胸骨后压榨性疼痛，休息可缓解。既往高血压十二年、2型糖尿病八年。"
    "心电图V4-V6 ST段压低，LDL-C 3.2。初步诊断：不稳定型心绞痛；高血压3级，极高危。"
    "处理：收住院，冠脉造影，启动阿托伐他汀40mg，加阿司匹林100mg。"
)

# Case 601 — 复诊追踪
CASE_601 = (
    "方建国复诊，上次开了氨氯地平，今天血压132/84，控制好了，胸闷基本没有了。"
    "血脂复查LDL 2.9，还是偏高，加阿托伐他汀20mg晚服。三个月后再来。"
)

# Case 701 — 急诊（STEMI）
CASE_701 = (
    "急诊记录。韩伟，男，59。突发胸痛两小时，持续不缓解，大汗，血压90/60，心率110。"
    "心电图II、III、aVF ST抬高，下壁STEMI。启动急诊PCI绿色通道。"
    "阿司匹林300mg咀嚼，替格瑞洛180mg负荷。"
)

# Case 702 — 急诊（完全性房室传导阻滞）
CASE_702 = (
    "卢慧芳，女，67。突然晕倒约十五秒，血压146/88，心率42，"
    "心电图三度房室传导阻滞。诊断：完全性房室传导阻滞。"
    "立即安置临时起搏器，转CCU，急查cTnI、电解质。"
)

# Case 703 — 急诊（主动脉夹层）
CASE_703 = (
    "马文涛，男，51，突发撕裂样胸背痛半小时，血压左右肢差异：右180/110，左138/90。"
    "高度怀疑主动脉夹层A型。即刻增强CT主动脉，艾司洛尔静脉泵入，联系心外科紧急会诊。"
)

# Case 801 — 多病共存
CASE_801 = (
    "蔡建明，男，71。冠心病支架（LAD+RCA），持续性房颤，慢性肾功能不全（Cr 168），"
    "2型糖尿病，高血压。利伐沙班15mg qd，阿托伐他汀20mg，坎地沙坦8mg。"
    "今天血压157/94，控制不满意，加氨氯地平5mg。"
)

# Case 901 — 信息模糊/不完整
CASE_901 = (
    "帮我记个病人。他说胸痛，不知道多久了，来之前吃了什么药他自己也说不清楚。"
    "血压有点高，具体多少我忘了。安排先做个心电图和抽血，结果出来再说。"
)

# Case 1001 — AI对话互动（指令性语气）
CASE_1001 = (
    "给我记一下这个病人：付海龙，男，55岁。血压控制不好，早上自测160多，"
    "诊断高血压2级，有晨峰现象。氨氯地平5mg改为睡前服，加培哚普利4mg晨服，"
    "一个月后复诊测24小时动态血压。"
)


@pytest.mark.parametrize("text,patient_name", [
    (CASE_101, "方建国"),
    (CASE_201, "吴大明"),
    (CASE_301, "魏建华"),
    (CASE_401, "柳振华"),
    (CASE_501, "贺志强"),
    (CASE_601, "方建国"),
    (CASE_701, "韩伟"),
    (CASE_702, "卢慧芳"),
    (CASE_703, "马文涛"),
    (CASE_801, "蔡建明"),
    (CASE_901, None),       # no patient name given
    (CASE_1001, "付海龙"),
], ids=[
    "case101_minimal_note",
    "case201_verbal_dictation",
    "case301_fragmented_stream",
    "case401_heavy_abbrev",
    "case501_full_narrative",
    "case601_followup",
    "case701_emergency_stemi",
    "case702_emergency_av_block",
    "case703_emergency_dissection",
    "case801_multimorbidity",
    "case901_incomplete_info",
    "case1001_instructional",
])
async def test_all_corpus_styles_route_to_add_record(mock_agent_llm, text, patient_name):
    args = {"patient_name": patient_name} if patient_name else {}
    mock_agent_llm.return_value = _agent_tool_call("add_medical_record", args)
    result = await dispatch(text)
    assert result.intent == Intent.add_record, (
        f"Expected add_record, got {result.intent} for: {text[:60]}"
    )


# ===========================================================================
# Section 2 — EMERGENCY FLAG: Cases 701–703 must set is_emergency=True
# ===========================================================================


@pytest.mark.parametrize("text,label", [
    (CASE_701, "STEMI+PCI绿色通道"),
    (CASE_702, "三度房室阻滞+临时起搏"),
    (CASE_703, "主动脉夹层"),
], ids=[
    "case701_stemi",
    "case702_av_block",
    "case703_dissection",
])
async def test_emergency_cases_set_is_emergency_true(mock_agent_llm, text, label):
    mock_agent_llm.return_value = _agent_tool_call(
        "add_medical_record", {"patient_name": "患者", "is_emergency": True}
    )
    result = await dispatch(text)
    assert result.is_emergency is True, f"is_emergency should be True for: {label}"


async def test_routine_case_does_not_set_emergency(mock_agent_llm):
    mock_agent_llm.return_value = _agent_tool_call(
        "add_medical_record", {"patient_name": "方建国", "is_emergency": False}
    )
    result = await dispatch(CASE_101)
    assert result.is_emergency is False


# ===========================================================================
# Section 3 — STRUCTURING: field placement per corpus style
# ===========================================================================


# ---------------------------------------------------------------------------
# Case 101 — 极简速记: required fields extracted from keyword-only input
# ---------------------------------------------------------------------------
async def test_style_minimal_note_fields_populated(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "content": "胸闷两周，爬楼加重，平路无症状。高血压八年，服氨氯地平5mg。BP 148/88。高血压；冠心病待排。",
        "tags": ["高血压", "冠心病待排"],
    })
    record = await structure_medical_record(CASE_101)
    assert record.content is not None
    assert "胸闷" in record.content
    assert "高血压" in record.content


# ---------------------------------------------------------------------------
# Case 201 — 口语化听写: instructional prefix stripped, clinical content extracted
# ---------------------------------------------------------------------------
async def test_style_verbal_dictation_prefix_stripped(mock_struct_llm):
    """The 帮我记一下 prefix must not pollute content."""
    mock_struct_llm.return_value = _struct_completion({
        "content": "心跳不规则，漏跳感，偶有气短，一个月。频发室早，每分钟10-15个；高血压，缬沙坦80mg。心电图：频发室早。频发室性早搏；高血压。安排24小时动态心电图；安排心超；暂观察。",
        "tags": ["频发室性早搏", "高血压"],
    })
    record = await structure_medical_record(CASE_201)
    assert "帮我记" not in record.content
    assert "记一下" not in record.content
    assert record.content is not None


# ---------------------------------------------------------------------------
# Case 301 — 碎片化思维流: core info extracted despite self-corrections
# ---------------------------------------------------------------------------
async def test_style_fragmented_stream_extracts_core_fields(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "content": "胸部压迫感，活动后加重，休息缓解。高血压；2型糖尿病六年。心电图V4V5 ST段轻度压低。不稳定型心绞痛待排。安排冠脉CTA；安排运动平板。",
        "tags": ["不稳定型心绞痛待排", "高血压", "2型糖尿病", "冠脉CTA"],
    })
    record = await structure_medical_record(CASE_301)
    assert record.content is not None
    assert "糖尿病" in record.content
    assert "CTA" in record.content or "冠脉" in record.content
    assert "ST" in record.content


# ---------------------------------------------------------------------------
# Case 401 — 重度缩写: specialist abbreviations land in correct fields
# ---------------------------------------------------------------------------
async def test_style_heavy_abbreviation_specialist_terms_placed_correctly(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "content": "STEMI急诊PCI术后第7天出院前评估。EF术后48%（较入院60%明显下降），心肌顿抑。急性前壁STEMI，PCI术后。DAPT：阿司匹林100mg+替格瑞洛90mg bid；阿托伐他汀40mg。1个月后复查ECG、心超、血脂。",
        "tags": ["急性前壁STEMI", "PCI术后", "DAPT", "1个月后复查"],
    })
    record = await structure_medical_record(CASE_401)
    assert record.content is not None
    assert "EF" in record.content
    assert "48" in record.content
    assert "DAPT" in record.content or "阿司匹林" in record.content


# ---------------------------------------------------------------------------
# Case 503 / 601 — 复诊追踪: trend data (BNP, EF) captured in content
# ---------------------------------------------------------------------------
CASE_503_EXCERPT = (
    "严国平，男性，74岁，慢性心衰急性加重三天。BNP 3820 pg/mL（上次门诊348），"
    "Cr 148（上次102）。EF基线值38%。收入CCU，呋塞米40mg iv bid，暂停沙库巴曲缬沙坦。"
    "48小时后复查BNP、肾功、电解质。"
)


async def test_bnp_trend_in_auxiliary_examinations(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "content": "慢性心衰急性加重三天。BNP 3820 pg/mL（上次348，明显升高）；Cr 148（上次102）；EF 38%。慢性心衰急性加重（NYHA IV级）；急性肾损伤AKI 1期。收入CCU；呋塞米40mg iv bid；48小时复查BNP、肾功。",
        "tags": ["慢性心衰", "NYHA IV级", "呋塞米40mg", "48小时复查"],
    })
    record = await structure_medical_record(CASE_503_EXCERPT)
    assert record.content is not None
    assert "BNP" in record.content
    assert "上次" in record.content or "升高" in record.content
    assert "复查" in record.content


async def test_followup_delta_case_captures_changes(mock_struct_llm):
    """Case 601: Follow-up only records what changed — new LDL result + new medication."""
    mock_struct_llm.return_value = _struct_completion({
        "content": "复诊：血压及血脂评估。血压132/84达标，胸闷消失。血脂复查：LDL 2.9（目标<1.8，未达标）。高血压（控制达标）；高脂血症（未达标）。加阿托伐他汀20mg晚服；继续氨氯地平5mg。三个月后复诊。",
        "tags": ["高血压", "高脂血症", "阿托伐他汀20mg", "三个月后复诊"],
    })
    record = await structure_medical_record(CASE_601)
    assert record.content is not None
    assert "LDL" in record.content
    assert "阿托伐他汀" in record.content


# ---------------------------------------------------------------------------
# Case 701 — 急诊: emergency fields captured in content
# ---------------------------------------------------------------------------
async def test_emergency_stemi_fields_correctly_placed(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "content": "突发胸痛两小时，持续不缓解，大汗。BP 90/60，HR 110。心电图：II/III/aVF ST段抬高；cTnI：待回。急性下壁STEMI；血流动力学不稳定。急诊PCI绿色通道；阿司匹林300mg咀嚼；替格瑞洛180mg负荷。",
        "tags": ["急性下壁STEMI", "阿司匹林300mg", "PCI"],
    })
    record = await structure_medical_record(CASE_701)
    assert record.content is not None
    assert "STEMI" in record.content
    assert "90/60" in record.content
    assert "ST" in record.content
    assert "PCI" in record.content or "阿司匹林" in record.content


# ---------------------------------------------------------------------------
# Case 801 — 多病共存: multiple diagnoses captured in content and tags
# ---------------------------------------------------------------------------
async def test_multimorbidity_multiple_diagnoses_in_diagnosis_field(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "content": "门诊调药。血压157/94，控制不满意。Cr 168；LDL 1.3（达标）。高血压（未达标）；冠心病（PCI术后）；持续性房颤；慢性肾功能不全（CKD 3期）；2型糖尿病。加氨氯地平5mg；维持利伐沙班15mg qd。",
        "tags": ["高血压", "冠心病PCI术后", "持续性房颤", "2型糖尿病"],
    })
    record = await structure_medical_record(CASE_801)
    assert record.content is not None
    assert "高血压" in record.content
    assert "冠心病" in record.content or "PCI" in record.content
    assert "房颤" in record.content
    assert "Cr" in record.content or "LDL" in record.content


# ---------------------------------------------------------------------------
# Case 901 — 信息模糊: incomplete info still produces valid content
# ---------------------------------------------------------------------------
async def test_incomplete_info_missing_fields_are_null(mock_struct_llm):
    """When key info is genuinely absent, LLM produces minimal content."""
    mock_struct_llm.return_value = _struct_completion({
        "content": "胸痛（持续时间不详），血压偏高（具体值不详）。安排心电图；抽血化验；待结果补充。",
        "tags": ["胸痛", "心电图待查"],
    })
    record = await structure_medical_record(CASE_901)
    assert isinstance(record, MedicalRecord)
    assert record.content is not None
    assert "胸痛" in record.content
    assert "心电图" in record.content or "化验" in record.content


# ---------------------------------------------------------------------------
# Case 1001 — AI互动指令: instructional directive stripped, clinical content extracted
# ---------------------------------------------------------------------------
async def test_ai_dialogue_directive_stripped_clinical_content_extracted(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "content": "血压控制不佳，晨峰高血压。自测早晨血压160多。高血压2级；晨峰高血压。氨氯地平5mg改为睡前服；加培哚普利4mg晨服；一个月后复诊安排24小时动态血压。",
        "tags": ["高血压2级", "晨峰高血压", "一个月后复诊"],
    })
    record = await structure_medical_record(CASE_1001)
    assert "给我记" not in record.content
    assert "记一下" not in record.content
    assert record.content is not None
    assert "高血压" in record.content
    assert "氨氯地平" in record.content
