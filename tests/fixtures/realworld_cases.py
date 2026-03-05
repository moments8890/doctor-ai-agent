from __future__ import annotations

from typing import List, Tuple


# (case_id, patient_name, input_text, expected_tokens_anywhere, expect_no_treatment)
REALWORLD_SCENARIOS: List[Tuple[str, str, str, List[str], bool]] = [
    (
        "verbose_stemi",
        "黎峰",
        "黎峰，男，59岁。今晨6点突发胸痛2小时，伴大汗恶心，心电图提示前壁ST段抬高，考虑STEMI，已走急诊PCI绿色通道。",
        ["stemi", "pci", "胸痛"],
        False,
    ),
    (
        "terse_note",
        "高宁",
        "高宁，男，47岁，胸闷3天。",
        ["胸闷"],
        True,
    ),
    (
        "multiline_fragmented",
        "赵岚",
        "赵岚，女，66岁\n反复胸闷1周\n活动后加重\nBNP 2100，EF 35%\n拟利尿+扩血管，3天复查",
        ["bnp", "ef"],
        False,
    ),
    (
        "oncology_followup",
        "许宁",
        "许宁，女，54岁，HER2阳性乳腺癌术后，化疗后乏力，拟继续靶向治疗，2周后门诊复查。",
        ["her2", "化疗", "靶向"],
        False,
    ),
    (
        "renal_marker",
        "何川",
        "何川，男，63岁，慢性肾病，最近EGFR下降，乏力纳差，建议调整用药并复查肾功。",
        ["egfr", "复查"],
        False,
    ),
    (
        "abbrev_heavy",
        "王述",
        "王述，男，71岁，CHF急性加重，NYHA III，BNP较前升高，EF 30%，予利尿、ARNI优化。",
        ["nyha", "bnp", "ef"],
        False,
    ),
    (
        "sparse_no_treatment",
        "尹晴",
        "尹晴，女，60岁，头痛2天，睡眠差。",
        ["头痛"],
        True,
    ),
    (
        "noisy_with_typos",
        "陈默",
        "陈默，男，58岁，突发胸痛2x小时，伴大汗，心电土疑ST段抬高，考虑stmei，拟急诊pci。",
        ["st", "pci", "胸痛"],
        False,
    ),
    (
        "short_english_mix",
        "周煜",
        "周煜, male 52, chest pain after exertion, ECG abnormal, plan CTA + follow-up.",
        ["胸痛", "ecg", "cta"],
        False,
    ),
    (
        "neuro_style_brief",
        "林烁",
        "林烁，男，68岁，突发言语含糊3小时，右上肢乏力，拟卒中流程评估。",
        ["言语", "乏力"],
        False,
    ),
]
