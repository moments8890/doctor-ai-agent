"""Engine-driven focus policy — moves state-machine logic from prompt to engine.

Why this exists: patient-intake.md grew to 233 lines / 32 rules trying to
encode "phase 1 / phase 2", priority among rules 11/12/12.1/17a/17b, and
asked-tracker dedup logic. None of that was supported by the engine. The
engine now computes phase1_complete + next_focus_question directly so the
LLM gets a concrete instruction each turn instead of having to interpret
8+ priority rules.

Coverage:
- phase 1 structural completeness (time + characteristic + ≥1 associated)
- 17a danger-screen trigger (head/chest/abdomen) + asked-tracker dedup
- 17b chronic-disease drill-down (糖尿病/高血压/抗凝)
- P2 fallback to required_missing[0] when no triggers fire
- _postprocess_suggestions chip injection (negative + uncertain) + cap-4
"""
from __future__ import annotations

from domain.intake.templates.medical_general import (
    GeneralMedicalExtractor,
    _postprocess_suggestions,
)


# ---- Phase 1 structural completeness ---------------------------------------

def test_phase1_complete_with_time_char_associated():
    extractor = GeneralMedicalExtractor()
    collected = {
        "chief_complaint": "腹痛",
        # has time (3天), characteristic (阵发), associated (恶心)
        "present_illness": "脐周阵发性疼痛3天，伴恶心",
    }
    state = extractor.completeness(collected, mode="patient")
    assert state.phase1_complete is True


def test_phase1_incomplete_without_associated():
    extractor = GeneralMedicalExtractor()
    # Use a CC that does NOT trigger 17a danger-screen (腰痛 is not in
    # the head/chest/abdomen keyword set), so phase 1 logic gets a chance.
    collected = {
        "chief_complaint": "腰痛",
        # has time + characteristic but NO associated symptom keyword
        "present_illness": "腰部阵发性疼痛3天",
    }
    state = extractor.completeness(collected, mode="patient")
    assert state.phase1_complete is False
    assert state.next_focus_question is not None
    # Should ask about associated symptoms
    assert "其他不舒服" in state.next_focus_question or "恶心" in state.next_focus_question


# ---- 17a danger-screen trigger map -----------------------------------------

def test_danger_screen_headache_first_question():
    extractor = GeneralMedicalExtractor()
    collected = {"chief_complaint": "头痛3天"}
    state = extractor.completeness(collected, mode="patient")
    assert state.next_focus_question == "是突然剧烈发作的，还是慢慢加重的？"
    assert "突然剧烈" in state.next_focus_suggestions


def test_danger_screen_skips_asked_questions():
    extractor = GeneralMedicalExtractor()
    collected = {
        "chief_complaint": "头痛3天",
        "_asked_safety_net": [
            "是突然剧烈发作的，还是慢慢加重的？",
            "有没有视物模糊、说话困难、手脚没力气？",
        ],
    }
    state = extractor.completeness(collected, mode="patient")
    # Third question in the head trigger list
    assert state.next_focus_question == "有没有发热？"


def test_danger_screen_skips_when_cc_no_match():
    extractor = GeneralMedicalExtractor()
    collected = {"chief_complaint": "腰扭伤一周"}
    state = extractor.completeness(collected, mode="patient")
    # No head/chest/abdomen keyword → no danger screen.
    # phase1 will still be incomplete (no characteristic in present_illness)
    # so we should fall through to phase 1 prompts, not 17a.
    assert state.next_focus_question is None or "突然剧烈" not in state.next_focus_question
    assert state.next_focus_question is None or "胸" not in state.next_focus_question


def test_danger_screen_chest_pain_triggered():
    extractor = GeneralMedicalExtractor()
    collected = {"chief_complaint": "胸痛", "present_illness": ""}
    state = extractor.completeness(collected, mode="patient")
    # First chest_pain question
    assert state.next_focus_question == "是劳累或情绪激动后出现的吗？"


def test_danger_screen_abdominal_triggered():
    extractor = GeneralMedicalExtractor()
    collected = {"chief_complaint": "肚子疼", "present_illness": ""}
    state = extractor.completeness(collected, mode="patient")
    assert state.next_focus_question == "具体在哪个位置？"


# ---- 17b chronic-disease drill-down ----------------------------------------

def test_chronic_drilldown_diabetes():
    extractor = GeneralMedicalExtractor()
    # Need the danger-screen path to NOT match; use a CC that doesn't
    # trigger 17a. "腰痛" doesn't match any DANGER_KEYWORDS group.
    collected = {
        "chief_complaint": "腰痛",
        "present_illness": "腰部酸痛持续2周",  # phase 1 enough to fall through
        "past_history": "糖尿病",  # short — just-mentioned, not yet drilled
    }
    state = extractor.completeness(collected, mode="patient")
    # Note: phase1 may not be complete (no associated keyword). Drill-down
    # P0b runs BEFORE phase1 P1, so it should fire when past_history is short.
    assert state.next_focus_question == "您现在血糖控制得怎么样？吃什么药？"


def test_chronic_drilldown_skipped_when_already_drilled():
    extractor = GeneralMedicalExtractor()
    collected = {
        "chief_complaint": "腰痛",
        "present_illness": "腰部酸痛持续2周伴恶心",  # phase1 complete (time+char+associated)
        # Long past_history (>30 chars) → already drilled, skip
        "past_history": (
            "糖尿病二十年余，二甲双胍每日两次，最近血糖控制可"
            "，空腹6.5左右，餐后8-9，无明显波动，眼底未查"
        ),
    }
    state = extractor.completeness(collected, mode="patient")
    # Should NOT be the diabetes drill-down question
    assert state.next_focus_question != "您现在血糖控制得怎么样？吃什么药？"


def test_chronic_drilldown_anticoagulant():
    extractor = GeneralMedicalExtractor()
    collected = {
        "chief_complaint": "腰痛",
        "present_illness": "酸痛2周",
        "past_history": "华法林",
    }
    state = extractor.completeness(collected, mode="patient")
    assert state.next_focus_question == "这个药按时吃吗？最近有没有自己停过？"


# ---- P2 fallback to required_missing ---------------------------------------

def test_p2_falls_through_to_required_missing():
    extractor = GeneralMedicalExtractor()
    collected = {
        "chief_complaint": "腰痛",
        "present_illness": "腰部阵发性疼痛3天伴恶心",  # phase1 complete
        # no past_history → 17b skipped
    }
    state = extractor.completeness(collected, mode="patient")
    assert state.phase1_complete is True
    # P2 should fall through to required_missing[0] which is past_history
    assert state.next_focus_question is not None
    assert "既往史" in state.next_focus_question


# ---- doctor mode does not get engine-driven focus --------------------------

def test_doctor_mode_no_engine_focus():
    """Engine-driven focus is patient-mode only. Doctor mode keeps the
    legacy behavior (next_focus = first missing field key, no question)."""
    extractor = GeneralMedicalExtractor()
    collected = {"chief_complaint": "头痛"}
    state = extractor.completeness(collected, mode="doctor")
    assert state.next_focus_question is None
    assert state.next_focus_suggestions == []


# ---- _postprocess_suggestions ----------------------------------------------

def test_postprocess_suggestions_injects_negative():
    """Binary question + suggestions without negative chip → inject 没有."""
    reply = "您有没有发热？"
    suggestions = ["有发热"]
    out = _postprocess_suggestions(reply, suggestions)
    assert "没有" in out


def test_postprocess_suggestions_injects_uncertain():
    """Multi-choice question without uncertain chip → inject 不清楚."""
    reply = "是突然发作的，还是慢慢加重的？"
    suggestions = ["突然", "慢慢"]
    out = _postprocess_suggestions(reply, suggestions)
    assert any("不清楚" in s or "说不准" in s or "说不清" in s for s in out)


def test_postprocess_suggestions_caps_4_and_dedups():
    reply = "请问您的情况？"
    suggestions = ["有", "没有", "有", "不清楚", "其他", "再说", "试试"]
    out = _postprocess_suggestions(reply, suggestions)
    assert len(out) <= 4
    # case-insensitive dedup → "有" appears once
    assert out.count("有") == 1


def test_postprocess_suggestions_truncates_long_chips():
    reply = "请问？"
    # 12-char string should get truncated to 10
    long_chip = "一二三四五六七八九十十一十二"
    out = _postprocess_suggestions(reply, [long_chip])
    assert all(len(s) <= 10 for s in out)


def test_postprocess_suggestions_no_inject_when_already_present():
    """If LLM already provided a negative chip, don't double-inject."""
    reply = "有没有发热？"
    suggestions = ["无", "有发热"]
    out = _postprocess_suggestions(reply, suggestions)
    # Should not inject another "没有" when "无" is already there
    assert out.count("没有") == 0
    assert "无" in out


def test_postprocess_suggestions_skips_when_full():
    """When suggestions are already at 4 entries, don't inject."""
    reply = "有没有发热？"
    suggestions = ["有发热", "高烧", "低烧", "时有时无"]
    out = _postprocess_suggestions(reply, suggestions)
    assert len(out) == 4
    # No room to inject — should keep what LLM gave us
    assert "没有" not in out
