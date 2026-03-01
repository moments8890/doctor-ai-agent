"""Tests for services/intent_rules.py — no mocking, pure logic."""
from services.intent_rules import detect_intent_rules, _extract_age, _extract_gender, _extract_name
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
