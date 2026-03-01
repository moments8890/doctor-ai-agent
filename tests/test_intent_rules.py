"""Tests for services/intent_rules.py — no mocking, pure logic."""
from services.intent_rules import detect_intent_rules, _extract_age, _extract_gender, _extract_name, _extract_cv_metrics
from services.intent import Intent


# ---------------------------------------------------------------------------
# Intent routing
# ---------------------------------------------------------------------------


def test_create_patient_explicit_keyword():
    r = detect_intent_rules("帮我建个新患者，李明，45岁男性")
    assert r.intent == Intent.create_patient


def test_create_patient_jiandang():
    r = detect_intent_rules("给张三建档，30岁女性")
    assert r.intent == Intent.create_patient


def test_query_records_chaxun():
    r = detect_intent_rules("查询一下李明的病历")
    assert r.intent == Intent.query_records


def test_query_records_lishi():
    r = detect_intent_rules("看看王芳的历史记录")
    assert r.intent == Intent.query_records


def test_add_record_zhenduan():
    r = detect_intent_rules("患者头痛两天，诊断紧张性头痛，布洛芬治疗")
    assert r.intent == Intent.add_record


def test_add_record_medical_keywords():
    r = detect_intent_rules("王芳今天咳嗽三天，低烧37.5°，诊断上呼吸道感染，给予连花清瘟胶囊")
    assert r.intent == Intent.add_record


def test_unknown_for_unrelated_text():
    r = detect_intent_rules("今天天气真好")
    assert r.intent == Intent.unknown


def test_create_takes_priority_over_add_record():
    # Contains both create keyword and medical keywords
    r = detect_intent_rules("新患者陈强，既往有高血压")
    assert r.intent == Intent.create_patient


# ---------------------------------------------------------------------------
# Age extraction
# ---------------------------------------------------------------------------


def test_extract_age_basic():
    assert _extract_age("李明45岁") == 45


def test_extract_age_with_space():
    assert _extract_age("患者 30 岁") == 30


def test_extract_age_not_present():
    assert _extract_age("患者头痛") is None


def test_extract_age_in_full_sentence():
    assert _extract_age("帮我建个新患者，李明，45岁男性") == 45


# ---------------------------------------------------------------------------
# Gender extraction
# ---------------------------------------------------------------------------


def test_extract_gender_male():
    assert _extract_gender("45岁男性") == "男"


def test_extract_gender_female():
    assert _extract_gender("30岁女性") == "女"


def test_extract_gender_male_short():
    assert _extract_gender("男，55岁") == "男"


def test_extract_gender_not_present():
    assert _extract_gender("患者头痛两天") is None


# ---------------------------------------------------------------------------
# Name extraction
# ---------------------------------------------------------------------------


def test_extract_name_after_huanzhe():
    assert _extract_name("患者李明今天复诊") == "李明"


def test_extract_name_jieba_nr():
    # jieba should tag common names as 'nr'
    name = _extract_name("帮我建个新患者，张伟，30岁男性")
    assert name is not None


def test_extract_name_not_present():
    result = _extract_name("今天天气真好")
    # May or may not find a name — just ensure it doesn't crash
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Full IntentResult entity extraction
# ---------------------------------------------------------------------------


def test_create_patient_full_entities():
    r = detect_intent_rules("帮我建个新患者，李明，45岁男性")
    assert r.intent == Intent.create_patient
    assert r.age == 45
    assert r.gender == "男"


def test_add_record_with_patient_name():
    r = detect_intent_rules("王芳今天咳嗽三天，诊断上呼吸道感染")
    assert r.intent == Intent.add_record
    assert r.age is None  # no age mentioned


def test_add_record_recording_trigger():
    r = detect_intent_rules("帮我记一下，患者今天头晕")
    assert r.intent == Intent.add_record


def test_add_record_colloquial_name_plus_symptom():
    r = detect_intent_rules("王芳，最近头疼很久，需要多喝热水")
    assert r.intent == Intent.add_record


def test_add_record_new_symptom_keywords():
    for text in ["患者感冒流涕两天", "牙疼三天开了消炎药", "腹胀胃疼，给予奥美拉唑"]:
        r = detect_intent_rules(text)
        assert r.intent == Intent.add_record, f"Expected add_record for: {text}"


# ---------------------------------------------------------------------------
# Cardiology keywords
# ---------------------------------------------------------------------------


def test_cardiology_symptoms_trigger_add_record():
    for text in [
        "患者胸痛两小时，心电图ST段抬高",
        "老李房颤，心率120，准备射频消融",
        "EF值35%，气短加重，调整利尿剂",
        "冠心病支架术后，阿司匹林双抗治疗中",
        "BNP 800，心衰加重",
    ]:
        r = detect_intent_rules(text)
        assert r.intent == Intent.add_record, f"Expected add_record for: {text}"


# ---------------------------------------------------------------------------
# Emergency detection
# ---------------------------------------------------------------------------


def test_emergency_sets_is_emergency_flag():
    r = detect_intent_rules("3床室颤，立即除颤")
    assert r.intent == Intent.add_record
    assert r.is_emergency is True


def test_emergency_overrides_other_intents():
    # Contains query keywords but emergency wins
    r = detect_intent_rules("查一下，患者心跳停止了")
    assert r.intent == Intent.add_record
    assert r.is_emergency is True


def test_non_emergency_has_false_flag():
    r = detect_intent_rules("患者头痛两天，诊断偏头痛")
    assert r.is_emergency is False


# ---------------------------------------------------------------------------
# CV metrics extraction
# ---------------------------------------------------------------------------


def test_cv_metrics_blood_pressure_slash_format():
    m = _extract_cv_metrics("血压160/100mmHg")
    assert m["bp_systolic"] == 160
    assert m["bp_diastolic"] == 100


def test_cv_metrics_heart_rate():
    m = _extract_cv_metrics("心率95次/分")
    assert m["heart_rate"] == 95


def test_cv_metrics_ef():
    m = _extract_cv_metrics("EF值只有35%，心衰加重")
    assert m["ef"] == 35


def test_cv_metrics_combined():
    m = _extract_cv_metrics("新患者张三，65岁，胸痛2小时，血压160/100，心率95")
    assert m["bp_systolic"] == 160
    assert m["bp_diastolic"] == 100
    assert m["heart_rate"] == 95


def test_cv_metrics_empty_for_non_cv_text():
    m = _extract_cv_metrics("今天天气真好")
    assert m == {}


def test_add_record_carries_cv_metrics():
    r = detect_intent_rules("患者胸痛，血压160/100，心率95，诊断急性冠脉综合征")
    assert r.intent == Intent.add_record
    assert r.extra_data.get("bp_systolic") == 160
    assert r.extra_data.get("heart_rate") == 95
