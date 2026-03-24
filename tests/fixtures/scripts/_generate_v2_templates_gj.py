#!/usr/bin/env python3
"""
临床情景模板 G–J：心律失常、脓毒症/重症、CKD肾科、精神心理。

由 generate_v2_expansion.py 导入；每个 tmpl_* 函数返回一个病例字典。

Clinical scenario templates G–J for V2 chatlog expansion.
导出：tmpl_arrhythmia, tmpl_sepsis, tmpl_renal, tmpl_mental
"""

from __future__ import annotations

import random

from tests.fixtures.scripts._generate_v2_phrase_bank import (
    addendum,
    context_summary,
    correction,
    followup_interval,
    lab_creatinine,
    lab_hb,
    opening_intro,
    query_history,
    save_command,
    set_reminder,
    vitals_hr,
)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE G – Arrhythmia management
# ═══════════════════════════════════════════════════════════════════════════════
RHYTHMS = [
    "持续性心房颤动（Af）",
    "阵发性心房颤动",
    "频发室性早搏（室早>10000次/24h）",
    "Ⅱ度Ⅱ型房室传导阻滞（莫氏Ⅱ型）",
    "窦性心动过速（HR>120次/分）",
    "室上性心动过速（SVT）",
    "心房扑动伴2:1传导",
    "长QT综合征，QTc延长",
    "预激综合征（WPW），心动过速",
    "病态窦房结综合征",
]

ANTIARRHYTHMIC_DRUGS = [
    "胺碘酮200mg tid，1周后减量至200mg qd",
    "比索洛尔2.5mg qd，逐步加量至5mg",
    "地高辛0.125mg qd，监测地高辛浓度",
    "维拉帕米40mg tid（禁用于WPW合并AF）",
    "利伐沙班20mg qd（随餐服用）抗凝",
    "华法林，INR目标2.0-3.0，每周监测",
    "普罗帕酮150mg tid",
    "索他洛尔80mg bid",
    "决奈达隆400mg bid",
    "伊布利特复律",
]

HOLTER_RESULTS = [
    "24小时Holter：早搏>10000次/24h，最长间歇1.8秒，室性连发3次",
    "Holter未见恶性心律失常，平均心率78次/分，房早偶发",
    "Holter示阵发性房颤共6次，总时长2.3小时，最长1.5小时",
    "24小时心电监测：室早二联律，有短阵室速（3-5次）",
    "Holter：高度房室传导阻滞，最长RR间期3.2秒，建议起搏器",
    "Holter结果待回，今先记临床印象",
    "动态心电图：WPW图形，最短RR 0.22秒，高危型",
]

ARRHYTHMIA_PLANS = [
    "评估射频消融适应症，请电生理科会诊。",
    "考虑心脏起搏器植入，转心外科评估。",
    "CHA₂DS₂-VASc评分{score}分，予抗凝治疗。",
    "Holter动态监测，评估心律失常负荷。",
    "调整抗心律失常药物，监测QTc。",
    "电复律后维持窦律，使用抗心律失常药物。",
    "控制心室率为主，不急于恢复窦律。",
]

def _arrhythmia_turns(
    name: str, gender: str, age: int, rhythm: str, hr: int,
    drug: str, holter: str, plan: str, hr_str: str, save: str,
    rng: random.Random,
) -> list:
    """Build arrhythmia template turn options and pick one."""
    open_v = [
        f"{name}，{gender}，{age}岁，心悸就诊，心电图示{rhythm}，{hr_str}。",
        f"心律失常患者{name}，{age}岁，ECG：{rhythm}，心率{hr}次/分。",
        f"{name}，{gender}，{age}，主诉心悸{rng.randint(1,7)}天，今日心电图：{rhythm}。",
        f"门诊：{name}，{gender}{age}岁，心慌不适，心电图报告{rhythm}，心率{hr}。",
    ]
    hd_v = [
        f"{holter}，予{drug}，{plan}",
        f"动态心电图结果：{holter}。用药：{drug}。下一步：{plan}",
        f"Holter回报：{holter}。处理：{drug}，{plan}",
        f"根据{holter}，方案：{drug}，{plan}",
    ]
    fw_v = [
        f"记录心律失常类型、当前治疗和评估结论，{followup_interval(4, rng)}复查心电图。",
        "1个月后门诊随访，复查12导联心电图和Holter。",
        "监测药物不良反应（甲状腺、肝肾功、QTc），2周后复诊。",
        "如心悸加重或晕厥，立即急诊。1个月复查动态心电图。",
    ]
    options = [
        [rng.choice(open_v), rng.choice(hd_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(hd_v),
         addendum(f"LVEF {rng.randint(40, 65)}%，左房内径{rng.randint(38, 55)}mm", rng),
         rng.choice(fw_v), save],
        [rng.choice(open_v), query_history(name, rng), rng.choice(hd_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(hd_v), rng.choice(fw_v),
         set_reminder(name, "1个月后", rng), save],
        [rng.choice(open_v), rng.choice(hd_v),
         context_summary(name, f"{rhythm}，{drug[:8]}治疗中", rng),
         rng.choice(fw_v), save],
    ]
    return rng.choice(options)


def tmpl_arrhythmia(name: str, idx: int, rng: random.Random) -> dict:
    """Return one arrhythmia management case dict."""
    gender = rng.choice(["男", "女"])
    age = rng.randint(46, 80)
    rhythm = rng.choice(RHYTHMS)
    hr = rng.randint(48, 152)
    drug = rng.choice(ANTIARRHYTHMIC_DRUGS)
    holter = rng.choice(HOLTER_RESULTS)
    score = rng.randint(1, 5)
    plan = rng.choice(ARRHYTHMIA_PLANS).format(score=score)
    hr_str = vitals_hr(hr, rng)
    chief = rng.choice(["心律失常", "心房颤动", "心悸"])
    save = save_command(name, gender, age, chief, rng)
    turns = _arrhythmia_turns(name, gender, age, rhythm, hr, drug, holter, plan, hr_str, save, rng)
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["心律失常", "房颤", "Holter", "抗凝", "心电图", "早搏", "心悸"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE H – Sepsis / critical care
# ═══════════════════════════════════════════════════════════════════════════════
SEPSIS_SOURCES = [
    "肺源性脓毒症（重症肺炎）",
    "腹腔源性脓毒症（急性化脓性阑尾炎穿孔）",
    "泌尿系统来源脓毒血症（复杂性UTI）",
    "血流感染（CVC相关导管感染）",
    "皮肤软组织坏死性筋膜炎，脓毒性休克",
    "胆道源性脓毒症（急性梗阻性化脓性胆管炎）",
    "腹腔内脓肿，术后感染性休克",
]

ICU_ANTIBIOTICS = [
    "亚胺培南西司他丁0.5g q6h + 万古霉素15mg/kg q12h（MRSA覆盖）",
    "哌拉西林他唑巴坦4.5g q8h + 氟康唑400mg qd（真菌覆盖）",
    "头孢他啶2g q8h + 甲硝唑500mg q8h",
    "美罗培南1g q8h + 利奈唑胺600mg q12h",
    "头孢吡肟2g q8h + 替考拉宁400mg q12h",
    "替加环素50mg q12h + 美罗培南1g q8h（广谱覆盖）",
]

VASOPRESSORS = [
    "去甲肾上腺素0.1-0.3μg/kg/min，目标MAP≥65mmHg",
    "多巴胺5-10μg/kg/min维持循环",
    "血压尚稳定，暂无需升压药，密切监测",
    "联合血管加压素0.03U/min + 去甲肾上腺素",
    "肾上腺素0.05μg/kg/min（去甲不足时）",
]

BUNDLE_STATUS = [
    "1小时集束化治疗已完成：血培养、抗生素、液体复苏。",
    "3小时集束化治疗达标：血培养2套，乳酸复查，抗生素已给。",
    "6小时集束化治疗完成，记录MAP、CVP和尿量目标。",
    "Hour-1 bundle完成，等待血培养结果，持续关注。",
]

ORGAN_MONITORING = [
    "每4小时评估器官功能，监测尿量>0.5ml/kg/h、肌酐、凝血。",
    "ICU持续监护，SOFA评分追踪，防止器官衰竭进展。",
    "监测：尿量、肌酐、乳酸、血小板趋势，警惕DIC。",
    "每6小时复查血气分析、乳酸和血常规，评估治疗反应。",
]

def _sepsis_turns(
    name: str, gender: str, age: int, source: str, pct: float,
    lactate: float, abx: str, vasopressor: str, bundle: str,
    organ_mon: str, map_val: int, save: str,
    rng: random.Random,
) -> list:
    """Build sepsis template turn options and pick one."""
    open_v = [
        f"{name}，{gender}，{age}岁，{source}，PCT {pct}ng/mL，乳酸{lactate}mmol/L。",
        f"ICU新入患者{name}，{gender}{age}，{source}，PCT {pct}，乳酸{lactate}。",
        f"{name}，{source}，年龄{age}，PCT {pct}ng/mL，血乳酸{lactate}mmol/L，血压{map_val}mmHg（MAP）。",
        f"脓毒症记录：{name}，{gender}，{age}岁，{source}，指标：PCT {pct}，LAC {lactate}。",
    ]
    tx_v = [
        f"予{abx}广谱覆盖，30ml/kg晶体液复苏，{vasopressor}。",
        f"抗感染：{abx}。复苏：30ml/kg乳酸林格液。升压：{vasopressor}。",
        f"{vasopressor}，同时{abx}经验性覆盖，完成液体复苏。",
    ]
    fw_v = [
        f"{bundle}{organ_mon}",
        f"{organ_mon}，{bundle}",
        f"集束化治疗：{bundle}，此后{organ_mon}",
    ]
    options = [
        [rng.choice(open_v), rng.choice(tx_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(tx_v),
         addendum("血培养已送检2套，等待结果，经验性覆盖", rng),
         rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(tx_v), rng.choice(fw_v),
         context_summary(name, f"{source}，PCT {pct}，乳酸{lactate}，{abx[:10]}覆盖中", rng), save],
        [rng.choice(open_v), rng.choice(tx_v), rng.choice(fw_v),
         set_reminder(name, "6小时后", rng), save],
    ]
    return rng.choice(options)


def tmpl_sepsis(name: str, idx: int, rng: random.Random) -> dict:
    """Return one sepsis / critical care case dict."""
    gender = rng.choice(["男", "女"])
    age = rng.randint(50, 90)
    source = rng.choice(SEPSIS_SOURCES)
    pct = round(rng.uniform(2.0, 60.0), 1)
    lactate = round(rng.uniform(1.5, 7.0), 1)
    abx = rng.choice(ICU_ANTIBIOTICS)
    vasopressor = rng.choice(VASOPRESSORS)
    bundle = rng.choice(BUNDLE_STATUS)
    organ_mon = rng.choice(ORGAN_MONITORING)
    map_val = rng.randint(55, 75)
    chief = rng.choice(["脓毒症", "感染性休克", source[:4]])
    save = save_command(name, gender, age, chief, rng)
    turns = _sepsis_turns(
        name, gender, age, source, pct, lactate, abx,
        vasopressor, bundle, organ_mon, map_val, save, rng,
    )
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["脓毒症", "感染", "PCT", "乳酸", "抗生素", "升压", "ICU", "集束化"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE I – CKD / renal
# ═══════════════════════════════════════════════════════════════════════════════
CKD_STAGES = [
    "CKD G3a期（eGFR 45-59 mL/min/1.73m²）",
    "CKD G3b期（eGFR 30-44）",
    "CKD G4期（eGFR 15-29）",
    "CKD G5期（透析前，eGFR<15）",
    "AKI 2期（肌酐升至基线2-3倍）",
    "终末期肾病（ESRD），维持性血液透析",
    "IgA肾病，慢性肾功能不全进展期",
    "糖尿病肾病IV期",
]

RENAL_PLANS = [
    "低蛋白饮食0.6g/kg/d，碳酸氢钠碱化尿液，控制血钾",
    "EPO 3000U每周3次皮下注射，蔗糖铁静注补铁",
    "肾内科会诊，评估透析时机，建议尽早建立AV瘘",
    "腹膜透析培训已开始，计划本周行腹透管置入",
    "血液透析每周3次，调整透析处方（时间/超滤量）",
    "限制钾磷摄入，碳酸钙作为磷结合剂餐中服用",
    "评估肾移植条件，转移植外科会诊",
]

RENAL_ELECTROLYTES = [
    lambda rng: f"血钾{round(rng.uniform(4.3, 7.0), 1)}mmol/L，血钠{rng.randint(130, 145)}mmol/L",
    lambda rng: f"血磷{round(rng.uniform(1.6, 3.0), 1)}mmol/L，血钙{round(rng.uniform(1.8, 2.3), 1)}mmol/L",
    lambda rng: f"碳酸氢根{rng.randint(14, 22)}mmol/L，酸中毒",
    lambda rng: f"血钾{round(rng.uniform(5.5, 7.0), 1)}mmol/L（高钾），需紧急处理",
]

def _renal_turns(
    name: str, gender: str, age: int, stage: str, cr: int,
    gfr: int, cr_str: str, electrolyte: str, hb_v: int,
    plan: str, save: str, rng: random.Random,
) -> list:
    """Build CKD/renal template turn options and pick one."""
    open_v = [
        f"{name}，{gender}，{age}岁，{stage}随访，{cr_str}，eGFR {gfr}mL/min/1.73m²。",
        f"肾内科随访：{name}，{age}岁，{stage}，肌酐{cr}，eGFR {gfr}。",
        f"{name}复诊，{gender}{age}岁，{stage}，今日血肌酐{cr}μmol/L，GFR {gfr}。",
        f"CKD患者{name}记录，{stage}，{cr_str}，eGFR {gfr}。",
    ]
    lab_v = [
        f"{electrolyte}，{lab_hb(hb_v, rng)}，{plan}，限制磷蛋白摄入。",
        f"电解质：{electrolyte}。血红蛋白{hb_v}g/L。方案：{plan}。",
        f"化验汇总：{electrolyte}，Hb {hb_v}。治疗：{plan}。",
    ]
    fw_v = [
        "1个月后复查肾功能、电解质、贫血三项，今日血压控制欠佳，调整降压方案。",
        f"{followup_interval(4, rng)}复查肾功、电解质、血常规，追踪CKD进展速度。",
        "记录本次CKD评估，注意避免肾毒性药物（NSAID、造影剂），下次门诊前后尿检。",
        "建议患者戒烟、控制血压和血糖，延缓CKD进展，下次复查带入尿液标本。",
    ]
    options = [
        [rng.choice(open_v), rng.choice(lab_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(lab_v),
         addendum("今日做床旁超声，双肾缩小，皮质变薄，符合CKD表现", rng),
         rng.choice(fw_v), save],
        [rng.choice(open_v), query_history(name, rng), rng.choice(lab_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(lab_v), rng.choice(fw_v),
         set_reminder(name, "1个月后", rng), save],
    ]
    return rng.choice(options)


def tmpl_renal(name: str, idx: int, rng: random.Random) -> dict:
    """Return one CKD / renal case dict."""
    gender = rng.choice(["男", "女"])
    age = rng.randint(40, 80)
    cr = rng.randint(180, 650)
    gfr = rng.randint(6, 48)
    stage = rng.choice(CKD_STAGES)
    electrolyte = rng.choice(RENAL_ELECTROLYTES)(rng)
    hb_v = rng.randint(68, 115)
    plan = rng.choice(RENAL_PLANS)
    cr_str = lab_creatinine(cr, rng)
    chief = rng.choice(["肾功能不全", "CKD随访", "慢性肾脏病"])
    save = save_command(name, gender, age, chief, rng)
    turns = _renal_turns(name, gender, age, stage, cr, gfr, cr_str, electrolyte, hb_v, plan, save, rng)
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["肾功能", "肌酐", "透析", "CKD", "eGFR", "电解质", "肾脏"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE J – Mental health
# ═══════════════════════════════════════════════════════════════════════════════
PSYCH_CONDITIONS = [
    "抑郁症（中重度发作）",
    "广泛性焦虑障碍（GAD）",
    "双相情感障碍Ⅰ型躁狂发作",
    "创伤后应激障碍（PTSD）",
    "强迫症（OCD），强迫观念为主",
    "社交焦虑障碍（社恐）",
    "惊恐障碍，惊恐发作每周>2次",
    "精神分裂症缓解期，维持治疗",
    "进食障碍（神经性厌食症）",
    "注意缺陷多动障碍（ADHD，成人型）",
    "躯体形式障碍，多部位躯体不适",
]

PSYCH_SCALES = [
    ("PHQ-9", lambda rng: rng.randint(10, 27)),
    ("GAD-7", lambda rng: rng.randint(10, 21)),
    ("HAMD-17", lambda rng: rng.randint(14, 30)),
    ("YMRS（躁狂）", lambda rng: rng.randint(12, 32)),
    ("PCL-5（PTSD）", lambda rng: rng.randint(28, 65)),
    ("PANSS（阳性）", lambda rng: rng.randint(15, 35)),
    ("Y-BOCS（强迫）", lambda rng: rng.randint(16, 35)),
]

PSYCH_DRUGS = [
    "舍曲林100mg qd（SSRI）",
    "文拉法辛缓释75mg qd，逐步加量至225mg（SNRI）",
    "氟西汀20mg qd，4周后评估加量",
    "劳拉西泮0.5mg tid短期使用（≤4周），减少依赖风险",
    "碳酸锂300mg bid，定期监测血锂（目标0.6-1.2mmol/L）",
    "奥氮平5mg qn（联合情绪稳定剂）",
    "度洛西汀60mg qd（抑郁+焦虑双重）",
    "帕罗西汀20mg qd（强迫症适应）",
    "喹硫平缓释25mg qn（辅助催眠/心境稳定）",
    "阿立哌唑10mg qd（双相辅助治疗）",
    "艾司西酞普兰10mg qd，副作用少，耐受性好",
]

RISK_LEVELS = [
    "无自杀/暴力风险，门诊随访，告知紧急联系方式。",
    "低风险，建议家属陪护，避免单独留患者，2周后复诊。",
    "中等风险，评估住院或日间病房指征，紧急联系人已告知。",
    "高风险，建议住院观察，已通知家属并签署知情同意。",
]

PSYCH_THERAPY = [
    "配合认知行为治疗（CBT），每周1次，共12次。",
    "建议正念减压疗法（MBSR），结合药物治疗。",
    "转介心理咨询，同时药物维持。",
    "辩证行为治疗（DBT）适用，已转介心理治疗师。",
    "心理支持治疗为主，暂不用药，密切随访。",
]

def _mental_turns(
    name: str, gender: str, age: int, condition: str,
    scale_name: str, score: int, drug: str, risk: str,
    therapy: str, fw_weeks: int, save: str,
    rng: random.Random,
) -> list:
    """Build mental health template turn options and pick one."""
    open_v = [
        f"{name}，{gender}，{age}岁，{condition}，{scale_name}评分{score}分。",
        f"精神科就诊：{name}，{gender}{age}，诊断{condition}，量表{scale_name} {score}分。",
        f"{name}，{age}岁，{condition}，今日门诊评估，{scale_name}={score}分。",
        f"心理/精神科记录：{name}，{gender}，{age}岁，{condition}，{scale_name}评分{score}。",
    ]
    dr_v = [
        f"予{drug}，{risk}{therapy}",
        f"用药方案：{drug}。风险评级：{risk.split('，')[0]}。治疗：{therapy}",
        f"开具：{drug}。{risk}推荐{therapy}",
        f"{drug}，同时{therapy}{risk}",
    ]
    fw_v = [
        f"{followup_interval(fw_weeks, rng)}随访，评估药物疗效和副反应，复查{scale_name}。",
        f"记录本次评估和用药，{fw_weeks}周后复诊，监测药物不良反应。",
        f"复诊时间：{followup_interval(fw_weeks, rng)}，关注睡眠、情绪和副反应（性功能/体重）。",
        "如症状明显加重或出现自伤倾向，立即急诊精神科就诊。",
    ]
    options = [
        [rng.choice(open_v), rng.choice(dr_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(dr_v),
         addendum("患者主诉睡眠障碍，入睡困难，予佐匹克隆短期辅助", rng),
         rng.choice(fw_v), save],
        [rng.choice(open_v), query_history(name, rng), rng.choice(dr_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(dr_v), rng.choice(fw_v),
         context_summary(name, f"{condition}，{scale_name} {score}分，{drug[:8]}治疗中", rng), save],
        [rng.choice(open_v), rng.choice(dr_v),
         correction("量表评分", f"{scale_name} {score}分（已核实）", rng),
         rng.choice(fw_v), save],
    ]
    return rng.choice(options)


def tmpl_mental(name: str, idx: int, rng: random.Random) -> dict:
    """Return one mental health case dict."""
    gender = rng.choice(["男", "女"])
    age = rng.randint(18, 68)
    condition = rng.choice(PSYCH_CONDITIONS)
    scale_name, score_fn = rng.choice(PSYCH_SCALES)
    score = score_fn(rng)
    drug = rng.choice(PSYCH_DRUGS)
    risk = rng.choice(RISK_LEVELS)
    therapy = rng.choice(PSYCH_THERAPY)
    fw_weeks = rng.choice([1, 2, 4])
    chief = condition[:4]
    save = save_command(name, gender, age, chief, rng)
    turns = _mental_turns(name, gender, age, condition, scale_name, score, drug, risk, therapy, fw_weeks, save, rng)
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["抑郁", "焦虑", "PHQ", "情绪", "心理", "GAD", "HAMD", "精神", "量表"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
