#!/usr/bin/env python3
"""
向 V2 聊天日志 fixture 追加 20 条 REALWORLD-V2-CORRECTION-XXX 更正案例。

Append 20 REALWORLD-V2-CORRECTION-XXX cases to v2 chatlog fixture.

Each case exercises a doctor correcting or updating patient information mid-conversation:
- gender / age / name corrections
- chief complaint overrides
- vital sign corrections
- addendum (supplemental symptoms)
- medication / dosage corrections
- lab value corrections
- diagnosis refinement
- allergy / history additions
- duration corrections
- mid-sentence self-correction phrasing

Expectations validate that the CORRECTED value (not the original wrong one)
appears in the agent's final acknowledgement.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = (
    ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v2.json"
)

CORRECTION_CASES = [
    # ── 001 Gender correction ─────────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-001",
        "title": "Doctor corrects patient gender (男→女) mid-dictation",
        "chatlog": [
            {"speaker": "doctor", "text": "张晴，男，35岁，头痛2天，睡眠差。"},
            {"speaker": "doctor", "text": "等等，张晴是女性，刚才性别说错了，请更正为女。"},
            {"speaker": "doctor", "text": "确认患者张晴，女，35岁，主诉头痛，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["女", "张晴", "头痛"]],
            "correction_type": "gender",
            "corrected_value": "女",
            "wrong_value": "男",
        },
    },
    # ── 002 Age correction ────────────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-002",
        "title": "Doctor corrects patient age (45→54) mid-dictation",
        "chatlog": [
            {"speaker": "doctor", "text": "陈旭，男，45岁，胸闷1周，活动后加重。"},
            {"speaker": "doctor", "text": "不对，年龄写错了，陈旭是54岁，不是45岁，帮我改一下。"},
            {"speaker": "doctor", "text": "确认患者陈旭，男，54岁，主诉胸闷，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["54", "陈旭", "胸闷"]],
            "correction_type": "age",
            "corrected_value": "54",
            "wrong_value": "45",
        },
    },
    # ── 003 Chief complaint correction ────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-003",
        "title": "Doctor corrects chief complaint (胸闷→胸痛)",
        "chatlog": [
            {"speaker": "doctor", "text": "李波，男，52岁，主诉胸闷3天，活动后加重。"},
            {"speaker": "doctor", "text": "不对，李波的主诉是胸痛，不是胸闷，请帮我更正。"},
            {"speaker": "doctor", "text": "确认患者李波，主诉胸痛，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["胸痛", "李波", "更正"]],
            "correction_type": "chief_complaint",
            "corrected_value": "胸痛",
            "wrong_value": "胸闷",
        },
    },
    # ── 004 Vital signs correction ────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-004",
        "title": "Doctor corrects blood pressure reading (150/90→170/105)",
        "chatlog": [
            {"speaker": "doctor", "text": "吴强，男，63岁，高血压门诊，血压150/90mmHg，心率80次/分。"},
            {"speaker": "doctor", "text": "血压读错了，实际是170/105，请更正，刚才记错了。"},
            {"speaker": "doctor", "text": "确认患者吴强，血压170/105，高血压，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["170", "170/105", "吴强", "更正"]],
            "correction_type": "vital_signs",
            "corrected_value": "170/105",
            "wrong_value": "150/90",
        },
    },
    # ── 005 Symptom addendum ──────────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-005",
        "title": "Doctor adds supplemental symptoms after initial sparse note",
        "chatlog": [
            {"speaker": "doctor", "text": "孙明，男，48岁，头痛2天。"},
            {"speaker": "doctor", "text": "补充一下：还有恶心和发热38.5℃，昨晚畏光明显。"},
            {"speaker": "doctor", "text": "孙明，头痛伴恶心发热畏光，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["头痛", "恶心", "发热", "38", "畏光"]],
            "correction_type": "addendum",
        },
    },
    # ── 006 Medication name correction ────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-006",
        "title": "Doctor corrects medication name (阿司匹林→氯吡格雷)",
        "chatlog": [
            {"speaker": "doctor", "text": "王磊，男，58岁，PCI术后，出院带药阿司匹林100mg qd。"},
            {"speaker": "doctor", "text": "刚才药名说错了，应该是氯吡格雷75mg，不是阿司匹林，请更正。"},
            {"speaker": "doctor", "text": "确认患者王磊，PCI术后，带药氯吡格雷75mg，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["氯吡格雷", "75mg", "更正"]],
            "correction_type": "medication",
            "corrected_value": "氯吡格雷75mg",
            "wrong_value": "阿司匹林",
        },
    },
    # ── 007 Lab value correction ──────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-007",
        "title": "Doctor corrects BNP lab value (1200→2100)",
        "chatlog": [
            {"speaker": "doctor", "text": "赵敏，女，67岁，心衰随访，BNP 1200pg/mL，EF 32%。"},
            {"speaker": "doctor", "text": "BNP那个数值我看错了，是2100，不是1200，帮我改掉。"},
            {"speaker": "doctor", "text": "确认患者赵敏，BNP 2100，心衰，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["2100", "BNP", "赵敏"]],
            "correction_type": "lab_value",
            "corrected_value": "2100",
            "wrong_value": "1200",
        },
    },
    # ── 008 Duration correction ───────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-008",
        "title": "Doctor corrects symptom duration (2天→2周)",
        "chatlog": [
            {"speaker": "doctor", "text": "刘洋，男，44岁，咳嗽2天，有痰。"},
            {"speaker": "doctor", "text": "不对，咳嗽是2周了，不是2天，时间说错了。"},
            {"speaker": "doctor", "text": "确认患者刘洋，咳嗽2周，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["2周", "刘洋", "咳嗽"]],
            "correction_type": "duration",
            "corrected_value": "2周",
            "wrong_value": "2天",
        },
    },
    # ── 009 Family history addition ───────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-009",
        "title": "Doctor adds family history that was initially omitted",
        "chatlog": [
            {"speaker": "doctor", "text": "陈默，男，58岁，突发胸痛2小时，STEMI可能，急诊就诊。"},
            {"speaker": "doctor", "text": "家族史补充一下：父亲有早发冠心病，55岁心梗，刚才忘记说了。"},
            {"speaker": "doctor", "text": "确认患者陈默，主诉急性胸痛，家族史阳性，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["家族", "冠心病", "胸痛", "STEMI"]],
            "correction_type": "addendum_family_history",
        },
    },
    # ── 010 Drug dosage correction ────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-010",
        "title": "Doctor corrects insulin dosage (8U→16U)",
        "chatlog": [
            {"speaker": "doctor", "text": "孟晨，女，55岁，2型糖尿病，甘精胰岛素8U每晚皮下注射。"},
            {"speaker": "doctor", "text": "剂量有误，应该是16U，不是8U，帮我更正胰岛素剂量。"},
            {"speaker": "doctor", "text": "确认患者孟晨，糖尿病，甘精胰岛素16U，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["16U", "16", "胰岛素", "孟晨"]],
            "correction_type": "dosage",
            "corrected_value": "16U",
            "wrong_value": "8U",
        },
    },
    # ── 011 Diagnosis refinement ──────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-011",
        "title": "Doctor refines diagnosis from preliminary to confirmed",
        "chatlog": [
            {"speaker": "doctor", "text": "周楠，男，61岁，心电图ST段抬高，考虑STEMI。"},
            {"speaker": "doctor", "text": "更新一下，肌钙蛋白回来了，明确STEMI，不是疑似，已开启PCI绿色通道。"},
            {"speaker": "doctor", "text": "确认患者周楠，明确STEMI诊断，急诊PCI，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["STEMI", "PCI", "肌钙蛋白", "明确"]],
            "correction_type": "diagnosis_update",
        },
    },
    # ── 012 Allergy history addition ──────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-012",
        "title": "Doctor adds allergy information omitted from initial note",
        "chatlog": [
            {"speaker": "doctor", "text": "唐慧，女，42岁，社区获得性肺炎，予头孢曲松2g qd治疗。"},
            {"speaker": "doctor", "text": "等等，患者有青霉素过敏史，头孢类也需要谨慎，过敏史刚才漏了，帮我补上。"},
            {"speaker": "doctor", "text": "确认患者唐慧，肺炎，青霉素过敏史，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["过敏", "青霉素", "唐慧"]],
            "correction_type": "addendum_allergy",
        },
    },
    # ── 013 Name spelling correction ──────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-013",
        "title": "Doctor corrects patient name spelling (王铭→王明)",
        "chatlog": [
            {"speaker": "doctor", "text": "帮我创建：王铭，男，47岁，心悸反复发作。"},
            {"speaker": "doctor", "text": "名字写错了，是王明，不是王铭，两个字读音一样，帮我改正。"},
            {"speaker": "doctor", "text": "确认患者王明，男，47岁，心悸，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["王明", "心悸", "更正"]],
            "correction_type": "name_spelling",
            "corrected_value": "王明",
            "wrong_value": "王铭",
        },
    },
    # ── 014 Mid-sentence self-correction ─────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-014",
        "title": "Doctor self-corrects mid-sentence during dictation",
        "chatlog": [
            {"speaker": "doctor", "text": "林宇，男，66岁，乏力——不对，主诉是气短，不是乏力，气短3天，活动后加重。"},
            {"speaker": "doctor", "text": "气短伴轻度下肢水肿，SpO₂ 92%，考虑心功能不全。"},
            {"speaker": "doctor", "text": "确认患者林宇，主诉气短，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["气短", "林宇", "SpO"]],
            "correction_type": "inline_self_correction",
        },
    },
    # ── 015 Multiple sequential corrections ───────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-015",
        "title": "Doctor makes two sequential corrections (gender then age)",
        "chatlog": [
            {"speaker": "doctor", "text": "黄梅，男，38岁，反复发作性头痛，持续约2小时。"},
            {"speaker": "doctor", "text": "性别说错了，黄梅是女性。"},
            {"speaker": "doctor", "text": "年龄也记错了，是43岁，不是38岁。"},
            {"speaker": "doctor", "text": "确认患者黄梅，女，43岁，头痛，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["女", "43", "黄梅", "头痛"]],
            "correction_type": "multiple_corrections",
        },
    },
    # ── 016 Test result correction ────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-016",
        "title": "Doctor corrects NIHSS score after re-evaluation",
        "chatlog": [
            {"speaker": "doctor", "text": "卫东，男，72岁，急性缺血性卒中，NIHSS评分6分入院。"},
            {"speaker": "doctor", "text": "重新评估了，NIHSS是10分，不是6分，评分偏低了，请更正。"},
            {"speaker": "doctor", "text": "确认患者卫东，NIHSS 10分，急性卒中，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["NIHSS", "10", "卫东", "卒中"]],
            "correction_type": "test_result",
            "corrected_value": "NIHSS 10",
            "wrong_value": "NIHSS 6",
        },
    },
    # ── 017 Procedure correction ──────────────────────────────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-017",
        "title": "Doctor corrects stated procedure (PCI→CABG)",
        "chatlog": [
            {"speaker": "doctor", "text": "方刚，男，65岁，三支病变，计划急诊PCI手术。"},
            {"speaker": "doctor", "text": "手术方式说错了，应该是CABG，不是PCI，三支病变应该搭桥，请更正。"},
            {"speaker": "doctor", "text": "确认患者方刚，三支病变，计划CABG，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["CABG", "更正", "方刚"]],
            "correction_type": "procedure",
            "corrected_value": "CABG",
            "wrong_value": "PCI",
        },
    },
    # ── 018 Partial update (keep most, change one field) ─────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-018",
        "title": "Doctor updates only the HbA1c value, other info unchanged",
        "chatlog": [
            {"speaker": "doctor", "text": "蒋慧，女，59岁，2型糖尿病随访，HbA1c 7.2%，血压138/88mmHg，空腹血糖8.2。"},
            {"speaker": "doctor", "text": "HbA1c数值更新一下，今天报告出来了是8.1%，不是7.2%，其他不变。"},
            {"speaker": "doctor", "text": "确认患者蒋慧，HbA1c 8.1%，糖尿病随访，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["8.1", "HbA1c", "蒋慧"]],
            "correction_type": "partial_update",
            "corrected_value": "8.1%",
            "wrong_value": "7.2%",
        },
    },
    # ── 019 Spoken clarification with implicit correction ─────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-019",
        "title": "Doctor clarifies ambiguous term used in initial dictation",
        "chatlog": [
            {"speaker": "doctor", "text": "谭峰，男，55岁，肾功能异常，肌酐偏高。"},
            {"speaker": "doctor", "text": "补充具体数值：肌酐416μmol/L，eGFR 14，属于CKD G5期。"},
            {"speaker": "doctor", "text": "再查一下谭峰的既往透析记录。"},
            {"speaker": "doctor", "text": "确认患者谭峰，CKD G5期，肌酐416，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["416", "CKD", "G5", "eGFR", "谭峰"]],
            "correction_type": "clarification_with_specifics",
        },
    },
    # ── 020 Wording replacement via "不是…是…" pattern ───────────────────────
    {
        "case_id": "REALWORLD-V2-CORRECTION-020",
        "title": "Doctor uses 不是X是Y pattern to correct diagnosis category",
        "chatlog": [
            {"speaker": "doctor", "text": "叶雪，女，34岁，持续性心悸，心电图室性早搏。"},
            {"speaker": "doctor", "text": "不是室性早搏，是室上性心动过速，心电图科重新判读了，请改过来。"},
            {"speaker": "doctor", "text": "确认患者叶雪，室上性心动过速，请创建并保存本次病历。"},
        ],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["室上性", "SVT", "叶雪", "心动过速"]],
            "correction_type": "not_X_but_Y",
            "corrected_value": "室上性心动过速",
            "wrong_value": "室性早搏",
        },
    },
]


def main() -> None:
    data: list[dict] = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    current = len(data)
    print(f"Current cases: {current}")

    # Validate no duplicate case_ids
    existing_ids = {c["case_id"] for c in data}
    for case in CORRECTION_CASES:
        assert case["case_id"] not in existing_ids, f"Duplicate: {case['case_id']}"
        assert len(case["chatlog"]) >= 3, f"{case['case_id']}: needs ≥3 turns"
        doc_turns = [t for t in case["chatlog"] if t["speaker"] == "doctor"]
        assert len(doc_turns) >= 3, f"{case['case_id']}: needs ≥3 doctor turns"
        assert case["expectations"]["must_not_timeout"] is True

    data.extend(CORRECTION_CASES)
    target = current + len(CORRECTION_CASES)
    assert len(data) == target

    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Added {len(CORRECTION_CASES)} correction cases. Total: {len(data)}")

    # Show correction types covered
    types = [c["expectations"].get("correction_type", "unknown") for c in CORRECTION_CASES]
    for t in types:
        print(f"  {t}")


if __name__ == "__main__":
    main()
