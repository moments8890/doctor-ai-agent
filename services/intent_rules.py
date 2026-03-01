"""Rule-based intent detection using jieba POS tagging + regex.

No LLM call — runs in < 5 ms with zero network dependency.

Intent priority (checked in order):
  0. emergency       — dangerous vital signs / life-threatening events → add_record + is_emergency=True
  1. list_patients   — list all patients
  2. create_patient  — most specific, explicit patient-creation keywords
  3. query_records   — query/history keywords
  4. add_record      — medical content keywords
  5. unknown         — fallback
"""
import re
import jieba.posseg as pseg
from services.intent import Intent, IntentResult

# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

_EMERGENCY_KW = [
    "心跳停止", "心脏停跳", "无脉", "室颤", "猝死",
    "血压测不出", "血压为零", "测不出血压",
    "过敏性休克", "失血性休克", "休克",
    "主动脉破裂", "主动脉夹层破裂",
    "心肌梗死急性", "急性心梗",
    "呼吸停止", "呼吸骤停", "心跳骤停",
]

_LIST_PATIENTS_KW = [
    "所有病人", "所有患者", "全部患者", "全部病人",
    "患者列表", "病人列表", "我的患者", "病人名单",
]

_CREATE_KW = [
    "新患者", "建档", "新病人", "建立患者", "添加患者",
    "注册患者", "登记患者", "创建患者", "新建患者",
]

_QUERY_KW = [
    "查询", "查一下", "查看", "历史记录", "病历记录",
    "查病历", "看病历", "历史", "过去记录", "之前记录",
    "查记录", "看看记录", "看看病历",
]

_RECORD_KW = [
    # recording triggers — doctor wants to log something
    "记录一下", "记一下", "帮我记", "录入", "写病历", "记病历",
    # clinical workflow
    "诊断", "主诉", "治疗", "症状", "病历", "开药",
    "处方", "检查", "化验", "手术", "随访", "复诊",
    "病情", "病史",
    # medication / procedure
    "给药", "用药", "服药", "注射", "输液", "换药",
    # symptoms — formal
    "发烧", "发热", "咳嗽", "头痛", "腹痛", "胸闷",
    "血压", "血糖", "心率",
    # symptoms — colloquial
    "头疼", "肚子疼", "胸痛", "背痛", "腰痛", "腿痛",
    "恶心", "呕吐", "腹泻", "便秘", "失眠", "乏力",
    "疲劳", "心慌", "气短", "浮肿", "水肿", "出血",
    "口渴", "多饮", "多尿", "消瘦", "体重下降",
    "头晕", "眩晕", "耳鸣", "视力", "皮疹", "瘙痒",
    "关节", "肿胀", "麻木", "抽筋", "痉挛",
    # additional common symptoms
    "感冒", "流涕", "鼻塞", "喉咙", "嗓子", "扁桃体",
    "腹胀", "胃痛", "胃疼", "牙痛", "牙疼",
    "肩痛", "肩膀", "颈痛", "脖子", "膝盖",
    "发冷", "寒颤", "食欲", "过敏",
    "骨折", "扭伤", "外伤", "伤口",
    # === cardiology symptoms ===
    "胸痛", "心绞痛", "胸闷痛", "压榨感", "濒死感",
    "心悸", "心跳快", "心跳慢", "早搏", "停跳",
    "气促", "呼吸困难", "端坐呼吸",
    "晕厥", "黑朦", "眼前发黑",
    "下肢水肿", "脚肿", "腿肿", "腹水", "颈静脉怒张",
    "咯血", "粉红色泡沫痰", "唇绀", "口唇发紫",
    "间歇性跛行", "肢体发凉", "脉搏弱",
    # === cardiology examinations & metrics ===
    "心电图", "ECG", "动态心电图", "Holter",
    "心脏彩超", "超声心动图", "射血分数", "EF值", "LVEF",
    "冠脉造影", "CAG", "支架", "PCI", "球囊",
    "冠脉CT", "CTA", "钙化积分",
    "肌钙蛋白", "TnI", "TnT", "CK-MB", "心肌酶",
    "BNP", "NT-proBNP", "脑钠肽",
    "D-二聚体", "凝血功能",
    "血脂", "低密度", "LDL", "甘油三酯", "胆固醇",
    "同型半胱氨酸",
    "平板运动试验", "负荷试验",
    # === cardiology diagnoses ===
    "冠心病", "心梗", "心肌梗死", "STEMI", "NSTEMI", "ACS",
    "心衰", "心力衰竭", "左心衰", "右心衰", "全心衰",
    "房颤", "房扑", "室上速", "室速", "室颤", "传导阻滞",
    "高血压", "高血压危象",
    "心肌炎", "心包炎", "心内膜炎",
    "瓣膜病", "二尖瓣", "三尖瓣", "主动脉瓣", "狭窄", "关闭不全", "反流",
    "先心病", "房缺", "室缺",
    "肺栓塞", "深静脉血栓",
    "主动脉夹层",
    "高血脂", "高脂血症",
    # === cardiology medications ===
    "阿司匹林", "氯吡格雷", "替格瑞洛", "双抗",
    "他汀", "阿托伐他汀", "瑞舒伐他汀",
    "美托洛尔", "倍他乐克", "比索洛尔",
    "依那普利", "缬沙坦",
    "硝苯地平", "氨氯地平",
    "呋塞米", "托拉塞米", "螺内酯",
    "硝酸甘油", "消心痛",
    "华法林", "利伐沙班", "达比加群", "抗凝",
    "地高辛", "胺碘酮", "普罗帕酮",
    "溶栓", "尿激酶",
    # === cardiology procedures ===
    "放支架", "植入支架", "搭桥", "CABG",
    "射频消融", "消融", "起搏器", "ICD", "CRT",
    "电复律", "除颤",
    "介入治疗",
]


# ---------------------------------------------------------------------------
# Entity extractors
# ---------------------------------------------------------------------------

def _extract_name(text: str) -> str | None:
    # 1. jieba POS — 'nr' tag = person name
    for word, flag in pseg.cut(text):
        if flag.startswith("nr") and 1 < len(word) <= 4:
            return word

    # 2. Pattern: after 患者/叫/名叫
    m = re.search(r'(?:患者|叫做?|名叫)\s*([^\s，,。！？\d]{2,4})', text)
    if m:
        return m.group(1)

    return None


def _extract_age(text: str) -> int | None:
    m = re.search(r'(\d+)\s*岁', text)
    return int(m.group(1)) if m else None


def _extract_gender(text: str) -> str | None:
    if re.search(r'男(?:性|生|士)?', text):
        return "男"
    if re.search(r'女(?:性|生|士)?', text):
        return "女"
    return None


# ---------------------------------------------------------------------------
# Cardiovascular metric extractor
# ---------------------------------------------------------------------------

def _extract_cv_metrics(text: str) -> dict:
    """Extract cardiovascular vitals from free text (< 1 ms, pure regex).

    Returns a dict of whichever metrics are present, e.g.:
        {"bp_systolic": 160, "bp_diastolic": 100, "heart_rate": 95, "ef": 35}
    """
    metrics: dict = {}

    # Blood pressure — "150/90" or "收缩压150 舒张压90"
    m = re.search(r'(\d{2,3})\s*/\s*(\d{2,3})\s*(?:mmHg)?', text)
    if m:
        s, d = int(m.group(1)), int(m.group(2))
        if s > d and 60 < d < 130 and 90 < s < 240:
            metrics["bp_systolic"] = s
            metrics["bp_diastolic"] = d
    if "bp_systolic" not in metrics:
        ms = re.search(r'收缩压\s*(\d{2,3})', text)
        md = re.search(r'舒张压\s*(\d{2,3})', text)
        if ms:
            metrics["bp_systolic"] = int(ms.group(1))
        if md:
            metrics["bp_diastolic"] = int(md.group(1))

    # Heart rate — "心率95" / "HR 95" / "95次/分"
    m = re.search(r'(?:心率|HR|脉搏)\s*(?:为|:|：)?\s*(\d{2,3})\s*(?:次/?分|bpm)?', text)
    if m:
        val = int(m.group(1))
        if 30 < val < 250:
            metrics["heart_rate"] = val

    # Ejection fraction — "EF值35%" / "LVEF 35" / "射血分数35%"
    m = re.search(r'(?:EF值?|LVEF|射血分数)\s*(?:为|:|：|只有)?\s*(\d{1,2})\s*%?', text)
    if m:
        val = int(m.group(1))
        if 10 < val < 80:
            metrics["ef"] = val

    # Blood glucose — "血糖7.8" / "GLU 11.2 mmol"
    m = re.search(r'(?:血糖|GLU)\s*(?:为|:|：)?\s*(\d+\.?\d*)\s*(?:mmol)?', text)
    if m:
        metrics["blood_glucose"] = float(m.group(1))

    return metrics


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_intent_rules(text: str) -> IntentResult:
    name    = _extract_name(text)
    age     = _extract_age(text)
    gender  = _extract_gender(text)
    metrics = _extract_cv_metrics(text)

    # Emergency check runs first — dangerous events are always add_record
    if any(kw in text for kw in _EMERGENCY_KW):
        return IntentResult(
            intent=Intent.add_record,
            patient_name=name, age=age, gender=gender,
            is_emergency=True,
            extra_data=metrics,
        )

    if any(kw in text for kw in _LIST_PATIENTS_KW):
        return IntentResult(intent=Intent.list_patients)

    if any(kw in text for kw in _CREATE_KW):
        return IntentResult(intent=Intent.create_patient, patient_name=name, age=age, gender=gender)

    if any(kw in text for kw in _QUERY_KW):
        return IntentResult(intent=Intent.query_records, patient_name=name, age=age, gender=gender)

    if any(kw in text for kw in _RECORD_KW):
        return IntentResult(
            intent=Intent.add_record,
            patient_name=name, age=age, gender=gender,
            extra_data=metrics,
        )

    return IntentResult(intent=Intent.unknown)
