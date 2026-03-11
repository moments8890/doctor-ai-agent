#!/usr/bin/env python3
"""
共享短语库与姓名池 — generate_v2_expansion.py 的内部辅助模块。

包含：
- 中文姓名池（SURNAMES / GIVEN / GIVEN_2CHAR）与 gen_unique_names()
- 医生言语短语构建函数（opening_intro / addendum / correction 等）
- 临床指标短语函数（vitals_bp / lab_wbc / followup_interval 等）

本模块仅依赖标准库，可被 generate_v2_expansion.py 及各模板模块安全导入。

Shared phrase bank and name pool helpers for V2 chatlog expansion scripts.
"""

from __future__ import annotations

import random

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
        f"确认患者{name}，主诉{chief}，请创建并保存本次病历。",
        f"好，把{name}的病历保存了，主诉{chief}。",
        f"帮我把刚才{name}的记录存档，主诉{chief}。",
        f"{name}的记录整理好了，存一下，主诉{chief}。",
        f"保存{name}本次就诊记录，{gender}{age}岁，主诉{chief}。",
        f"请新建{name}并保存这次病历，主诉{chief}。",
        f"{name}，{gender}，{age}岁，今日主诉{chief}，创建保存。",
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

