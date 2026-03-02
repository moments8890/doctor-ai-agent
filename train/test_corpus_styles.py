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

from services.intent import Intent
from services.agent import dispatch
from services.structuring import structure_medical_record
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
    with patch("services.agent.AsyncOpenAI", return_value=MagicMock(
        chat=MagicMock(completions=MagicMock(create=mock))
    )):
        yield mock


@pytest.fixture
def mock_struct_llm(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    mock = AsyncMock()
    with patch("services.structuring.AsyncOpenAI", return_value=MagicMock(
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
        "chief_complaint": "胸闷两周，爬楼加重",
        "history_of_present_illness": "活动后胸闷，平路无症状，血压148/88",
        "past_medical_history": "高血压八年，服氨氯地平5mg",
        "physical_examination": "BP 148/88",
        "auxiliary_examinations": None,
        "diagnosis": "高血压；冠心病待排",
        "treatment_plan": None,
        "follow_up_plan": None,
    })
    record = await structure_medical_record(CASE_101)
    assert record.chief_complaint is not None
    assert "胸闷" in record.chief_complaint
    assert record.past_medical_history is not None
    assert "高血压" in record.past_medical_history


# ---------------------------------------------------------------------------
# Case 201 — 口语化听写: instructional prefix stripped, clinical content extracted
# ---------------------------------------------------------------------------
async def test_style_verbal_dictation_prefix_stripped(mock_struct_llm):
    """The 帮我记一下 prefix must not pollute chief_complaint."""
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "心跳不规则，漏跳感，偶有气短，一个月",
        "history_of_present_illness": "频发室早，每分钟10-15个；高血压，缬沙坦80mg，BP 138/86",
        "past_medical_history": "高血压",
        "physical_examination": "BP 138/86，HR 正常",
        "auxiliary_examinations": "心电图：频发室早",
        "diagnosis": "频发室性早搏；高血压",
        "treatment_plan": "安排24小时动态心电图；安排心超；暂观察，不加抗心律失常药",
        "follow_up_plan": None,
    })
    record = await structure_medical_record(CASE_201)
    assert "帮我记" not in (record.chief_complaint or "")
    assert "记一下" not in (record.chief_complaint or "")
    assert record.chief_complaint is not None


# ---------------------------------------------------------------------------
# Case 301 — 碎片化思维流: core info extracted despite self-corrections
# ---------------------------------------------------------------------------
async def test_style_fragmented_stream_extracts_core_fields(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "胸部压迫感，活动后加重，休息缓解",
        "history_of_present_illness": "劳力性胸部不适，爬楼或快走诱发，休息后缓解；高血压；2型糖尿病六年",
        "past_medical_history": "高血压（硝苯地平缓释片）；2型糖尿病（二甲双胍）",
        "physical_examination": "BP 152/92",
        "auxiliary_examinations": "心电图V4V5 ST段轻度压低",
        "diagnosis": "不稳定型心绞痛待排；高血压；2型糖尿病",
        "treatment_plan": "安排冠脉CTA；安排运动平板；加单硝酸异山梨酯",
        "follow_up_plan": None,
    })
    record = await structure_medical_record(CASE_301)
    # Despite self-corrections in input, structural output is clean
    assert record.chief_complaint is not None
    assert record.past_medical_history is not None
    assert "糖尿病" in record.past_medical_history
    # Planned tests go to treatment_plan
    assert record.treatment_plan is not None
    assert "CTA" in record.treatment_plan or "冠脉" in record.treatment_plan
    # Existing results go to auxiliary_examinations
    assert record.auxiliary_examinations is not None
    assert "ST" in record.auxiliary_examinations


# ---------------------------------------------------------------------------
# Case 401 — 重度缩写: specialist abbreviations land in correct fields
# ---------------------------------------------------------------------------
async def test_style_heavy_abbreviation_specialist_terms_placed_correctly(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "STEMI急诊PCI术后第7天出院前评估",
        "history_of_present_illness": "急诊PCI术后，IRA为LAD近段，支架一枚，TIMI 3级血流；cTnI峰值38",
        "past_medical_history": None,
        "physical_examination": None,
        "auxiliary_examinations": "EF术后48%（较入院60%明显下降），心肌顿抑",
        "diagnosis": "急性前壁STEMI，PCI术后；心肌顿抑",
        "treatment_plan": "DAPT：阿司匹林100mg+替格瑞洛90mg bid；阿托伐他汀40mg；培哚普利4mg；美托洛尔缓释片23.75mg；心脏康复；1个月后复查ECG、心超、血脂",
        "follow_up_plan": "1个月后门诊复查ECG、心超、血脂；随访EF恢复情况及DAPT耐受",
    })
    record = await structure_medical_record(CASE_401)
    # EF comparison goes to auxiliary_examinations (existing result with trend)
    assert record.auxiliary_examinations is not None
    assert "EF" in record.auxiliary_examinations
    assert "48" in record.auxiliary_examinations
    # Treatment contains DAPT and medications
    assert record.treatment_plan is not None
    assert "DAPT" in record.treatment_plan or "阿司匹林" in record.treatment_plan


# ---------------------------------------------------------------------------
# Case 503 / 601 — 复诊追踪: trend data (BNP, EF) lands in auxiliary_examinations
# ---------------------------------------------------------------------------
CASE_503_EXCERPT = (
    "严国平，男性，74岁，慢性心衰急性加重三天。BNP 3820 pg/mL（上次门诊348），"
    "Cr 148（上次102）。EF基线值38%。收入CCU，呋塞米40mg iv bid，暂停沙库巴曲缬沙坦。"
    "48小时后复查BNP、肾功、电解质。"
)


async def test_bnp_trend_in_auxiliary_examinations(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "慢性心衰急性加重三天",
        "history_of_present_illness": "气短加重，夜间不能平卧，双下肢水肿加重，尿量减少",
        "past_medical_history": "冠心病缺血性心肌病，慢性心衰五年，PCI术后，高血压，2型糖尿病，CKD 3期",
        "physical_examination": "BP 104/68，HR 102，双肺底湿啰音，双下肢中度凹陷性水肿",
        "auxiliary_examinations": "BNP 3820 pg/mL（上次348，明显升高）；Cr 148（上次102，急性肾损伤）；EF 38%（基线）",
        "diagnosis": "慢性心衰急性加重（NYHA IV级）；急性肾损伤AKI 1期",
        "treatment_plan": "收入CCU；呋塞米40mg iv bid；暂停沙库巴曲缬沙坦；暂停达格列净；48小时复查BNP、肾功",
        "follow_up_plan": "48小时后复查BNP、肾功、电解质",
    })
    record = await structure_medical_record(CASE_503_EXCERPT)
    assert record.auxiliary_examinations is not None
    assert "BNP" in record.auxiliary_examinations
    assert "上次" in record.auxiliary_examinations or "升高" in record.auxiliary_examinations
    # Planned re-check goes to treatment_plan
    assert record.treatment_plan is not None
    assert "复查" in record.treatment_plan


async def test_followup_delta_case_captures_changes(mock_struct_llm):
    """Case 601: Follow-up only records what changed — new LDL result + new medication."""
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "复诊：血压及血脂评估",
        "history_of_present_illness": "上次开氨氯地平后血压132/84达标，胸闷消失",
        "past_medical_history": None,
        "physical_examination": "BP 132/84",
        "auxiliary_examinations": "血脂复查：LDL 2.9（目标<1.8，未达标）",
        "diagnosis": "高血压（控制达标）；高脂血症（未达标）",
        "treatment_plan": "加阿托伐他汀20mg晚服；继续氨氯地平5mg",
        "follow_up_plan": "三个月后复诊",
    })
    record = await structure_medical_record(CASE_601)
    # New test result (LDL) goes to auxiliary_examinations
    assert record.auxiliary_examinations is not None
    assert "LDL" in record.auxiliary_examinations
    # New medication goes to treatment_plan
    assert record.treatment_plan is not None
    assert "阿托伐他汀" in record.treatment_plan


# ---------------------------------------------------------------------------
# Case 701 — 急诊: emergency fields in correct columns
# ---------------------------------------------------------------------------
async def test_emergency_stemi_fields_correctly_placed(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "突发胸痛两小时，持续不缓解，大汗",
        "history_of_present_illness": "突发持续性胸痛，血压90/60，心率110",
        "past_medical_history": None,
        "physical_examination": "BP 90/60，HR 110，大汗",
        "auxiliary_examinations": "心电图：II/III/aVF ST段抬高；cTnI：待回",
        "diagnosis": "急性下壁STEMI；血流动力学不稳定",
        "treatment_plan": "急诊PCI绿色通道；阿司匹林300mg咀嚼；替格瑞洛180mg负荷；肝素静推",
        "follow_up_plan": None,
    })
    record = await structure_medical_record(CASE_701)
    assert record.diagnosis is not None
    assert "STEMI" in record.diagnosis
    assert record.physical_examination is not None
    assert "90/60" in record.physical_examination
    assert record.auxiliary_examinations is not None
    assert "ST" in record.auxiliary_examinations
    assert record.treatment_plan is not None
    assert "PCI" in record.treatment_plan or "阿司匹林" in record.treatment_plan


# ---------------------------------------------------------------------------
# Case 801 — 多病共存: multiple diagnoses captured in diagnosis field
# ---------------------------------------------------------------------------
async def test_multimorbidity_multiple_diagnoses_in_diagnosis_field(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "门诊调药",
        "history_of_present_illness": "血压157/94，控制不满意",
        "past_medical_history": "冠心病支架（LAD+RCA）；持续性房颤；慢性肾功能不全（Cr 168）；2型糖尿病；高血压",
        "physical_examination": "BP 157/94",
        "auxiliary_examinations": "Cr 168，GFR约35；Holter：阵发AF心室率平均74次/分；LDL 1.3（达标）",
        "diagnosis": "高血压（未达标）；冠心病（PCI术后）；持续性房颤；慢性肾功能不全（CKD 3期）；2型糖尿病",
        "treatment_plan": "加氨氯地平5mg；维持利伐沙班15mg qd；维持阿托伐他汀20mg；告知关注蛋白尿，可能转肾内科共管",
        "follow_up_plan": None,
    })
    record = await structure_medical_record(CASE_801)
    assert record.diagnosis is not None
    # Multiple conditions should be present
    diag = record.diagnosis
    assert "高血压" in diag
    assert "冠心病" in diag or "PCI" in diag
    assert "房颤" in diag
    # Existing lab goes to auxiliary_examinations
    assert record.auxiliary_examinations is not None
    assert "Cr" in record.auxiliary_examinations or "LDL" in record.auxiliary_examinations


# ---------------------------------------------------------------------------
# Case 901 — 信息模糊: missing fields return None, not guessed values
# ---------------------------------------------------------------------------
async def test_incomplete_info_missing_fields_are_null(mock_struct_llm):
    """When key info is genuinely absent, LLM must return null, not fabricate."""
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "胸痛（持续时间不详）",
        "history_of_present_illness": "胸痛就诊，病史不详，血压偏高（具体值不详），自行服药（具体不详）",
        "past_medical_history": None,
        "physical_examination": None,
        "auxiliary_examinations": None,
        "diagnosis": None,
        "treatment_plan": "安排心电图；抽血化验；待结果补充",
        "follow_up_plan": None,
    })
    record = await structure_medical_record(CASE_901)
    assert isinstance(record, MedicalRecord)
    # Fields with no data must be None, not invented strings
    assert record.past_medical_history is None
    assert record.physical_examination is None
    assert record.auxiliary_examinations is None
    assert record.diagnosis is None
    # Chief complaint and pending plan should still be populated
    assert record.chief_complaint is not None
    assert record.treatment_plan is not None


# ---------------------------------------------------------------------------
# Case 1001 — AI互动指令: instructional directive stripped, clinical content extracted
# ---------------------------------------------------------------------------
async def test_ai_dialogue_directive_stripped_clinical_content_extracted(mock_struct_llm):
    mock_struct_llm.return_value = _struct_completion({
        "chief_complaint": "血压控制不佳，晨峰高血压",
        "history_of_present_illness": "自测早晨血压160多，下午145，服药后130。氨氯地平在晚上服。",
        "past_medical_history": None,
        "physical_examination": "BP（门诊）未记录；K 3.9，Cr 82（正常）",
        "auxiliary_examinations": "血钾 3.9，Cr 82",
        "diagnosis": "高血压2级；晨峰高血压",
        "treatment_plan": "氨氯地平5mg改为睡前服；加培哚普利4mg晨服；一个月后复诊安排24小时动态血压",
        "follow_up_plan": "一个月后复诊，测24小时动态血压评估谷峰比值",
    })
    record = await structure_medical_record(CASE_1001)
    # Directive prefix must not appear in clinical fields
    assert "给我记" not in (record.chief_complaint or "")
    assert "记一下" not in (record.chief_complaint or "")
    assert record.chief_complaint is not None
    assert record.diagnosis is not None
    assert "高血压" in record.diagnosis
    assert record.treatment_plan is not None
    assert "氨氯地平" in record.treatment_plan
