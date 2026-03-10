#!/usr/bin/env python3
"""
V3 模板构建器数据与函数 — generate_v3_fixture.py 的内部辅助模块。

包含：名称池、短语库、临床情景定义、30个模板构建器函数。
由 generate_v3_fixture.py 导入；不应直接运行。

V3 template builder data and functions for generate_v3_fixture.py.
Exports: SURNAMES, MALE_GIVEN, FEMALE_GIVEN, CLINICAL_SCENARIOS,
         TEMPLATE_SCENARIO_MAP, TEMPLATE_DB_ASSERTIONS,
         OPERATION_NAMES, TEMPLATE_BUILDERS, generate_patient_pool, pick
"""

from __future__ import annotations

import random

# ─────────────────────────────────────────────────────────────────────────────
# NAME POOL
# ─────────────────────────────────────────────────────────────────────────────
SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
    "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
    "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕",
    "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛", "叶", "阎",
]

MALE_GIVEN = [
    "伟", "芳", "磊", "勇", "强", "军", "杰", "涛", "超", "明",
    "浩", "亮", "鹏", "飞", "帆", "峰", "宇", "坚", "辉", "锋",
    "博", "凯", "翔", "昊", "威", "龙", "阳", "奇", "健", "鑫",
]

FEMALE_GIVEN = [
    "芳", "霞", "娜", "静", "敏", "洁", "婷", "华", "雪", "丽",
    "慧", "颖", "燕", "萍", "梅", "玲", "云", "蕾", "琳", "莉",
    "晴", "悦", "欣", "怡", "雯", "倩", "彤", "心", "月", "蝶",
]


def gen_name(rng: random.Random, gender: str) -> str:
    sur = rng.choice(SURNAMES)
    given_pool = MALE_GIVEN if gender == "男" else FEMALE_GIVEN
    given = rng.choice(given_pool)
    if rng.random() < 0.4:
        given += rng.choice(given_pool)
    return sur + given


def gen_age(rng: random.Random, min_age: int = 28, max_age: int = 80) -> int:
    return rng.randint(min_age, max_age)


def generate_patient_pool(n: int, rng: random.Random) -> list:
    """Generate n unique patient dicts with name/gender/age."""
    seen_names: set = set()
    patients = []
    attempts = 0
    while len(patients) < n and attempts < n * 20:
        attempts += 1
        gender = rng.choice(["男", "女"])
        name = gen_name(rng, gender)
        if name in seen_names:
            continue
        seen_names.add(name)
        age = gen_age(rng)
        patients.append({"name": name, "gender": gender, "age": age})
    return patients


# ─────────────────────────────────────────────────────────────────────────────
# CLINICAL SCENARIOS
# ─────────────────────────────────────────────────────────────────────────────
CLINICAL_SCENARIOS = {
    "A": {
        "name": "急性缺血性卒中",
        "keywords": ["NIHSS", "溶栓", "脑梗", "rt-PA", "偏瘫", "卒中", "肢体无力"],
        "chief_complaints": ["突发肢体无力", "失语伴偏瘫", "头痛伴言语不清", "突发视野缺损"],
        "details": [
            "NIHSS评分8分，右侧肢体活动受限",
            "溶栓窗内，已启动rt-PA静脉溶栓",
            "MRI示左侧MCA区域梗死灶",
            "DWI高信号，FLAIR未见，考虑超急性期",
        ],
        "plans": [
            "安排72小时后复查头颅MRI及NIHSS评分",
            "神经内科会诊，评估溶栓适应证",
            "开启卒中绿色通道，备DSA介入",
        ],
    },
    "B": {
        "name": "STEMI急诊PCI",
        "keywords": ["STEMI", "PCI", "LVEF", "BNP", "肌钙蛋白", "冠脉", "心肌梗死"],
        "chief_complaints": ["胸痛2小时伴大汗", "突发剧烈胸痛放射至左臂", "胸痛伴恶心呕吐"],
        "details": [
            "心电图示II/III/aVF ST段抬高，考虑下壁STEMI",
            "肌钙蛋白I 12.4ng/mL，BNP 980pg/mL",
            "急诊PCI成功，TIMI 3级血流，LVEF 45%",
            "术后予阿司匹林+氯吡格雷双联抗板",
        ],
        "plans": [
            "术后心脏监护24小时，每6h复查心肌酶",
            "出院前复查超声心动图评估LVEF",
            "随访4周，复查BNP及心功能",
        ],
    },
    "C": {
        "name": "2型糖尿病管理",
        "keywords": ["HbA1c", "SGLT-2", "FBG", "胰岛素", "糖尿病", "血糖", "降糖"],
        "chief_complaints": ["血糖控制不佳", "反复低血糖发作", "多饮多尿体重下降"],
        "details": [
            "HbA1c 9.2%，空腹血糖FBG 12.6mmol/L",
            "调整方案：加用恩格列净10mg qd (SGLT-2抑制剂)",
            "甘精胰岛素剂量调整至20U每晚皮下注射",
            "监测血糖波动，CGM显示TIR仅42%",
        ],
        "plans": [
            "3个月后复查HbA1c及肾功能",
            "营养科会诊，制定低GI饮食方案",
            "血糖日记记录，每周上传CGM数据",
        ],
    },
    "D": {
        "name": "COPD急性加重",
        "keywords": ["SpO2", "HFNC", "哮喘", "氧疗", "COPD", "气促", "肺功能"],
        "chief_complaints": ["气促加重3天", "咳嗽咳痰伴喘息", "夜间阵发性呼吸困难"],
        "details": [
            "SpO2 88%，予高流量鼻导管HFNC氧疗60L/min FiO2 40%",
            "胸片示双肺透亮度增高，膈肌低平",
            "血气分析pH 7.32 PaCO2 58mmHg，II型呼吸衰竭",
            "予沙丁胺醇+异丙托溴铵雾化，甲强龙40mg静脉",
        ],
        "plans": [
            "每4h复查血气分析及SpO2",
            "评估无创通气(NIV)指征",
            "肺功能复查及吸入装置用药培训",
        ],
    },
    "E": {
        "name": "化疗后骨髓抑制",
        "keywords": ["化疗", "WBC", "骨髓抑制", "KPS", "粒缺", "G-CSF", "肿瘤"],
        "chief_complaints": ["化疗后发热伴粒细胞缺乏", "乏力纳差白细胞低", "化疗后4天发热"],
        "details": [
            "WBC 0.8×10⁹/L，ANC 0.3×10⁹/L，IV度粒缺发热",
            "KPS评分60分，化疗后第5天",
            "予G-CSF 300μg qd皮下注射，广谱抗生素覆盖",
            "血培养已送，暂予美罗培南1g q8h",
        ],
        "plans": [
            "每日复查血常规，WBC>2.0后评估停G-CSF",
            "肿瘤科会诊，下周期化疗方案调整预防",
            "营养支持，静脉营养补充",
        ],
    },
    "F": {
        "name": "外科术后随访",
        "keywords": ["NRS疼痛", "切口", "引流", "康复", "术后", "镇痛", "手术"],
        "chief_complaints": ["腹部手术后切口疼痛", "术后引流量增多", "术后活动受限疼痛评分高"],
        "details": [
            "NRS疼痛评分6/10，切口愈合II/甲",
            "腹腔引流管日引流量50mL淡血性液体",
            "腹腔镜下结肠癌根治术后第3天",
            "镇痛方案：氟比洛芬酯50mg q12h+按需吗啡",
        ],
        "plans": [
            "明日拔除引流管，伤口换药",
            "康复科介入，早期下地活动方案",
            "出院前评估NRS≤3，完善出院宣教",
        ],
    },
    "G": {
        "name": "心律失常管理",
        "keywords": ["房颤", "Holter", "抗凝", "射频消融", "心电图", "心律失常", "华法林"],
        "chief_complaints": ["持续性心悸伴气短", "阵发性心悸反复发作", "心悸伴头晕乏力"],
        "details": [
            "24h Holter示持续性房颤，平均心室率112次/分",
            "CHA₂DS₂-VASc评分3分，启动华法林抗凝",
            "心电图示QRS波增宽，考虑差异性传导",
            "超声示LA 48mm，建议射频消融评估",
        ],
        "plans": [
            "每周复查INR，目标2.0-3.0",
            "电生理科会诊，评估射频消融适应证",
            "每月门诊随访，复查Holter",
        ],
    },
    "H": {
        "name": "脓毒症重症监护",
        "keywords": ["PCT", "乳酸", "集束化", "去甲肾", "脓毒症", "感染", "ICU"],
        "chief_complaints": ["高热寒战血压下降", "腹腔感染脓毒症休克", "发热伴意识改变"],
        "details": [
            "PCT 48ng/mL，乳酸4.2mmol/L，脓毒症休克",
            "去甲肾上腺素0.3μg/(kg·min)维持MAP>65",
            "集束化治疗：3h bundle已完成，血培养×2已送",
            "美罗培南+万古霉素联合广谱抗感染",
        ],
        "plans": [
            "1h后复查乳酸及MAP，评估液体复苏反应",
            "感染科会诊，根据培养结果调整抗菌谱",
            "每日SBT评估，ICU集束化护理",
        ],
    },
    "I": {
        "name": "慢性肾病管理",
        "keywords": ["肌酐", "eGFR", "透析", "EPO", "CKD", "肾功能", "电解质"],
        "chief_complaints": ["肾功能进行性下降", "透析间期乏力水肿", "肌酐急剧升高"],
        "details": [
            "肌酐352μmol/L，eGFR 18mL/min，CKD G4期",
            "血钾5.8mmol/L，予限钾饮食+聚磺苯乙烯",
            "血红蛋白88g/L，予EPO 4000U皮下注射每周3次",
            "评估动静脉内瘘建立时机，肾替代治疗准备",
        ],
        "plans": [
            "4周后复查肾功能全套、电解质、血常规",
            "肾内科会诊，制定肾替代治疗时间表",
            "低蛋白饮食教育，血压控制目标<130/80",
        ],
    },
    "J": {
        "name": "抑郁焦虑综合评估",
        "keywords": ["PHQ-9", "焦虑", "抑郁", "SSRI", "GAD-7", "心理", "情绪"],
        "chief_complaints": ["情绪低落兴趣减退2月", "焦虑反复发作睡眠差", "抑郁伴躯体化症状"],
        "details": [
            "PHQ-9评分16分（中重度抑郁），GAD-7评分14分",
            "予舍曲林50mg qd起始，逐步增量至100mg",
            "有消极观念，无自杀计划，需密切随访",
            "心理治疗：CBT每周1次，共12次疗程",
        ],
        "plans": [
            "2周后门诊随访，评估药物反应及副作用",
            "精神科会诊，评估住院指征",
            "社工介入，家庭支持评估",
        ],
    },
    "K": {
        "name": "肝硬化消化道出血",
        "keywords": ["肝硬化", "内镜", "消化道出血", "胆红素", "腹水", "Child-Pugh", "EVL"],
        "chief_complaints": ["呕血黑便急诊入院", "肝硬化腹水加重", "上消化道出血"],
        "details": [
            "急诊胃镜示食管静脉曲张破裂出血，EVL治疗",
            "Child-Pugh B级，胆红素38μmol/L，白蛋白28g/L",
            "腹水B超示大量腹水，腹围105cm",
            "予奥曲肽0.1mg q8h静脉，质子泵抑制剂护胃",
        ],
        "plans": [
            "1周后复查内镜，评估EVL效果",
            "消化科+肝病科联合随访，评估TIPS适应证",
            "限钠饮食，螺内酯+呋塞米利尿，每日监测腹围",
        ],
    },
    "L": {
        "name": "出院摘要及随访计划",
        "keywords": ["出院带药", "门诊随访", "出院诊断", "带药医嘱", "出院宣教", "随访计划"],
        "chief_complaints": ["病情稳定准备出院", "住院治疗后好转出院", "达到出院标准"],
        "details": [
            "出院诊断：冠心病稳定型心绞痛，高血压3级",
            "出院带药：阿司匹林100mg qd + 阿托伐他汀20mg qn",
            "出院宣教：饮食低盐低脂，避免剧烈运动",
            "随访计划：4周后心内科门诊复诊",
        ],
        "plans": [
            "4周门诊随访，复查血脂、肾功能",
            "如出现胸痛、呼吸困难，立即急诊",
            "出院小结已归档，上传医院HIS系统",
        ],
    },
    "M": {
        "name": "血液系统疾病",
        "keywords": ["淋巴瘤", "骨髓", "PLT", "血红蛋白", "CHOP", "化疗", "造血干细胞"],
        "chief_complaints": ["颈部淋巴结进行性肿大", "全血细胞减少乏力发热", "淋巴结活检确诊"],
        "details": [
            "骨髓穿刺示弥漫大B细胞淋巴瘤(DLBCL)侵犯",
            "PLT 42×10⁹/L，血红蛋白78g/L，予输血支持",
            "R-CHOP方案第2周期，累计剂量监测",
            "LDH 680U/L，Ann Arbor分期III期B",
        ],
        "plans": [
            "2周期后PET-CT评估疗效",
            "血液科会诊，评估自体造血干细胞移植时机",
            "预防性G-CSF，监测白细胞谷值",
        ],
    },
    "N": {
        "name": "骨科关节置换康复",
        "keywords": ["THA", "TKA", "关节", "康复锻炼", "骨科", "假体", "DVT预防"],
        "chief_complaints": ["膝关节疼痛活动受限", "髋关节置换术后康复", "关节疼痛影响日常生活"],
        "details": [
            "右膝TKA术后第2天，VTE风险评估中高危",
            "予利伐沙班10mg qd预防DVT，弹力袜+气压治疗",
            "康复训练：踝泵练习+股四头肌等长收缩",
            "X线示假体位置良好，力线对齐",
        ],
        "plans": [
            "术后4周随访，评估屈膝角度及步态",
            "6周后复查X线，评估骨整合情况",
            "康复科制定3个月康复训练计划",
        ],
    },
    "O": {
        "name": "高血压心衰综合管理",
        "keywords": ["高血压", "心衰", "利尿剂", "地高辛", "ACEI", "EF", "NT-proBNP"],
        "chief_complaints": ["血压控制不佳头痛", "心衰急性加重水肿", "活动后气短下肢水肿"],
        "details": [
            "血压178/102mmHg，EF 35%，NT-proBNP 4800pg/mL",
            "予呋塞米20mg IV利尿，地高辛0.125mg qd",
            "ACEI: 培哚普利4mg qd，螺内酯20mg qd",
            "限液1500mL/d，每日监测体重及尿量",
        ],
        "plans": [
            "72小时后复查NT-proBNP及肾功能",
            "评估CRT/ICD置入适应证",
            "心脏康复门诊随访，6MWT评估",
        ],
    },
}

TEMPLATE_SCENARIO_MAP = {
    1: "A", 2: "B", 3: "C", 4: "D", 5: "E",
    6: "F", 7: "G", 8: "H", 9: "I", 10: "J",
    11: "K", 12: "L", 13: "M", 14: "N", 15: "O",
    16: "A", 17: "B", 18: "C", 19: "D", 20: "E",
    21: "F", 22: "G", 23: "H", 24: "I", 25: "J",
    26: "K", 27: "L", 28: "M", 29: "N", 30: "O",
}

TEMPLATE_DB_ASSERTIONS = {
    1:  {"patients": 1, "medical_records": 1},
    2:  {"patients": 1, "medical_records": 1},
    3:  {"patients": 1, "medical_records": 1},
    4:  {"patients": 1, "medical_records": 1},
    5:  {"patients": 1, "medical_records": 1},
    6:  {"patients": 1, "medical_records": 1},
    7:  {"patients": 1},
    8:  {"patients": 1, "medical_records": 1},
    9:  {"patients": 1, "medical_records": 1},
    10: {"patients": 1, "medical_records": 1},
    11: {"patients": 1, "medical_records": 1},
    12: {"patients": 1, "medical_records": 1},
    13: {"patients": 1, "medical_records": 1},
    14: {"patients": 1, "medical_records": 1},
    15: {"patients": 1, "medical_records": 1},
    16: {"patients": 1, "medical_records": 1},
    17: {"patients": 1, "medical_records": 1},
    18: {"patients": 1, "medical_records": 1},
    19: {"patients": 1, "medical_records": 1},
    20: {"patients": 1, "medical_records": 1},
    21: {"patients": 1, "medical_records": 1},
    22: {"patients": 1, "medical_records": 1},
    23: {"patients": 1, "medical_records": 1},
    24: {"patients": 1, "medical_records": 1},
    25: {"patients": 1, "medical_records": 1},
    26: {"patients": 1, "medical_records": 1},
    27: {"patients": 1, "medical_records": 1},
    28: {"patients": 1, "medical_records": 1},
    29: {"patients": 1, "medical_records": 1},
    30: {"patients": 1, "medical_records": 1},
}

OPERATION_NAMES = {
    1: "simple_add", 2: "add_supplement", 3: "list_then_add",
    4: "query_then_add", 5: "complete_task_add", 6: "update_patient",
    7: "duplicate_dedup", 8: "schedule_followup", 9: "multi_patient",
    10: "export_records", 11: "postpone_followup", 12: "cancel_task",
    13: "inline_correction", 14: "voice_abbreviated", 15: "mixed_language",
    16: "complex_3patient", 17: "discharge_plan", 18: "lab_update",
    19: "allergy_addendum", 20: "cross_visit",
    21: "complex_update_correction", 22: "complex_multi_schedule",
    23: "complex_lab_correction", 24: "complex_allergy_crossvisit",
    25: "complex_multi_discharge", 26: "complex_3patient_export",
    27: "complex_task_schedule_cancel", 28: "complex_inline_supplement",
    29: "complex_postpone_update", 30: "complex_query_correction_export",
}

# ─────────────────────────────────────────────────────────────────────────────
# PHRASE BANKS
# ─────────────────────────────────────────────────────────────────────────────
OPEN_CASUAL = ["先记一下：", "快速记录：", "早班先记：", "帮我记：", "简单记一个："]
OPEN_FORMAL = ["请建档：", "新患者，麻烦建档：", "新建患者档案：", "请录入新患者："]
SAVE_REQUEST = [
    "请建档并保存本次病历。", "建档保存。", "帮我录入并保存病历。",
    "确认建档，保存本次就诊记录。", "请录入并归档。",
]
TASK_LIST = ["先看下我今天的待办列表。", "查一下今天有哪些任务。", "显示我的任务列表。", "列出所有待办事项。"]
TASK_COMPLETE = ["把第一条任务标记为完成。", "完成第1个待办。", "刚才第一个任务做完了，帮我标一下。"]
SCHEDULE_REMINDER = ["帮我设一个{days}天后的复查提醒。", "添加复诊提醒：{days}天后。", "设置随访提醒，{days}天后复查。"]
LIST_PATIENTS = ["列出所有患者。", "显示当前患者列表。", "查一下我有哪些患者。", "患者列表给我看看。"]
QUERY_HISTORY = ["查一下{name}的历史病历。", "调取{name}的既往记录。", "看看{name}以前的就诊情况。"]
SUPPLEMENT = ["补充一下：", "刚才忘说了，补充：", "再补一条：", "附加信息："]
CORRECTION_PHRASE = ["刚才说错了，更正：", "不对，请改为：", "帮我更正一下：", "修改一下，"]
VOICE_ABB = ["速记：", "简记：", "快记，口述：", "语音输入："]
CONFIRM_SAVE = ["确认以上信息，请保存。", "以上信息无误，请归档。", "核对完毕，请建档保存。", "确认并保存。"]
EXPORT_PHRASE = ["导出{name}的病历摘要。", "生成{name}的出院小结。", "整理并导出{name}的就诊记录。"]
DELETE_PHRASE = ["删除第二个同名患者。", "把重复的那个患者删掉。", "第二位{name}建档有误，请删除。"]
POSTPONE_PHRASE = ["把上次设的复查提醒推迟{days}天。", "延迟复查时间{days}天。", "刚才的提醒推后{days}天再执行。"]
CANCEL_PHRASE = ["取消之前设的那个复查提醒。", "把刚才的随访任务取消掉。", "这个提醒不需要了，帮我删除。"]
ALLERGY_ADD = ["过敏史补充：{drug}过敏。", "刚才忘了，{name}有{drug}过敏史，帮我加上。", "补充过敏记录：{drug}。"]
DISCHARGE_PHRASE = [
    "出院诊断已明确，帮我出院小结。", "患者准备出院，请整理出院带药医嘱。",
    "出院了，帮我记录出院信息和随访计划。",
]


def pick(rng: random.Random, lst: list, fmt: dict = None) -> str:
    """Pick a random item from lst and optionally format it."""
    s = rng.choice(lst)
    if fmt:
        try:
            s = s.format(**fmt)
        except KeyError:
            pass
    return s


def _turn(text: str) -> dict:
    return {"speaker": "doctor", "text": text}


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE BUILDER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def build_template_1(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """simple_add: create patient + add record."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{pick(rng, OPEN_CASUAL)}{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"{rng.choice(sc['plans'])}。"),
        _turn(f"请明确执行：{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_2(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """add_supplement: create + add record + supplement addendum."""
    cc = rng.choice(sc["chief_complaints"])
    detail = rng.choice(sc["details"])
    supp = rng.choice([d for d in sc["details"] if d != detail] or sc["details"])
    return [
        _turn(f"{pick(rng, OPEN_FORMAL)}{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{detail}。"),
        _turn(f"{pick(rng, SUPPLEMENT)}{supp}。"),
        _turn(f"确认{name}所有信息，{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_3(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """list_then_add: list patients/tasks + create + add record."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{pick(rng, TASK_LIST)}"),
        _turn(f"然后新患者：{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"请建档并保存{name}本次病历。"),
    ]


def build_template_4(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """query_then_add: query existing + new add record."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{pick(rng, QUERY_HISTORY, {'name': name})}"),
        _turn(f"今天新记录：{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"{rng.choice(sc['plans'])}。"),
        _turn(f"保存{name}本次就诊记录。"),
    ]


def build_template_5(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complete_task_add: list tasks + complete task + add record."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{pick(rng, TASK_LIST)}"),
        _turn(f"{pick(rng, TASK_COMPLETE)}"),
        _turn(f"新记录{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"建档保存{name}，{sc['name']}诊断。"),
    ]


def build_template_6(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """update_patient: create + update demographic + add record."""
    cc = rng.choice(sc["chief_complaints"])
    new_age = age + rng.randint(1, 5)
    return [
        _turn(f"建档{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{pick(rng, CORRECTION_PHRASE)}年龄应为{new_age}岁，刚才记错了。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"确认{name}，{gender}，{new_age}岁，{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_7(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """duplicate_dedup: create × 2 same name + add record + delete duplicate."""
    cc = rng.choice(sc["chief_complaints"])
    other_gender = "女" if gender == "男" else "男"
    other_age = age + rng.randint(5, 15)
    return [
        _turn(f"先建档：{name}，{gender}，{age}岁。"),
        _turn(f"再来一个同名患者：{name}，{other_gender}，{other_age}岁。"),
        _turn(f"记录第二位{name}：{cc}。"),
        _turn(f"{pick(rng, DELETE_PHRASE, {'name': name})}"),
        _turn(f"确认保留{name}（{gender}，{age}岁）的档案并保存病历。"),
    ]


def build_template_8(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """schedule_followup: create + add record + set reminder."""
    cc = rng.choice(sc["chief_complaints"])
    days = rng.choice([7, 14, 30])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, SCHEDULE_REMINDER, {'days': days})}"),
        _turn(f"建档{name}并保存本次病历及提醒。"),
    ]


def build_template_9(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """multi_patient: create patient A + create patient B + query A."""
    cc = rng.choice(sc["chief_complaints"])
    name_b_gender = "女" if gender == "男" else "男"
    name_b_age = rng.randint(30, 70)
    return [
        _turn(f"先处理{name}：{gender}，{age}岁，{cc}。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"再建一个新患者，{name_b_gender}，{name_b_age}岁，{sc['name']}门诊。"),
        _turn(f"查询{name}刚刚录入的记录，确认保存。"),
    ]


def build_template_10(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """export_records: create + add record + export."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{pick(rng, OPEN_FORMAL)}{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"保存{name}病历后，{pick(rng, EXPORT_PHRASE, {'name': name})}"),
        _turn(f"确认导出完成，归档{name}本次就诊。"),
    ]


def build_template_11(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """postpone_followup: create + add record + schedule + postpone."""
    cc = rng.choice(sc["chief_complaints"])
    days1, days2 = rng.choice([7, 14]), rng.choice([3, 7])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"建档保存，{pick(rng, SCHEDULE_REMINDER, {'days': days1})}"),
        _turn(f"{pick(rng, POSTPONE_PHRASE, {'days': days2})}"),
        _turn(f"确认{name}档案及更新后的复查时间。"),
    ]


def build_template_12(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """cancel_task: create + add record + schedule + cancel task."""
    cc = rng.choice(sc["chief_complaints"])
    days = rng.choice([7, 14, 30])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"建档，{pick(rng, SCHEDULE_REMINDER, {'days': days})}"),
        _turn(f"等等，{pick(rng, CANCEL_PHRASE)}"),
        _turn(f"确认{name}病历已保存，提醒已取消。"),
    ]


def build_template_13(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """inline_correction: create with error in same turn + add record."""
    cc = rng.choice(sc["chief_complaints"])
    wrong_age = age + rng.choice([-10, -5, 5, 10])
    return [
        _turn(f"{name}，{gender}，{wrong_age}岁——不对，是{age}岁，{cc}。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"确认{name}，{gender}，{age}岁，{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_14(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """voice_abbreviated: telegraphic/abbreviated clinical notes."""
    cc = rng.choice(sc["chief_complaints"])
    kws = sc["keywords"][:3]
    return [
        _turn(f"{pick(rng, VOICE_ABB)}{name} {gender} {age}y {cc}"),
        _turn(f"{' / '.join(kws)}，{rng.choice(sc['details'][:2])}"),
        _turn(f"{rng.choice(sc['plans'])}"),
        _turn(f"建档存档 {name}。"),
    ]


def build_template_15(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """mixed_language: English abbreviations + Chinese."""
    cc = rng.choice(sc["chief_complaints"])
    kws = sc["keywords"]
    eng_kw = next((k for k in kws if k.isascii() and len(k) > 2), kws[0])
    return [
        _turn(f"Quick note: {name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{eng_kw} noted. {rng.choice(sc['details'])}。"),
        _turn(f"Save and archive {name}'s record，{rng.choice(sc['plans'])}。"),
        _turn(f"确认建档并保存{name}。"),
    ]


def build_template_16(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex_3patient: create 3 patients + 3 records + query all."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"连续建档三位患者，先是{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"第二位，{rng.randint(30,70)}岁，同类{sc['name']}就诊。"),
        _turn(f"第三位，{rng.randint(30,70)}岁，{sc['name']}复查。"),
        _turn(f"三位均需病历：{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, LIST_PATIENTS)}"),
        _turn(f"确认{name}档案及病历已保存。"),
    ]


def build_template_17(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """discharge_plan: clinical note + discharge medication + followup."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}，今日出院。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, DISCHARGE_PHRASE)}"),
        _turn(f"确认{name}出院小结已归档，随访时间已设置。"),
    ]


def build_template_18(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """lab_update: create + add lab result + correction of value."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"化验结果出来了，更新一下{rng.choice(sc['keywords'])}数值。"),
        _turn(f"{pick(rng, CORRECTION_PHRASE)}{rng.choice(sc['plans'])}。"),
        _turn(f"确认{name}更新后的化验结果已保存。"),
    ]


def build_template_19(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """allergy_addendum: create + add allergy history + add record."""
    cc = rng.choice(sc["chief_complaints"])
    drug = rng.choice(["青霉素", "磺胺", "阿司匹林", "碘造影剂", "头孢类"])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, ALLERGY_ADD, {'name': name, 'drug': drug})}"),
        _turn(f"确认{name}过敏史已记录，病历保存。"),
    ]


def build_template_20(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """cross_visit: query history + new visit record + followup plan."""
    cc = rng.choice(sc["chief_complaints"])
    days = rng.choice([14, 30])
    return [
        _turn(f"{pick(rng, QUERY_HISTORY, {'name': name})}"),
        _turn(f"今天复诊：{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"{rng.choice(sc['plans'])}。"),
        _turn(f"{pick(rng, SCHEDULE_REMINDER, {'days': days})}"),
        _turn(f"保存{name}本次复诊记录。"),
    ]


def build_template_21(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: update_patient + inline_correction × Post-surgical."""
    cc = rng.choice(sc["chief_complaints"])
    wrong_gender = "女" if gender == "男" else "男"
    return [
        _turn(f"新患者{name}，{wrong_gender}，{age}岁，{cc}。"),
        _turn(f"{pick(rng, CORRECTION_PHRASE)}性别应为{gender}，刚才说错了。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"更新后确认{name}，{gender}，{age}岁，{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_22(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: multi_patient + schedule × Arrhythmia."""
    cc = rng.choice(sc["chief_complaints"])
    days = rng.choice([7, 14, 30])
    return [
        _turn(f"先处理{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, LIST_PATIENTS)}"),
        _turn(f"保存{name}病历，并{pick(rng, SCHEDULE_REMINDER, {'days': days})}"),
        _turn(f"确认{name}档案及复查提醒已设置。"),
    ]


def build_template_23(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: lab_update + correction × Sepsis."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"实验室数值有误，{pick(rng, CORRECTION_PHRASE)}{rng.choice(sc['plans'])}。"),
        _turn(f"确认更正后{name}的数据，{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_24(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: allergy_addendum + cross_visit × CKD."""
    cc = rng.choice(sc["chief_complaints"])
    drug = rng.choice(["青霉素", "磺胺", "阿司匹林", "碘造影剂"])
    return [
        _turn(f"{pick(rng, QUERY_HISTORY, {'name': name})}"),
        _turn(f"今天复诊：{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, ALLERGY_ADD, {'name': name, 'drug': drug})}"),
        _turn(f"保存{name}复诊记录及过敏史更新。"),
    ]


def build_template_25(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: multi_patient + discharge × Mental health."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}，今日出院评估。"),
        _turn(f"{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, LIST_PATIENTS)}"),
        _turn(f"{pick(rng, DISCHARGE_PHRASE)}"),
        _turn(f"确认{name}出院信息及病历归档。"),
    ]


def build_template_26(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: 3patient + export × GI/Hepatic."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"连续三位患者：先{name}，{gender}，{age}岁，{cc}。"),
        _turn(f"第二位，{rng.randint(35, 65)}岁，{sc['name']}随访。"),
        _turn(f"第三位，{rng.randint(35, 65)}岁，{sc['name']}首诊。"),
        _turn(f"为三位均录入：{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, EXPORT_PHRASE, {'name': name})}"),
        _turn(f"确认{name}病历已保存并导出。"),
    ]


def build_template_27(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: task + schedule + cancel × Discharge."""
    cc = rng.choice(sc["chief_complaints"])
    days = rng.choice([7, 14])
    return [
        _turn(f"{pick(rng, TASK_LIST)}"),
        _turn(f"{pick(rng, TASK_COMPLETE)}"),
        _turn(f"新建{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"{pick(rng, SCHEDULE_REMINDER, {'days': days})}"),
        _turn(f"等等，{pick(rng, CANCEL_PHRASE)}"),
        _turn(f"确认{name}病历已保存，任务状态更新。"),
    ]


def build_template_28(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: inline_correction + supplement × Hematology."""
    cc = rng.choice(sc["chief_complaints"])
    detail = rng.choice(sc["details"])
    supp = rng.choice([d for d in sc["details"] if d != detail] or sc["details"])
    return [
        _turn(f"{name}，{gender}，{age + rng.choice([-5, 5])}岁——更正，{age}岁，{cc}。"),
        _turn(f"{detail}。"),
        _turn(f"{pick(rng, SUPPLEMENT)}{supp}。"),
        _turn(f"确认{name}全部信息，{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_29(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: postpone + update × Orthopedic."""
    cc = rng.choice(sc["chief_complaints"])
    days1, days2 = rng.choice([14, 30]), rng.choice([7, 14])
    return [
        _turn(f"{name}，{gender}，{age}岁，{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"建档保存，{pick(rng, SCHEDULE_REMINDER, {'days': days1})}"),
        _turn(f"{pick(rng, POSTPONE_PHRASE, {'days': days2})}"),
        _turn(f"同时更新{name}的康复计划记录，{pick(rng, SAVE_REQUEST)}"),
    ]


def build_template_30(name: str, gender: str, age: int, sc: dict, rng: random.Random) -> list:
    """complex: query + correction + export × Cardiology."""
    cc = rng.choice(sc["chief_complaints"])
    return [
        _turn(f"{pick(rng, QUERY_HISTORY, {'name': name})}"),
        _turn(f"今天：{cc}，{rng.choice(sc['details'])}。"),
        _turn(f"数值更正：{pick(rng, CORRECTION_PHRASE)}{rng.choice(sc['plans'])}。"),
        _turn(f"{pick(rng, EXPORT_PHRASE, {'name': name})}"),
        _turn(f"确认{name}更新记录已保存并导出。"),
    ]


TEMPLATE_BUILDERS = {
    1: build_template_1, 2: build_template_2, 3: build_template_3,
    4: build_template_4, 5: build_template_5, 6: build_template_6,
    7: build_template_7, 8: build_template_8, 9: build_template_9,
    10: build_template_10, 11: build_template_11, 12: build_template_12,
    13: build_template_13, 14: build_template_14, 15: build_template_15,
    16: build_template_16, 17: build_template_17, 18: build_template_18,
    19: build_template_19, 20: build_template_20, 21: build_template_21,
    22: build_template_22, 23: build_template_23, 24: build_template_24,
    25: build_template_25, 26: build_template_26, 27: build_template_27,
    28: build_template_28, 29: build_template_29, 30: build_template_30,
}
