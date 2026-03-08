#!/usr/bin/env python3
"""
Expand realworld_doctor_agent_chatlogs_e2e_v2.json from 100 → 1000 cases (10x).

10 new clinical scenario types (90 cases each):
  A - Stroke / Neuro
  B - Discharge summary
  C - Diabetes + Hypertension management
  D - Post-operative follow-up
  E - Oncology / Chemotherapy tracking
  F - Respiratory / Pulmonology
  G - Arrhythmia management
  H - Sepsis / Critical care
  I - CKD / Renal
  J - Mental health

Grammar & word bank:
- Multiple opening / middle / closing frame variants per template
- Shared phrase banks: casual, abbreviated, mixed-lang, self-correction, addendum
- 4–6 turn chatlogs (varied length)
- Real doctor speech register: telegraphic, formal, mid-sentence corrections
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = (
    ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v2.json"
)

# ═══════════════════════════════════════════════════════════════════════════════
# NAME POOL
# ═══════════════════════════════════════════════════════════════════════════════
SURNAMES = [
    "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴",
    "徐", "孙", "胡", "朱", "高", "林", "何", "郭", "马", "罗",
    "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧",
    "程", "曹", "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕",
    "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛", "叶", "阎",
    "余", "潘", "杜", "戴", "夏", "钟", "汪", "田", "任", "姜",
    "范", "方", "石", "姚", "谭", "廖", "邹", "熊", "金", "陆",
    "郝", "孔", "白", "崔", "康", "毛", "邱", "秦", "江", "史",
    "顾", "侯", "邵", "孟", "龙", "万", "段", "雷", "钱", "汤",
    "尹", "黎", "易", "常", "武", "乔", "贺", "赖", "龚", "文",
    "施", "洪", "褚", "卫", "蒲", "华", "向", "鲁", "水", "连",
]

GIVEN = [
    # male-leaning
    "博", "强", "军", "明", "勇", "超", "峰", "辉", "刚", "宇",
    "建", "杰", "飞", "浩", "磊", "亮", "斌", "平", "涛", "鹏",
    "东", "凯", "坤", "成", "海", "波", "昊", "锋", "虎", "旭",
    "阳", "宁", "锐", "翔", "健", "庆", "恒", "晟", "睿", "煜",
    "轩", "泽", "昕", "旻", "晨", "浚", "霖", "烨", "晖", "煦",
    "鑫", "炜", "彬", "俊", "威", "诚", "铭", "航", "驰", "远",
    "志", "国", "天", "文", "大", "少", "正", "新", "永", "荣",
    # female-leaning
    "芳", "娜", "燕", "英", "霞", "洁", "玲", "红", "丽", "雪",
    "静", "晴", "婷", "菊", "梅", "云", "慧", "萍", "莹", "悦",
    "蕾", "珊", "欣", "雯", "嫣", "桂", "秀", "琴", "花", "莲",
    "瑶", "漫", "璐", "岚", "淑", "苗", "彩", "凤", "娇", "媛",
    "娟", "倩", "丽", "慧", "敏", "然", "冰", "月", "雁", "青",
]

GIVEN_2CHAR = [
    # two-character given names for diversity
    "志远", "明杰", "国强", "东阳", "文斌", "海涛", "建军", "振宇", "晓峰",
    "天明", "永锋", "少华", "云辉", "泽宇", "浩轩", "国辉", "思远", "博文",
    "嘉豪", "俊熙", "子轩", "宇航", "靖远", "梓豪", "晓薇", "思怡", "雨桐",
    "欣怡", "梦琪", "晓雯", "紫涵", "芷若", "雨欣", "婉仪", "晨曦", "芸菲",
]


def gen_unique_names(n: int, rng: random.Random) -> list[str]:
    """Generate n unique 2- or 3-character Chinese names."""
    seen: set[str] = set()
    result: list[str] = []
    attempts = 0
    # mix 2-char and 3-char names at ~80/20
    while len(result) < n and attempts < n * 200:
        attempts += 1
        if rng.random() < 0.2 and GIVEN_2CHAR:
            name = rng.choice(SURNAMES) + rng.choice(GIVEN_2CHAR)
        else:
            name = rng.choice(SURNAMES) + rng.choice(GIVEN)
        if name not in seen:
            seen.add(name)
            result.append(name)
    for i in range(len(result), n):
        result.append(f"患{i:04d}")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED PHRASE BANKS
# ═══════════════════════════════════════════════════════════════════════════════

# ── Ways a doctor introduces / opens a case ───────────────────────────────────
def opening_intro(name: str, gender: str, age: int, symptom: str, rng: random.Random) -> str:
    g_zh = "男性" if gender == "男" else "女性"
    patterns = [
        f"{name}，{gender}，{age}岁，{symptom}，急诊入院。",
        f"先记一下：{name}，{age}岁{g_zh}，{symptom}。",
        f"帮我建个档：{name}，{gender}{age}岁，{symptom}。",
        f"{name}这个患者，{age}岁，{symptom}，刚收进来。",
        f"新收患者{name}，{gender}，{age}岁，主诉{symptom}，请先记录。",
        f"{name}，{symptom}，{gender}{age}岁，今天来急诊的。",
        f"快速记一下：{name}，{g_zh}，{age}岁，{symptom}。",
        f"患者{name}，{age}岁，{gender}，主诉：{symptom}。",
    ]
    return rng.choice(patterns)


# ── Ways a doctor appends/corrects mid-note ───────────────────────────────────
def addendum(detail: str, rng: random.Random) -> str:
    patterns = [
        f"补充一下：{detail}",
        f"刚想到，{detail}",
        f"再加上：{detail}",
        f"另外，{detail}",
        f"对了，还有{detail}",
        f"顺便记：{detail}",
        f"附加信息：{detail}",
        f"还需要记录：{detail}",
    ]
    return rng.choice(patterns)


# ── Ways a doctor gives a correction ─────────────────────────────────────────
def correction(old_val: str, new_val: str, rng: random.Random) -> str:
    patterns = [
        f"更正一下，{old_val}说错了，应该是{new_val}。",
        f"刚才{old_val}记错了，改成{new_val}。",
        f"不对，{old_val}那里改一下：{new_val}。",
        f"{old_val}有误，正确是{new_val}，帮我改掉。",
        f"我口误了，{old_val}应为{new_val}。",
    ]
    return rng.choice(patterns)


# ── Ways a doctor queries history ────────────────────────────────────────────
def query_history(name: str, rng: random.Random) -> str:
    patterns = [
        f"顺便查一下{name}的历史病历。",
        f"看一下{name}有没有既往记录。",
        f"调取{name}的门诊记录。",
        f"帮我拉{name}的历史就诊情况。",
        f"先查{name}的用药记录和既往诊断。",
    ]
    return rng.choice(patterns)


# ── Ways to request a reminder / follow-up task ──────────────────────────────
def set_reminder(name: str, when: str, rng: random.Random) -> str:
    patterns = [
        f"帮{name}设一个{when}的复查提醒。",
        f"记一个提醒：{name}，{when}复查。",
        f"给{name}创建{when}随访任务。",
        f"{name}需要{when}复诊，帮我记上。",
        f"任务：{when}跟进{name}复查。",
    ]
    return rng.choice(patterns)


# ── Save / close commands ─────────────────────────────────────────────────────
def save_command(name: str, gender: str, age: int, chief: str, rng: random.Random) -> str:
    patterns = [
        f"请明确执行：新建患者{name}，{gender}{age}岁，主诉{chief}，并保存本次病历。",
        f"确认患者{name}，主诉{chief}，请建档并保存本次病历。",
        f"好，把{name}的病历保存了，主诉{chief}。",
        f"帮我把刚才{name}的记录存档，主诉{chief}。",
        f"{name}的记录整理好了，存一下，主诉{chief}。",
        f"保存{name}本次就诊记录，{gender}{age}岁，主诉{chief}。",
        f"请新建{name}并保存这次病历，主诉{chief}。",
        f"{name}，{gender}，{age}岁，今日主诉{chief}，建档保存。",
    ]
    return rng.choice(patterns)


# ── Context-summary phrases ───────────────────────────────────────────────────
def context_summary(name: str, summary: str, rng: random.Random) -> str:
    patterns = [
        f"总结上下文：{name}本次就诊重点是{summary}。",
        f"记录摘要：{name}，{summary}。",
        f"保存上下文：{name}，{summary}，纳入结构化病历。",
        f"这次{name}的核心问题是{summary}，记录清楚。",
    ]
    return rng.choice(patterns)


# ═══════════════════════════════════════════════════════════════════════════════
# CLINICAL WORD BANKS (shared across templates)
# ═══════════════════════════════════════════════════════════════════════════════

# Vital sign phrasings
def vitals_bp(sbp: int, dbp: int, rng: random.Random) -> str:
    return rng.choice([
        f"血压{sbp}/{dbp}mmHg",
        f"BP {sbp}/{dbp}",
        f"血压测得{sbp}/{dbp}",
        f"收缩压{sbp}，舒张压{dbp}",
    ])

def vitals_hr(hr: int, rng: random.Random) -> str:
    return rng.choice([
        f"心率{hr}次/分",
        f"HR {hr}bpm",
        f"脉搏{hr}次/分",
        f"心率{hr}",
    ])

def vitals_spo2(spo2: int, rng: random.Random) -> str:
    return rng.choice([
        f"SpO₂ {spo2}%",
        f"血氧{spo2}%",
        f"氧饱和度{spo2}%",
        f"指脉氧{spo2}",
    ])

def vitals_temp(temp: float, rng: random.Random) -> str:
    return rng.choice([
        f"体温{temp}℃",
        f"T {temp}℃",
        f"发热，体温{temp}度",
        f"热峰{temp}℃",
    ])

# Follow-up interval phrasings
def followup_interval(weeks: int, rng: random.Random) -> str:
    if weeks == 1:
        return rng.choice(["1周后", "下周", "7天后", "一周内"])
    elif weeks == 2:
        return rng.choice(["2周后", "半月后", "14天后"])
    elif weeks == 4:
        return rng.choice(["1个月后", "4周后", "下月"])
    elif weeks == 3:
        return rng.choice(["3个月后", "季度复查"])
    return f"{weeks}周后"

# Lab value phrasings
def lab_wbc(wbc: float, rng: random.Random) -> str:
    return rng.choice([
        f"WBC {wbc}×10⁹/L",
        f"白细胞{wbc}",
        f"白血球计数{wbc}×10⁹",
    ])

def lab_hb(hb: int, rng: random.Random) -> str:
    return rng.choice([
        f"Hb {hb}g/L",
        f"血红蛋白{hb}",
        f"Hemoglobin {hb}g/L",
    ])

def lab_creatinine(cr: int, rng: random.Random) -> str:
    return rng.choice([
        f"肌酐{cr}μmol/L",
        f"Cr {cr}",
        f"血肌酐{cr}μmol",
        f"肾功肌酐{cr}",
    ])

# Drug prescription phrasings
def rx(drug: str, dose: str, freq: str, rng: random.Random) -> str:
    return rng.choice([
        f"{drug} {dose} {freq}",
        f"开{drug} {dose}，{freq}口服",
        f"予{drug} {dose} {freq}",
        f"处方{drug} {dose} {freq}",
    ])

# Imaging result phrasings
def imaging_chest(finding: str, rng: random.Random) -> str:
    return rng.choice([
        f"胸片提示{finding}",
        f"CT示{finding}",
        f"影像：{finding}",
        f"胸部X线：{finding}",
        f"肺部CT：{finding}",
    ])

# Generic recording phrases
def record_note(detail: str, rng: random.Random) -> str:
    return rng.choice([
        f"记录：{detail}",
        f"写进病历：{detail}",
        f"备注：{detail}",
        f"补充记录：{detail}",
        f"纳入本次病历：{detail}",
    ])


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

def tmpl_stroke(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(48, 84)
    nihss = rng.choice([2, 4, 6, 8, 10, 12, 14, 16, 18])
    side = rng.choice(["左", "右"])
    symptom_raw = rng.choice(STROKE_SYMPTOMS).format(side=side)
    # 30% chance: symptom starts with "突发" already, otherwise add onset prefix
    if not symptom_raw.startswith("突发") and not symptom_raw.startswith("突然") and rng.random() < 0.4:
        onset_hour = rng.randint(1, 6)
        symptom = f"{symptom_raw}{onset_hour}小时"
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

    turns_options = [
        # 4-turn
        [
            opening_intro(name, gender, age, symptom, rng),
            nihss_phrase,
            followup,
            save,
        ],
        # 5-turn: add detail fragment
        [
            opening_intro(name, gender, age, symptom, rng),
            nihss_phrase,
            addendum(detail, rng),
            followup,
            save,
        ],
        # 5-turn: history query
        [
            opening_intro(name, gender, age, symptom, rng),
            nihss_phrase,
            query_history(name, rng),
            followup,
            save,
        ],
        # 5-turn: context summary
        [
            opening_intro(name, gender, age, symptom, rng),
            nihss_phrase,
            followup,
            context_summary(name, f"{symptom}，NIHSS {nihss}分", rng),
            save,
        ],
        # 6-turn: full
        [
            opening_intro(name, gender, age, symptom, rng),
            nihss_phrase,
            addendum(detail, rng),
            followup,
            set_reminder(name, "48小时后", rng),
            save,
        ],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

def tmpl_discharge(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(36, 80)
    days = rng.randint(3, 18)
    diagnosis = rng.choice(DISCHARGE_DIAGNOSES)
    drugs = rng.choice(DISCHARGE_DRUG_PACKS)
    diet = rng.choice(DISCHARGE_DIET)
    fw_weeks = rng.choice([1, 2, 4])
    fw = followup_interval(fw_weeks, rng)

    # Opening variants for discharge
    open_variants = [
        f"{name}，{gender}，{age}岁，住院{days}天，今日出院，诊断：{diagnosis}。",
        f"帮我写{name}的出院记录，住院{days}天，出院诊断{diagnosis}。",
        f"{name}今天出院，{gender}{age}岁，入院诊断{diagnosis}，共住院{days}天。",
        f"出院病历：{name}，{gender}，{age}岁，诊断{diagnosis}，住院{days}天好转出院。",
    ]
    drug_variants = [
        f"带药：{drugs}，出院医嘱：{diet}",
        f"出院用药：{drugs}。饮食指导：{diet}",
        f"开具出院处方：{drugs}。同时嘱咐患者：{diet}",
        f"医嘱用药{drugs}，生活方式：{diet}",
    ]
    fw_variants = [
        f"{fw}门诊复查，如症状加重立即就诊。",
        f"门诊随访：{fw}复查，不适随诊。",
        f"嘱{fw}来院复查，不舒服随时急诊。",
        f"随访计划：{fw}，如有胸痛/气短立即就医。",
    ]

    chief = rng.choice(["出院", "住院治疗后出院", diagnosis[:4]])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(drug_variants), rng.choice(fw_variants), save],
        [rng.choice(open_variants), rng.choice(drug_variants), rng.choice(fw_variants),
         context_summary(name, f"住院{days}天，{diagnosis[:6]}，出院用药已开具", rng), save],
        [rng.choice(open_variants), addendum(f"此次住院期间完善了相关检查，结果存档", rng),
         rng.choice(drug_variants), rng.choice(fw_variants), save],
        [rng.choice(open_variants), rng.choice(drug_variants),
         set_reminder(name, fw, rng), rng.choice(fw_variants), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

def tmpl_chronic(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(43, 74)
    hba1c = round(rng.uniform(6.2, 12.0), 1)
    sbp = rng.randint(126, 182)
    dbp = rng.randint(80, 115)
    fg = round(rng.uniform(6.0, 15.5), 1)
    pp_glucose = round(fg + rng.uniform(3.0, 6.0), 1)
    insulin_action = rng.choice(DM_INSULIN_ACTIONS)
    bp_action = rng.choice(HTN_ACTIONS)
    complication_check = rng.choice(DM_COMPLICATIONS_CHECK)
    fw_months = rng.choice([1, 2, 3])

    bp_str = vitals_bp(sbp, dbp, rng)

    open_variants = [
        f"{name}，{gender}，{age}岁，2型糖尿病+高血压随访，空腹血糖{fg}mmol/L，{bp_str}。",
        f"{name}慢病随访，{age}岁，血糖{fg}（空腹），餐后{pp_glucose}，血压{sbp}/{dbp}。",
        f"今天{name}来门诊了，{gender}{age}，DM2+HTN随访，FBG {fg}，{bp_str}。",
        f"复诊：{name}，{gender}，{age}岁，糖尿病高血压患者，空腹糖{fg}mmol，血压{sbp}/{dbp}mmHg。",
    ]
    dm_turn_variants = [
        f"HbA1c {hba1c}%，{insulin_action}；血压控制不佳，{bp_action}。",
        f"糖化血红蛋白{hba1c}%，较上次{'改善' if hba1c < 8 else '升高'}，{insulin_action}。血压：{bp_action}。",
        f"HbA1c回来了，{hba1c}%，血糖{insulin_action}，降压方面{bp_action}。",
        f"化验结果：HbA1c {hba1c}%，血脂偏高，{insulin_action}。同时{bp_action}。",
    ]
    fw_variants = [
        f"{followup_interval(fw_months * 4, rng)}复查HbA1c和肾功能，{complication_check}",
        f"安排{fw_months}个月后复查，{complication_check}。嘱患者记录血压日志。",
        f"下次就诊{followup_interval(fw_months * 4, rng)}，复查空腹血糖、HbA1c、肾功。{complication_check}",
    ]

    chief = rng.choice(["血糖管理", "慢病随访", "糖尿病高血压随访"])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(dm_turn_variants), rng.choice(fw_variants), save],
        [rng.choice(open_variants), rng.choice(dm_turn_variants),
         addendum(f"嘱患者低盐低糖饮食，每天步行30分钟", rng), rng.choice(fw_variants), save],
        [rng.choice(open_variants), rng.choice(dm_turn_variants), rng.choice(fw_variants),
         set_reminder(name, f"{fw_months}个月后", rng), save],
        [rng.choice(open_variants), query_history(name, rng),
         rng.choice(dm_turn_variants), rng.choice(fw_variants), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

    op_day_zh = ["一", "二", "三", "四", "五", "六", "七", "八"][min(op_day - 1, 7)]
    open_variants = [
        f"{name}，{gender}，{age}岁，{surgery}术后第{op_day}天，{wound}。",
        f"术后查房：{name}，{surgery}后D{op_day}，{wound}。",
        f"{name}，{op_day_zh}术后，{surgery}，切口情况：{wound}。",
        f"帮我记{name}的术后记录，{gender}{age}岁，{surgery}术后第{op_day}天。",
    ]
    pain_variants = [
        f"疼痛NRS评分{pain}分，{drain}，镇痛继续。",
        f"疼痛{pain}/10，{drain}，维持现有镇痛方案。",
        f"{drain}。疼痛评分{pain}分，患者可耐受。",
        f"患者诉疼痛{pain}分，{drain}，处理方案不变。",
    ]
    rehab_variants = [
        f"{complication}明日开始早期康复训练，预计{rng.randint(2, 5)}天后出院。",
        f"{complication}康复科会诊，{rng.randint(2, 5)}天后可出院。",
        f"已请康复科评估，{complication}计划住院{rng.randint(2, 5)}天后出院。",
    ]

    chief = rng.choice(["术后恢复", f"{surgery[:4]}术后", "外科术后随访"])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(pain_variants), rng.choice(rehab_variants), save],
        [rng.choice(open_variants), rng.choice(pain_variants),
         addendum(f"今日复查血常规：Hb {hb_val}g/L，WBC正常", rng),
         rng.choice(rehab_variants), save],
        [rng.choice(open_variants), rng.choice(pain_variants), rng.choice(rehab_variants),
         set_reminder(name, f"{rng.randint(2, 4)}天后", rng), save],
        [rng.choice(open_variants), rng.choice(pain_variants), rng.choice(rehab_variants),
         context_summary(name, f"{surgery}术后第{op_day}天，{wound[:6]}，NRS {pain}分", rng), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

def tmpl_oncology(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(36, 74)
    cycle = rng.randint(1, 8)
    cancer = rng.choice(CANCERS)
    regimen = rng.choice(CHEMO_REGIMENS)
    day_after = rng.choice([3, 5, 7, 10, 14])
    wbc_v = round(rng.uniform(0.8, 4.8), 1)
    hb_v = rng.randint(68, 128)
    plt_v = rng.randint(38, 210)
    toxicity = rng.choice(TOXICITIES)
    action = rng.choice(CHEMO_ACTIONS)

    wbc_str = lab_wbc(wbc_v, rng)
    hb_str = lab_hb(hb_v, rng)

    open_variants = [
        f"{name}，{gender}，{age}岁，{cancer}，{regimen}第{cycle}周期，化疗后第{day_after}天，{toxicity}。",
        f"{name}来随访了，{cancer}化疗第{cycle}疗程后D{day_after}，{toxicity}。",
        f"肿瘤科随访：{name}，{gender}{age}，{cancer}，第{cycle}次化疗（{regimen}）后{day_after}天，{toxicity}。",
        f"记录{name}化疗副反应，{cancer}，{cycle}疗程，第{day_after}天，{toxicity}。",
    ]
    lab_variants = [
        f"血常规：{wbc_str}，{hb_str}，PLT {plt_v}×10⁹/L，{action}。",
        f"化验：{wbc_str}，Hb {hb_v}，PLT {plt_v}，{action}。",
        f"血象：白血胞{wbc_v}，血红蛋白{hb_v}g/L，血小板{plt_v}，{action}。",
    ]
    followup_variants = [
        "记录本疗程耐受情况和毒副反应等级，下次化疗前24小时复查血象。",
        "下周期前评估血象，同时复查肝肾功能和肿瘤标志物。",
        f"纳入化疗毒性记录：Grade{'I' if wbc_v > 2 else 'II'}，{followup_interval(2, rng)}复查。",
        "记录本次不良反应，评估是否需要调整下一周期化疗方案。",
    ]

    chief = rng.choice(["化疗随访", "肿瘤化疗", f"{cancer[:3]}化疗"])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(lab_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(lab_variants),
         addendum(f"患者体重较上次下降{rng.randint(1,4)}kg，营养支持评估", rng),
         rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(lab_variants), rng.choice(followup_variants),
         set_reminder(name, f"{rng.choice(['下周', '5天后', '1周后'])}血象复查", rng), save],
        [rng.choice(open_variants), query_history(name, rng),
         rng.choice(lab_variants), rng.choice(followup_variants), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

def tmpl_respiratory(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(40, 84)
    spo2 = rng.randint(83, 97)
    symptom_fn = rng.choice(RESP_SYMPTOMS)
    symptom = symptom_fn(rng)
    antibiotic = rng.choice(ANTIBIOTICS)
    o2 = rng.choice(O2_SUPPORT)
    imaging_finding = rng.choice(RESP_IMAGING)

    spo2_str = vitals_spo2(spo2, rng)

    open_variants = [
        f"{name}，{gender}，{age}岁，{symptom}，{spo2_str}入院。",
        f"收治{name}，{gender}{age}岁，{symptom}，血氧{spo2}%。",
        f"呼吸科新收患者{name}，{age}岁，{symptom}，SpO₂ {spo2}%。",
        f"急诊入院：{name}，{gender}，{age}，{symptom}，氧饱和{spo2}%。",
    ]
    treatment_variants = [
        f"{imaging_chest(imaging_finding, rng)}，予{antibiotic}抗感染，{o2}。",
        f"影像：{imaging_finding}。开始{antibiotic}，辅助{o2}。",
        f"{antibiotic}抗感染治疗，{o2}，{imaging_finding}（影像）。",
        f"治疗方案：{antibiotic} + {o2}。胸片/CT：{imaging_finding}。",
    ]
    followup_variants = [
        "48小时后复查血常规、CRP和胸片，监测体温和氧合趋势。",
        "24-48h评估疗效，复查血常规、PCT，必要时升阶梯抗生素。",
        "每日监测体温、SpO₂和痰液变化，3天无效则考虑换药。",
        "记录本次呼吸道感染评分，规划抗生素疗程和出院节点。",
    ]

    chief = rng.choice(["肺炎", "呼吸道感染", "COPD急性加重", symptom[:4]])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(treatment_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(treatment_variants),
         addendum(f"患者既往{rng.choice(['COPD', '哮喘', '高血压', '糖尿病', '无特殊病史'])}", rng),
         rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(treatment_variants), rng.choice(followup_variants),
         set_reminder(name, "48小时后", rng), save],
        [rng.choice(open_variants), query_history(name, rng),
         rng.choice(treatment_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(treatment_variants),
         correction("抗生素", antibiotic, rng),
         rng.choice(followup_variants), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
            "must_include_any_of": [["咳嗽", "肺炎", "SpO", "抗生素", "胸片", "气促", "COPD", "氧疗"]],
        },
    }


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

def tmpl_arrhythmia(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(46, 80)
    rhythm = rng.choice(RHYTHMS)
    hr = rng.randint(48, 152)
    drug = rng.choice(ANTIARRHYTHMIC_DRUGS)
    holter = rng.choice(HOLTER_RESULTS)
    score = rng.randint(1, 5)
    plan = rng.choice(ARRHYTHMIA_PLANS).format(score=score)
    hr_str = vitals_hr(hr, rng)

    open_variants = [
        f"{name}，{gender}，{age}岁，心悸就诊，心电图示{rhythm}，{hr_str}。",
        f"心律失常患者{name}，{age}岁，ECG：{rhythm}，心率{hr}次/分。",
        f"{name}，{gender}，{age}，主诉心悸{rng.randint(1,7)}天，今日心电图：{rhythm}。",
        f"门诊：{name}，{gender}{age}岁，心慌不适，心电图报告{rhythm}，心率{hr}。",
    ]
    holter_drug_variants = [
        f"{holter}，予{drug}，{plan}",
        f"动态心电图结果：{holter}。用药：{drug}。下一步：{plan}",
        f"Holter回报：{holter}。处理：{drug}，{plan}",
        f"根据{holter}，方案：{drug}，{plan}",
    ]
    followup_variants = [
        f"记录心律失常类型、当前治疗和评估结论，{followup_interval(4, rng)}复查心电图。",
        "1个月后门诊随访，复查12导联心电图和Holter。",
        "监测药物不良反应（甲状腺、肝肾功、QTc），2周后复诊。",
        "如心悸加重或晕厥，立即急诊。1个月复查动态心电图。",
    ]

    chief = rng.choice(["心律失常", "心房颤动", "心悸"])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(holter_drug_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(holter_drug_variants),
         addendum(f"LVEF {rng.randint(40, 65)}%，左房内径{rng.randint(38, 55)}mm", rng),
         rng.choice(followup_variants), save],
        [rng.choice(open_variants), query_history(name, rng),
         rng.choice(holter_drug_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(holter_drug_variants), rng.choice(followup_variants),
         set_reminder(name, "1个月后", rng), save],
        [rng.choice(open_variants), rng.choice(holter_drug_variants),
         context_summary(name, f"{rhythm}，{drug[:8]}治疗中", rng),
         rng.choice(followup_variants), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

def tmpl_sepsis(name: str, idx: int, rng: random.Random) -> dict:
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

    open_variants = [
        f"{name}，{gender}，{age}岁，{source}，PCT {pct}ng/mL，乳酸{lactate}mmol/L。",
        f"ICU新入患者{name}，{gender}{age}，{source}，PCT {pct}，乳酸{lactate}。",
        f"{name}，{source}，年龄{age}，PCT {pct}ng/mL，血乳酸{lactate}mmol/L，血压{map_val}mmHg（MAP）。",
        f"脓毒症记录：{name}，{gender}，{age}岁，{source}，指标：PCT {pct}，LAC {lactate}。",
    ]
    treatment_variants = [
        f"予{abx}广谱覆盖，30ml/kg晶体液复苏，{vasopressor}。",
        f"抗感染：{abx}。复苏：30ml/kg乳酸林格液。升压：{vasopressor}。",
        f"{vasopressor}，同时{abx}经验性覆盖，完成液体复苏。",
    ]
    followup_variants = [
        f"{bundle}{organ_mon}",
        f"{organ_mon}，{bundle}",
        f"集束化治疗：{bundle}，此后{organ_mon}",
    ]

    chief = rng.choice(["脓毒症", "感染性休克", source[:4]])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(treatment_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(treatment_variants),
         addendum(f"血培养已送检2套，等待结果，经验性覆盖", rng),
         rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(treatment_variants), rng.choice(followup_variants),
         context_summary(name, f"{source}，PCT {pct}，乳酸{lactate}，{abx[:10]}覆盖中", rng), save],
        [rng.choice(open_variants), rng.choice(treatment_variants), rng.choice(followup_variants),
         set_reminder(name, "6小时后", rng), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

def tmpl_renal(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(40, 80)
    cr = rng.randint(180, 650)
    gfr = rng.randint(6, 48)
    stage = rng.choice(CKD_STAGES)
    electrolyte = rng.choice(RENAL_ELECTROLYTES)(rng)
    hb_v = rng.randint(68, 115)
    plan = rng.choice(RENAL_PLANS)
    cr_str = lab_creatinine(cr, rng)

    open_variants = [
        f"{name}，{gender}，{age}岁，{stage}随访，{cr_str}，eGFR {gfr}mL/min/1.73m²。",
        f"肾内科随访：{name}，{age}岁，{stage}，肌酐{cr}，eGFR {gfr}。",
        f"{name}复诊，{gender}{age}岁，{stage}，今日血肌酐{cr}μmol/L，GFR {gfr}。",
        f"CKD患者{name}记录，{stage}，{cr_str}，eGFR {gfr}。",
    ]
    lab_variants = [
        f"{electrolyte}，{lab_hb(hb_v, rng)}，{plan}，限制磷蛋白摄入。",
        f"电解质：{electrolyte}。血红蛋白{hb_v}g/L。方案：{plan}。",
        f"化验汇总：{electrolyte}，Hb {hb_v}。治疗：{plan}。",
    ]
    followup_variants = [
        f"1个月后复查肾功能、电解质、贫血三项，今日血压控制欠佳，调整降压方案。",
        f"{followup_interval(4, rng)}复查肾功、电解质、血常规，追踪CKD进展速度。",
        "记录本次CKD评估，注意避免肾毒性药物（NSAID、造影剂），下次门诊前后尿检。",
        "建议患者戒烟、控制血压和血糖，延缓CKD进展，下次复查带入尿液标本。",
    ]

    chief = rng.choice(["肾功能不全", "CKD随访", "慢性肾脏病"])
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(lab_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(lab_variants),
         addendum(f"今日做床旁超声，双肾缩小，皮质变薄，符合CKD表现", rng),
         rng.choice(followup_variants), save],
        [rng.choice(open_variants), query_history(name, rng),
         rng.choice(lab_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(lab_variants), rng.choice(followup_variants),
         set_reminder(name, "1个月后", rng), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
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

def tmpl_mental(name: str, idx: int, rng: random.Random) -> dict:
    gender = rng.choice(["男", "女"])
    age = rng.randint(18, 68)
    condition = rng.choice(PSYCH_CONDITIONS)
    scale_name, score_fn = rng.choice(PSYCH_SCALES)
    score = score_fn(rng)
    drug = rng.choice(PSYCH_DRUGS)
    risk = rng.choice(RISK_LEVELS)
    therapy = rng.choice(PSYCH_THERAPY)
    fw_weeks = rng.choice([1, 2, 4])

    open_variants = [
        f"{name}，{gender}，{age}岁，{condition}，{scale_name}评分{score}分。",
        f"精神科就诊：{name}，{gender}{age}，诊断{condition}，量表{scale_name} {score}分。",
        f"{name}，{age}岁，{condition}，今日门诊评估，{scale_name}={score}分。",
        f"心理/精神科记录：{name}，{gender}，{age}岁，{condition}，{scale_name}评分{score}。",
    ]
    drug_risk_variants = [
        f"予{drug}，{risk}{therapy}",
        f"用药方案：{drug}。风险评级：{risk.split('，')[0]}。治疗：{therapy}",
        f"开具：{drug}。{risk}推荐{therapy}",
        f"{drug}，同时{therapy}{risk}",
    ]
    followup_variants = [
        f"{followup_interval(fw_weeks, rng)}随访，评估药物疗效和副反应，复查{scale_name}。",
        f"记录本次评估和用药，{fw_weeks}周后复诊，监测药物不良反应。",
        f"复诊时间：{followup_interval(fw_weeks, rng)}，关注睡眠、情绪和副反应（性功能/体重）。",
        "如症状明显加重或出现自伤倾向，立即急诊精神科就诊。",
    ]

    chief = condition[:4]
    save = save_command(name, gender, age, chief, rng)

    turns_options = [
        [rng.choice(open_variants), rng.choice(drug_risk_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(drug_risk_variants),
         addendum(f"患者主诉睡眠障碍，入睡困难，予佐匹克隆短期辅助", rng),
         rng.choice(followup_variants), save],
        [rng.choice(open_variants), query_history(name, rng),
         rng.choice(drug_risk_variants), rng.choice(followup_variants), save],
        [rng.choice(open_variants), rng.choice(drug_risk_variants), rng.choice(followup_variants),
         context_summary(name, f"{condition}，{scale_name} {score}分，{drug[:8]}治疗中", rng), save],
        [rng.choice(open_variants), rng.choice(drug_risk_variants),
         correction("量表评分", f"{scale_name} {score}分（已核实）", rng),
         rng.choice(followup_variants), save],
    ]
    turns = rng.choice(turns_options)

    return {
        "case_id": f"REALWORLD-V2-{idx}",
        "title": f"Complex real-world doctor-agent case v2 #{idx}",
        "chatlog": [{"speaker": "doctor", "text": t} for t in turns],
        "expectations": {
            "must_not_timeout": True,
            "expected_table_min_counts_global": {"system_prompts": 1},
            "must_include_any_of": [["抑郁", "焦虑", "PHQ", "情绪", "心理", "GAD", "HAMD", "精神", "量表"]],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — regenerate V2-101..1000 in-place
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    data: list[dict] = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    # Keep only original 100 cases, regenerate the expansion
    original = [c for c in data if int(c["case_id"].split("-")[-1]) <= 100]
    assert len(original) == 100, f"Expected 100 original cases, found {len(original)}"
    print(f"Original cases kept: {len(original)}")

    rng = random.Random(42)

    templates = [
        tmpl_stroke,
        tmpl_discharge,
        tmpl_chronic,
        tmpl_postop,
        tmpl_oncology,
        tmpl_respiratory,
        tmpl_arrhythmia,
        tmpl_sepsis,
        tmpl_renal,
        tmpl_mental,
    ]

    target = 1000
    new_count = target - len(original)   # 900
    names = gen_unique_names(new_count, rng)

    new_cases: list[dict] = []
    for i, name in enumerate(names):
        case_num = len(original) + 1 + i   # 101 … 1000
        tmpl_fn = templates[i % len(templates)]
        case = tmpl_fn(name, case_num, rng)
        new_cases.append(case)

    result = original + new_cases
    assert len(result) == target

    # Validate all new cases
    errors = []
    for c in new_cases:
        chatlog = c.get("chatlog", [])
        doc_turns = [x for x in chatlog if x.get("speaker") == "doctor"]
        if len(chatlog) < 4:
            errors.append(f"{c['case_id']}: only {len(chatlog)} turns")
        if len(doc_turns) < 3:
            errors.append(f"{c['case_id']}: only {len(doc_turns)} doctor turns")
        if not c.get("expectations", {}).get("must_not_timeout"):
            errors.append(f"{c['case_id']}: missing must_not_timeout")
    if errors:
        print(f"VALIDATION ERRORS ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e}")
        raise SystemExit(1)

    DATA_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(result)} total cases ({new_count} new).")

    # Turn-length distribution
    from collections import Counter
    turn_dist = Counter(len(c["chatlog"]) for c in new_cases)
    print("Turn-length distribution (new cases):")
    for k in sorted(turn_dist):
        print(f"  {k} turns: {turn_dist[k]}")

    # Scenario distribution
    kw_dist: dict[str, int] = {}
    for c in new_cases:
        k = c["expectations"]["must_include_any_of"][0][0]
        kw_dist[k] = kw_dist.get(k, 0) + 1
    print("Scenario distribution:")
    for k, v in sorted(kw_dist.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
