#!/usr/bin/env python3
"""
临床情景模板 A–F：脑卒中、出院小结、慢病管理、术后随访、肿瘤化疗、呼吸科。

由 generate_v2_expansion.py 导入；每个 tmpl_* 函数返回一个病例字典。

Clinical scenario templates A–F for V2 chatlog expansion.
导出：tmpl_stroke, tmpl_discharge, tmpl_chronic, tmpl_postop, tmpl_oncology, tmpl_respiratory
"""

from __future__ import annotations

import random

from tests.fixtures.scripts._generate_v2_phrase_bank import (
    addendum,
    context_summary,
    correction,
    followup_interval,
    imaging_chest,
    lab_hb,
    lab_wbc,
    opening_intro,
    query_history,
    save_command,
    set_reminder,
    vitals_bp,
    vitals_spo2,
    vitals_temp,
)

# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE A – Acute stroke / neuro
# ═══════════════════════════════════════════════════════════════════════════════
STROKE_SYMPTOMS = [
    "{side}侧肢体无力伴言语不清",
    "突发言语含糊，{side}侧面瘫",
    "突发{side}侧肢体麻木，言语困难",
    "突然意识下降，{side}侧偏瘫",
    "急性头痛伴{side}侧肢体乏力",
    "突发{side}侧肢体瘫痪，面部歪斜",
    "口角歪斜，{side}侧上肢力弱",
    "言语不清，伴{side}侧肢体瘫软",
]

STROKE_PLANS = [
    "在溶栓时间窗内，拟行rt-PA静脉溶栓，急查头颅CT。",
    "超过溶栓时间窗，拟行机械取栓评估，联系神经介入。",
    "影像示大面积脑梗死，保守治疗，严密监测颅内压。",
    "请神经介入会诊，评估血管内治疗方案。",
    "出血性卒中，停用抗凝药，神经外科会诊。",
    "桥接治疗：先溶栓再评估取栓。",
    "窗口内，患者家属同意溶栓，准备rt-PA。",
    "小卒中，暂不溶栓，抗血小板治疗+他汀。",
]

STROKE_FOLLOWUP = [
    "安排24小时复查MRI，卒中单元监护。",
    "床旁康复评估，记录神经功能缺损进展。",
    "抗血小板双联治疗，他汀强化，控制血压。",
    "完善颈动脉超声和心脏超声，找病因。",
    "请康复科会诊，制定早期康复计划。",
    "神经内科随访，72小时内复查NIHSS。",
    "补充：血脂四项、同型半胱氨酸、凝血功能。",
    "记录格拉斯哥昏迷评分，每小时观察瞳孔。",
]

STROKE_DETAIL_FRAGMENTS = [
    "既往高血压，未规律服药。",
    "发病时间明确，家属陪同就诊。",
    "合并心房颤动，需评估抗凝。",
    "血糖偏高，注意血糖管理。",
    "无既往卒中病史，首次发病。",
    "烟酒史，颈动脉斑块待查。",
]

def _stroke_turns(
    name: str, gender: str, age: int, symptom: str, nihss_phrase: str,
    detail: str, followup: str, save: str, nihss: int, rng: random.Random,
) -> list:
    """Build turn-sequence options for the stroke template and pick one."""
    intro = opening_intro(name, gender, age, symptom, rng)
    options = [
        [intro, nihss_phrase, followup, save],
        [intro, nihss_phrase, addendum(detail, rng), followup, save],
        [intro, nihss_phrase, query_history(name, rng), followup, save],
        [intro, nihss_phrase, followup,
         context_summary(name, f"{symptom}，NIHSS {nihss}分", rng), save],
        [intro, nihss_phrase, addendum(detail, rng), followup,
         set_reminder(name, "48小时后", rng), save],
    ]
    return rng.choice(options)


def tmpl_stroke(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(48, 84)
    nihss = rng.choice([2, 4, 6, 8, 10, 12, 14, 16, 18])
    side = rng.choice(["左", "右"])
    symptom_raw = rng.choice(STROKE_SYMPTOMS).format(side=side)
    if not symptom_raw.startswith("突发") and not symptom_raw.startswith("突然") and rng.random() < 0.4:
        symptom = f"{symptom_raw}{rng.randint(1, 6)}小时"
    else:
        symptom = symptom_raw

    plan = rng.choice(STROKE_PLANS)
    followup = rng.choice(STROKE_FOLLOWUP)
    detail = rng.choice(STROKE_DETAIL_FRAGMENTS)
    nihss_phrase = rng.choice([
        f"NIHSS评分{nihss}分，{plan}",
        f"入院NIHSS {nihss}分，{plan}",
        f"神经功能评分NIHSS {nihss}，{plan}",
        f"床旁NIHSS {nihss}分。{plan}",
    ])
    chief = rng.choice(["急性卒中", "脑卒中", "偏瘫", "言语不清"])
    save = save_command(name, gender, age, chief, rng)
    turns = _stroke_turns(name, gender, age, symptom, nihss_phrase, detail, followup, save, nihss, rng)
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["NIHSS", "溶栓", "卒中", "肢体", "偏瘫", "脑梗", "rt-PA"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE B – Discharge summary
# ═══════════════════════════════════════════════════════════════════════════════
DISCHARGE_DIAGNOSES = [
    "急性ST段抬高心肌梗死（STEMI），PCI术后恢复",
    "社区获得性肺炎，足疗程抗感染后好转",
    "急性胆囊炎，腹腔镜胆囊切除术后恢复",
    "急性缺血性脑卒中恢复期，早期康复治疗后",
    "2型糖尿病酮症酸中毒，胰岛素方案调整稳定",
    "慢性心力衰竭急性失代偿，利尿脱水治疗后缓解",
    "上消化道出血（胃溃疡），内镜止血成功",
    "急性阑尾炎，腹腔镜阑尾切除术后恢复",
    "急性胰腺炎（轻型），禁食补液治疗后好转",
    "下肢深静脉血栓，抗凝治疗后稳定出院",
    "非ST段抬高心肌梗死（NSTEMI），保守治疗后",
    "高血压危象，静脉降压后血压控制稳定",
]

DISCHARGE_DRUG_PACKS = [
    "阿司匹林100mg qd + 阿托伐他汀40mg qn + 美托洛尔缓释片47.5mg qd",
    "左氧氟沙星500mg qd + 氨溴索30mg tid，疗程共10天",
    "头孢曲松2g qd + 泮托拉唑40mg bid，共7天",
    "氯吡格雷75mg qd + 阿托伐他汀40mg qn + 培哚普利4mg qd",
    "甘精胰岛素16U qn + 二甲双胍500mg bid + 达格列净10mg qd",
    "呋塞米20mg qd + 螺内酯20mg qd + 卡维地洛6.25mg bid + ACEI",
    "华法林（INR目标2.0-3.0）+ 奥美拉唑40mg qd",
    "利伐沙班15mg bid × 3周，后20mg qd维持",
    "厄贝沙坦150mg qd + 氨氯地平5mg qd + 他汀类",
]

DISCHARGE_DIET = [
    "低盐低脂饮食，禁烟酒，规律作息。",
    "低糖低脂饮食，控制热量，每日适度运动。",
    "清淡易消化饮食，避免辛辣刺激，少食多餐。",
    "低蛋白低磷饮食，控制液体入量。",
    "无特殊饮食限制，均衡饮食，禁酒。",
    "低脂低胆固醇饮食，增加膳食纤维。",
]

def _discharge_turns(
    name: str, gender: str, age: int, days: int, diagnosis: str,
    drugs: str, diet: str, fw: str, save: str, rng: random.Random,
) -> list:
    """Build discharge template turn options and pick one."""
    open_v = [
        f"{name}，{gender}，{age}岁，住院{days}天，今日出院，诊断：{diagnosis}。",
        f"帮我写{name}的出院记录，住院{days}天，出院诊断{diagnosis}。",
        f"{name}今天出院，{gender}{age}岁，入院诊断{diagnosis}，共住院{days}天。",
        f"出院病历：{name}，{gender}，{age}岁，诊断{diagnosis}，住院{days}天好转出院。",
    ]
    drug_v = [
        f"带药：{drugs}，出院医嘱：{diet}",
        f"出院用药：{drugs}。饮食指导：{diet}",
        f"开具出院处方：{drugs}。同时嘱咐患者：{diet}",
        f"医嘱用药{drugs}，生活方式：{diet}",
    ]
    fw_v = [
        f"{fw}门诊复查，如症状加重立即就诊。",
        f"门诊随访：{fw}复查，不适随诊。",
        f"嘱{fw}来院复查，不舒服随时急诊。",
        f"随访计划：{fw}，如有胸痛/气短立即就医。",
    ]
    options = [
        [rng.choice(open_v), rng.choice(drug_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(drug_v), rng.choice(fw_v),
         context_summary(name, f"住院{days}天，{diagnosis[:6]}，出院用药已开具", rng), save],
        [rng.choice(open_v), addendum("此次住院期间完善了相关检查，结果存档", rng),
         rng.choice(drug_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(drug_v), set_reminder(name, fw, rng), rng.choice(fw_v), save],
    ]
    return rng.choice(options)


def tmpl_discharge(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(36, 80)
    days = rng.randint(3, 18)
    diagnosis = rng.choice(DISCHARGE_DIAGNOSES)
    drugs = rng.choice(DISCHARGE_DRUG_PACKS)
    diet = rng.choice(DISCHARGE_DIET)
    fw = followup_interval(rng.choice([1, 2, 4]), rng)
    chief = rng.choice(["出院", "住院治疗后出院", diagnosis[:4]])
    save = save_command(name, gender, age, chief, rng)
    turns = _discharge_turns(name, gender, age, days, diagnosis, drugs, diet, fw, save, rng)
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["出院", "随访", "带药", "复查", "医嘱", "门诊", "出院诊断"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE C – Chronic disease: DM + HTN
# ═══════════════════════════════════════════════════════════════════════════════
DM_INSULIN_ACTIONS = [
    "胰岛素剂量上调4U",
    "加用SGLT-2抑制剂恩格列净10mg",
    "调整为GLP-1受体激动剂司美格鲁肽0.5mg周注射",
    "维持现有口服药方案，加强饮食控制",
    "停用磺脲类，改用DPP-4抑制剂西格列汀",
    "启用胰岛素泵，基础量调整",
    "加用阿卡波糖50mg tid餐中嚼服",
    "改用预混胰岛素30R早晚注射",
]

HTN_ACTIONS = [
    "加用氨氯地平5mg qd",
    "ACEI剂量加倍，培哚普利4→8mg",
    "加用吲达帕胺缓释片1.5mg qd",
    "降压方案暂不调整，监测血压",
    "换用ARB类，缬沙坦80mg qd",
    "加用β受体阻滞剂比索洛尔",
    "联合用药：ACEI + CCB",
    "复方降压胶囊改为规范单药",
]

DM_COMPLICATIONS_CHECK = [
    "今日做眼底检查和足底神经感觉评估。",
    "完善尿微量白蛋白和尿肌酐比值。",
    "复查24小时尿蛋白，排查糖尿病肾病。",
    "检查足背动脉搏动，评估外周血管。",
    "安排眼科会诊，评估糖尿病视网膜病变。",
    "今日心电图检查，评估心肌缺血。",
]

def _chronic_turns(
    name: str, gender: str, age: int, hba1c: float, sbp: int, dbp: int,
    fg: float, pp_glucose: float, insulin_action: str, bp_action: str,
    complication_check: str, fw_months: int, save: str, rng: random.Random,
) -> list:
    """Build chronic disease template turn options and pick one."""
    bp_str = vitals_bp(sbp, dbp, rng)
    open_v = [
        f"{name}，{gender}，{age}岁，2型糖尿病+高血压随访，空腹血糖{fg}mmol/L，{bp_str}。",
        f"{name}慢病随访，{age}岁，血糖{fg}（空腹），餐后{pp_glucose}，血压{sbp}/{dbp}。",
        f"今天{name}来门诊了，{gender}{age}，DM2+HTN随访，FBG {fg}，{bp_str}。",
        f"复诊：{name}，{gender}，{age}岁，糖尿病高血压患者，空腹糖{fg}mmol，血压{sbp}/{dbp}mmHg。",
    ]
    dm_v = [
        f"HbA1c {hba1c}%，{insulin_action}；血压控制不佳，{bp_action}。",
        f"糖化血红蛋白{hba1c}%，较上次{'改善' if hba1c < 8 else '升高'}，{insulin_action}。血压：{bp_action}。",
        f"HbA1c回来了，{hba1c}%，血糖{insulin_action}，降压方面{bp_action}。",
        f"化验结果：HbA1c {hba1c}%，血脂偏高，{insulin_action}。同时{bp_action}。",
    ]
    fw_v = [
        f"{followup_interval(fw_months * 4, rng)}复查HbA1c和肾功能，{complication_check}",
        f"安排{fw_months}个月后复查，{complication_check}。嘱患者记录血压日志。",
        f"下次就诊{followup_interval(fw_months * 4, rng)}，复查空腹血糖、HbA1c、肾功。{complication_check}",
    ]
    options = [
        [rng.choice(open_v), rng.choice(dm_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(dm_v),
         addendum("嘱患者低盐低糖饮食，每天步行30分钟", rng), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(dm_v), rng.choice(fw_v),
         set_reminder(name, f"{fw_months}个月后", rng), save],
        [rng.choice(open_v), query_history(name, rng), rng.choice(dm_v), rng.choice(fw_v), save],
    ]
    return rng.choice(options)


def tmpl_chronic(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(43, 74)
    hba1c = round(rng.uniform(6.2, 12.0), 1)
    sbp, dbp = rng.randint(126, 182), rng.randint(80, 115)
    fg = round(rng.uniform(6.0, 15.5), 1)
    pp_glucose = round(fg + rng.uniform(3.0, 6.0), 1)
    insulin_action = rng.choice(DM_INSULIN_ACTIONS)
    bp_action = rng.choice(HTN_ACTIONS)
    complication_check = rng.choice(DM_COMPLICATIONS_CHECK)
    fw_months = rng.choice([1, 2, 3])
    chief = rng.choice(["血糖管理", "慢病随访", "糖尿病高血压随访"])
    save = save_command(name, gender, age, chief, rng)
    turns = _chronic_turns(
        name, gender, age, hba1c, sbp, dbp, fg, pp_glucose,
        insulin_action, bp_action, complication_check, fw_months, save, rng,
    )
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["血糖", "HbA1c", "血压", "糖尿病", "胰岛素", "降压", "DM"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE D – Post-operative follow-up
# ═══════════════════════════════════════════════════════════════════════════════
SURGERIES = [
    "腹腔镜阑尾切除术",
    "腹腔镜胆囊切除术",
    "冠状动脉旁路移植术（CABG）",
    "全膝关节置换术（TKA）",
    "胃癌根治术（D2切除）",
    "腰椎间盘摘除+椎管减压术",
    "甲状腺全切+淋巴结清扫术",
    "肝右叶部分切除术",
    "结肠癌根治术",
    "前列腺根治性切除术（RARP）",
    "髋关节置换术（THA）",
    "子宫全切术（腹腔镜）",
]

WOUND_STATUS = [
    "切口愈合良好，无渗出，无红肿",
    "切口少量浆液性渗出，已换药处理",
    "切口局部红肿，考虑浅表感染，加强换药",
    "切口干燥清洁，拆线后愈合佳",
    "腹腔镜孔口愈合可，无渗液",
    "引流口周围皮肤轻度红斑",
]

DRAIN_STATUS = [
    "引流管已于今日拔除",
    lambda rng: f"引流量{rng.randint(10, 70)}ml/24h，计划明日拔除",
    "引流管通畅，引流液为淡血性浆液",
    "无引流管，无明显积液",
    lambda rng: f"引流量{rng.randint(80, 200)}ml/24h，暂不拔管",
]

POSTOP_COMPLICATIONS = [
    "体温正常，无发热，肠鸣音恢复。",
    "轻度腹胀，予促胃肠动力药，肛门已排气。",
    "血压偏低，补液支持，监测心率。",
    "血常规正常，无感染迹象。",
    "轻度贫血，Hb{hb}g/L，暂不输血。",
    "DVT预防：低分子肝素+弹力袜，早期下床活动。",
    "肺功能锻炼：呼吸训练器每小时使用。",
]

def _postop_turns(
    name: str, gender: str, age: int, surgery: str, op_day: int, wound: str,
    drain: str, pain: int, hb_val: int, complication: str, save: str, rng: random.Random,
) -> list:
    """Build post-op template turn options and pick one."""
    op_day_zh = ["一", "二", "三", "四", "五", "六", "七", "八"][min(op_day - 1, 7)]
    open_v = [
        f"{name}，{gender}，{age}岁，{surgery}术后第{op_day}天，{wound}。",
        f"术后查房：{name}，{surgery}后D{op_day}，{wound}。",
        f"{name}，{op_day_zh}术后，{surgery}，切口情况：{wound}。",
        f"帮我记{name}的术后记录，{gender}{age}岁，{surgery}术后第{op_day}天。",
    ]
    pain_v = [
        f"疼痛NRS评分{pain}分，{drain}，镇痛继续。",
        f"疼痛{pain}/10，{drain}，维持现有镇痛方案。",
        f"{drain}。疼痛评分{pain}分，患者可耐受。",
        f"患者诉疼痛{pain}分，{drain}，处理方案不变。",
    ]
    rehab_v = [
        f"{complication}明日开始早期康复训练，预计{rng.randint(2, 5)}天后出院。",
        f"{complication}康复科会诊，{rng.randint(2, 5)}天后可出院。",
        f"已请康复科评估，{complication}计划住院{rng.randint(2, 5)}天后出院。",
    ]
    options = [
        [rng.choice(open_v), rng.choice(pain_v), rng.choice(rehab_v), save],
        [rng.choice(open_v), rng.choice(pain_v),
         addendum(f"今日复查血常规：Hb {hb_val}g/L，WBC正常", rng), rng.choice(rehab_v), save],
        [rng.choice(open_v), rng.choice(pain_v), rng.choice(rehab_v),
         set_reminder(name, f"{rng.randint(2, 4)}天后", rng), save],
        [rng.choice(open_v), rng.choice(pain_v), rng.choice(rehab_v),
         context_summary(name, f"{surgery}术后第{op_day}天，{wound[:6]}，NRS {pain}分", rng), save],
    ]
    return rng.choice(options)


def tmpl_postop(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(30, 74)
    op_day = rng.randint(1, 8)
    surgery = rng.choice(SURGERIES)
    wound = rng.choice(WOUND_STATUS)
    drain_raw = rng.choice(DRAIN_STATUS)
    drain = drain_raw(rng) if callable(drain_raw) else drain_raw
    pain = rng.randint(1, 6)
    hb_val = rng.randint(82, 130)
    complication = rng.choice(POSTOP_COMPLICATIONS).format(hb=hb_val)
    chief = rng.choice(["术后恢复", f"{surgery[:4]}术后", "外科术后随访"])
    save = save_command(name, gender, age, chief, rng)
    turns = _postop_turns(name, gender, age, surgery, op_day, wound, drain, pain, hb_val, complication, save, rng)
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["术后", "切口", "引流", "康复", "疼痛", "NRS", "手术"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE E – Oncology / chemotherapy
# ═══════════════════════════════════════════════════════════════════════════════
CANCERS = [
    "乳腺癌（HER2阳性）",
    "肺腺癌（EGFR突变）",
    "结肠腺癌（MSS型）",
    "弥漫大B细胞淋巴瘤",
    "胃腺癌（Lauren弥漫型）",
    "卵巢上皮性癌（BRCA1突变）",
    "宫颈鳞癌（IIB期）",
    "肝细胞肝癌（BCLC B期）",
    "非小细胞肺癌（鳞癌）",
    "多发性骨髓瘤",
]

CHEMO_REGIMENS = [
    "TC方案（紫杉醇+卡铂）",
    "FOLFOX方案（奥沙利铂+5-FU+亚叶酸钙）",
    "R-CHOP方案（利妥昔单抗+CHOP）",
    "AC-T方案（蒽环类序贯紫杉类）",
    "SOX方案（替吉奥+奥沙利铂）",
    "BEP方案（博来霉素+依托泊苷+顺铂）",
    "单药培美曲塞+卡铂",
    "奥希替尼靶向单药治疗",
    "帕博利珠单抗免疫治疗",
]

TOXICITIES = [
    "恶心呕吐3级，予昂丹司琼8mg q8h止吐",
    "骨髓抑制II度，中性粒细胞减少，发热性中性粒细胞减少症（FN）",
    "外周神经毒性1-2级，手足麻木，步态轻度不稳",
    "口腔黏膜炎2级，予漱口液每日3次",
    "疲劳乏力，KPS评分从80降至70",
    "脱发2级，情绪低落，给予心理支持",
    "腹泻3级，洛哌丁胺处理，注意水电解质补充",
    "肝功能轻度异常，ALT升至正常上限2倍",
    "皮疹2级（靶向药相关），外用糖皮质激素",
]

CHEMO_ACTIONS = [
    "予重组人粒细胞刺激因子（G-CSF）升白，5天后复查血象",
    "延迟下一疗程7-14天，待血象恢复后继续",
    "按原方案继续，同时加强支持治疗",
    "奥沙利铂减量20%继续，其余不变",
    "暂停化疗，营养支持为主，待患者恢复",
    "更换方案：改用二线紫杉醇单药",
    "联合应用止吐三联方案，预防下周期呕吐",
]

def _oncology_turns(
    name: str, gender: str, age: int, cancer: str, regimen: str, cycle: int,
    day_after: int, toxicity: str, wbc_v: float, hb_v: int, plt_v: int,
    action: str, save: str, rng: random.Random,
) -> list:
    """Build oncology template turn options and pick one."""
    wbc_str = lab_wbc(wbc_v, rng)
    hb_str = lab_hb(hb_v, rng)
    open_v = [
        f"{name}，{gender}，{age}岁，{cancer}，{regimen}第{cycle}周期，化疗后第{day_after}天，{toxicity}。",
        f"{name}来随访了，{cancer}化疗第{cycle}疗程后D{day_after}，{toxicity}。",
        f"肿瘤科随访：{name}，{gender}{age}，{cancer}，第{cycle}次化疗（{regimen}）后{day_after}天，{toxicity}。",
        f"记录{name}化疗副反应，{cancer}，{cycle}疗程，第{day_after}天，{toxicity}。",
    ]
    lab_v = [
        f"血常规：{wbc_str}，{hb_str}，PLT {plt_v}×10⁹/L，{action}。",
        f"化验：{wbc_str}，Hb {hb_v}，PLT {plt_v}，{action}。",
        f"血象：白血胞{wbc_v}，血红蛋白{hb_v}g/L，血小板{plt_v}，{action}。",
    ]
    fw_v = [
        "记录本疗程耐受情况和毒副反应等级，下次化疗前24小时复查血象。",
        "下周期前评估血象，同时复查肝肾功能和肿瘤标志物。",
        f"纳入化疗毒性记录：Grade{'I' if wbc_v > 2 else 'II'}，{followup_interval(2, rng)}复查。",
        "记录本次不良反应，评估是否需要调整下一周期化疗方案。",
    ]
    options = [
        [rng.choice(open_v), rng.choice(lab_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(lab_v),
         addendum(f"患者体重较上次下降{rng.randint(1, 4)}kg，营养支持评估", rng),
         rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(lab_v), rng.choice(fw_v),
         set_reminder(name, f"{rng.choice(['下周', '5天后', '1周后'])}血象复查", rng), save],
        [rng.choice(open_v), query_history(name, rng), rng.choice(lab_v), rng.choice(fw_v), save],
    ]
    return rng.choice(options)


def tmpl_oncology(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(36, 74)
    cycle = rng.randint(1, 8)
    cancer = rng.choice(CANCERS)
    regimen = rng.choice(CHEMO_REGIMENS)
    day_after = rng.choice([3, 5, 7, 10, 14])
    wbc_v = round(rng.uniform(0.8, 4.8), 1)
    hb_v, plt_v = rng.randint(68, 128), rng.randint(38, 210)
    toxicity = rng.choice(TOXICITIES)
    action = rng.choice(CHEMO_ACTIONS)
    chief = rng.choice(["化疗随访", "肿瘤化疗", f"{cancer[:3]}化疗"])
    save = save_command(name, gender, age, chief, rng)
    turns = _oncology_turns(
        name, gender, age, cancer, regimen, cycle, day_after, toxicity,
        wbc_v, hb_v, plt_v, action, save, rng,
    )
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["化疗", "血象", "白细胞", "骨髓抑制", "疗程", "WBC", "肿瘤"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE F – Respiratory / pulmonology
# ═══════════════════════════════════════════════════════════════════════════════
RESP_SYMPTOMS = [
    lambda rng: f"咳嗽咳黄脓痰{rng.randint(3, 12)}天，{vitals_temp(round(rng.uniform(38.0, 39.8), 1), rng)}",
    lambda rng: "活动后气促进行性加重，平地步行100m即感气短",
    lambda rng: "急性喘息发作，呼气相哮鸣音明显，既往哮喘史",
    lambda rng: f"痰中带血{rng.randint(1, 7)}天，鲜血或血丝痰",
    lambda rng: "COPD急性加重（AECOPD），呼吸困难加重，痰量增多变黄",
    lambda rng: "胸痛伴突发呼吸困难，怀疑急性肺栓塞，D-dimer升高",
    lambda rng: "反复发热咳嗽1个月，CT示右下肺结节，疑肺结核",
    lambda rng: f"胸腔积液，{rng.choice(['右侧', '左侧', '双侧'])}中等量，呼吸困难",
]

ANTIBIOTICS = [
    "头孢他啶2g q12h静脉滴注",
    "莫西沙星400mg qd口服/静脉",
    "哌拉西林他唑巴坦4.5g q8h",
    "阿奇霉素500mg qd + 头孢曲松2g qd",
    "亚胺培南西司他丁0.5g q6h",
    "左氧氟沙星500mg qd",
    "头孢呋辛1.5g q8h",
    "利奈唑胺600mg q12h（MRSA覆盖）",
]

O2_SUPPORT = [
    "鼻导管给氧2-3L/min",
    "面罩给氧5-8L/min，目标SpO₂>95%",
    "无创正压通气（BIPAP），S/T模式",
    "高流量湿化氧疗（HFNC），FiO₂ 40-50%",
    "经鼻高流量氧疗30L/min",
    "暂不需要氧疗，SpO₂维持正常",
]

RESP_IMAGING = [
    "右下肺浸润影，考虑肺炎",
    "双肺弥漫磨玻璃影，不除外病毒性肺炎",
    "左肺下叶实变，支气管充气征阳性",
    "肺气肿背景，右下肺浸润加重",
    "肺动脉主干增宽，肺栓塞待查，CTA进一步确认",
    "右侧大量胸腔积液，心脏移位",
    "气胸，右肺压缩30%",
]

def _respiratory_turns(
    name: str, gender: str, age: int, symptom: str, spo2: int,
    antibiotic: str, o2: str, imaging_finding: str, save: str, rng: random.Random,
) -> list:
    """Build respiratory template turn options and pick one."""
    spo2_str = vitals_spo2(spo2, rng)
    open_v = [
        f"{name}，{gender}，{age}岁，{symptom}，{spo2_str}入院。",
        f"收治{name}，{gender}{age}岁，{symptom}，血氧{spo2}%。",
        f"呼吸科新收患者{name}，{age}岁，{symptom}，SpO₂ {spo2}%。",
        f"急诊入院：{name}，{gender}，{age}，{symptom}，氧饱和{spo2}%。",
    ]
    treat_v = [
        f"{imaging_chest(imaging_finding, rng)}，予{antibiotic}抗感染，{o2}。",
        f"影像：{imaging_finding}。开始{antibiotic}，辅助{o2}。",
        f"{antibiotic}抗感染治疗，{o2}，{imaging_finding}（影像）。",
        f"治疗方案：{antibiotic} + {o2}。胸片/CT：{imaging_finding}。",
    ]
    fw_v = [
        "48小时后复查血常规、CRP和胸片，监测体温和氧合趋势。",
        "24-48h评估疗效，复查血常规、PCT，必要时升阶梯抗生素。",
        "每日监测体温、SpO₂和痰液变化，3天无效则考虑换药。",
        "记录本次呼吸道感染评分，规划抗生素疗程和出院节点。",
    ]
    options = [
        [rng.choice(open_v), rng.choice(treat_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(treat_v),
         addendum(f"患者既往{rng.choice(['COPD', '哮喘', '高血压', '糖尿病', '无特殊病史'])}", rng),
         rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(treat_v), rng.choice(fw_v),
         set_reminder(name, "48小时后", rng), save],
        [rng.choice(open_v), query_history(name, rng), rng.choice(treat_v), rng.choice(fw_v), save],
        [rng.choice(open_v), rng.choice(treat_v), correction("抗生素", antibiotic, rng), rng.choice(fw_v), save],
    ]
    return rng.choice(options)


def tmpl_respiratory(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(40, 84)
    spo2 = rng.randint(83, 97)
    symptom = rng.choice(RESP_SYMPTOMS)(rng)
    antibiotic = rng.choice(ANTIBIOTICS)
    o2 = rng.choice(O2_SUPPORT)
    imaging_finding = rng.choice(RESP_IMAGING)
    chief = rng.choice(["肺炎", "呼吸道感染", "COPD急性加重", symptom[:4]])
    save = save_command(name, gender, age, chief, rng)
    turns = _respiratory_turns(name, gender, age, symptom, spo2, antibiotic, o2, imaging_finding, save, rng)
    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {},
            "must_include_any_of": [["咳嗽", "肺炎", "SpO", "抗生素", "胸片", "气促", "COPD", "氧疗"]],
        },
    }


