"""
Keyword frozensets for fast_router.

All frozensets are static immutable literals — no loading at runtime.
"""

from __future__ import annotations

# ── Import history detection ───────────────────────────────────────────────────
_IMPORT_KEYWORDS: frozenset[str] = frozenset({
    "导入病历", "导入历史", "历史记录导入", "既往病历",
    # "过往记录" removed — ambiguous with query_patient_records; let LLM decide
})

# ── Tier 1: Exact / normalised keyword sets ────────────────────────────────────

_LIST_PATIENTS_EXACT: frozenset[str] = frozenset({
    "所有患者", "全部患者", "患者列表", "病人列表", "患者名单",
    "显示患者", "我的患者", "查看患者",
    "病人名单", "我的病人", "列出患者", "列出病人",
    "看看患者", "患者信息", "所有病人",
    "有哪些患者", "有哪些病人", "患者都有谁", "病人都有谁",
    "列出所有患者", "列出所有病人",
    "再给我所有患者列表", "再给所有患者列表", "再看所有患者",
    "再看一下所有患者", "再看一下患者列表",
})

# Very short triggers — only match if the entire message is exactly these chars.
# Bare "患者"/"病人" removed — too ambiguous as standalone messages.
_LIST_PATIENTS_SHORT: frozenset[str] = frozenset({
    "患者列表", "患者名单",
})

_LIST_TASKS_EXACT: frozenset[str] = frozenset({
    "所有任务", "全部任务", "待办列表", "任务列表", "我的待办",
    "显示任务", "查看任务", "待办事项",
    "待办任务", "我的任务", "待处理",
    "有什么任务", "有啥任务", "待处理任务",
    "查看待办", "显示待办", "有哪些任务",
    "最近任务", "今天任务", "今日任务",
    "先看下我还有几个待办", "先看下我今天待办", "先看下今天待办",
    "我还有几个待办", "今天有什么待办", "先看下我的待办",
    "先看下我今天的任务", "先看下我的任务",
    "先看下我今天待办事项",
})

# Bare "任务" removed — too ambiguous as standalone message.
_LIST_TASKS_SHORT: frozenset[str] = frozenset({
    "待办", "任务列表",
})

# ── Domain keywords that must never be treated as patient names ────────────────
_NON_NAME_KEYWORDS: frozenset[str] = frozenset({
    "病历", "记录", "情况", "病情", "近况", "状态", "任务", "待办",
    "患者", "病人", "诊断", "治疗",
    # Action verbs / non-names that _CREATE_LEAD_RE can falsely capture at
    # end-of-string (e.g. "创建查看" → name="查看").  Blocklist over regex
    # because CJK verb phrases are indistinguishable from names by pattern.
    "查看", "存档", "住院", "保存", "确认", "取消", "更新", "使用",
    "档案", "一个", "一下", "备注", "创建", "操作",
    "创建", "等下",  # P3: prevent lead-keyword from capturing itself or filler as name
    "信息",  # guard for "确认患者信息" edge case
})

# ── Tier 3: name-extraction bad-name guard ─────────────────────────────────────
_TIER3_BAD_NAME: frozenset[str] = frozenset({
    "患者", "病人", "主诉", "诊断", "治疗", "随访", "复查", "处置",
})

# ── Tier 3: clinical keyword set ───────────────────────────────────────────────
# High-specificity terms that strongly imply clinical content. Conservative — if
# a keyword could appear in a non-clinical question, it is omitted here. Border-
# line messages still fall through to the routing LLM.
_CLINICAL_KW_TIER3: frozenset[str] = frozenset({
    # Cardinal symptoms
    "胸痛", "胸闷", "心悸", "气促", "气短", "头痛", "发热", "发烧",
    "咳嗽", "腹痛", "呕吐", "眩晕", "水肿",
    # removed: 乏力 (too generic — "I'm tired" is universal; let LLM decide)
    # removed: 恶心 (dual meaning: nausea / disgusting in everyday Chinese)
    # removed: 阵发性 (bare modifier — any message worth routing here already has another kw)
    # removed: 头晕 (too colloquial; Tier-B patient voice guard misses many forms)
    "呼吸困难", "晕厥", "心绞痛", "发绀",
    "浮肿", "偏头痛", "头晕耳鸣",
    # Cardiovascular diagnoses / procedures
    "心衰", "心梗", "房颤", "STEMI", "PCI", "溶栓", "消融", "支架",
    "心律失常", "心脏病", "心电图", "心力衰竭",
    # removed: 心慌 (colloquial for nervousness as much as palpitations; also was duplicate)
    # Oncology
    "化疗", "靶向", "放疗", "肿瘤", "升白",
    "肺癌", "血管瘤", "颅内肿瘤",
    "腺癌", "转移瘤", "脾大", "淋巴瘤", "直肠癌",
    # removed: 直肠 (bare anatomy noun; 直肠癌 above covers the clinical case)
    "肝癌", "前列腺癌",
    # Specific lab markers (unlikely in non-clinical speech)
    "BNP", "肌钙蛋白", "HbA1c", "CEA", "ANC", "EGFR", "HER2",
    "INR", "血常规", "抗凝",
    # removed: 白细胞, 血红蛋白 — valid clinical terms but frequently appear in
    # patient questions about their own lab results; not strong doctor-note signals
    "空腹血糖", "餐后血糖", "血糖升高", "血糖偏高", "血糖控制", "血糖异常",
    # English clinical terms (mixed-language doctor notes)
    # removed: chest (single common English word; countless non-clinical uses)
    "ECG", "NIHSS", "dyspnea", "palpitation",
    # Neurological (CBLUE-expanded)
    "颅内高压", "颅内压增高", "颅压高", "脑水肿", "脑疝", "颅内占位性病变",
    "视乳头水肿",
    "三叉神经痛", "搭桥手术", "烟雾病", "脑动脉", "脑梗", "脑梗死", "脑梗塞",
    "脑血管病", "视野缺损", "视野缩窄", "颅内动脉", "颅外颅内", "颈椎病",
    # Neurological — strokes / CVD (reviewer-identified gaps)
    "偏瘫", "单瘫", "截瘫", "失语", "构音障碍", "共济失调",
    "脑出血", "脑血栓", "脑栓塞", "蛛网膜下腔出血", "SAH", "TIA",
    "动脉瘤", "颅内动脉瘤", "血肿", "硬膜下血肿", "硬膜外血肿",
    "脑积水", "脑脊液", "再出血", "血管痉挛",
    "意识障碍", "昏迷", "谵妄",
    # Neurological — imaging descriptors
    "DWI", "FLAIR", "弥散受限",
    # Metabolic / systemic
    "低血糖", "高氨血症", "代谢性酸中毒", "黄疸",
    "低蛋白血症", "低血压", "高脂血症", "高血压病史",
    "血压",  # Doctor follow-up notes: "血压稳定", "血压120/80". Patient questions containing
    # 血压 are guarded by _is_patient_question (怎么办, 多少 etc.) or the MCQ ending block.
    # removed: 高血压, 糖尿病 — common chronic disease names; appear heavily in patient
    # questions and family summaries; 高血压病史 above is a stronger doctor-note signal
    # Cardiology
    "胸腔积液", "室间隔缺损", "动脉导管未闭", "大动脉转位",
    # Respiratory
    "肺炎", "肺结核", "肺气肿", "胸膜炎",
    # Gastrointestinal
    # removed: 便秘, 腹泻, 胃痛 — top everyday self-reported complaints; not
    # high-specificity doctor-dictation signals; 腹痛/便血/呕血 etc. already present
    "腹胀", "胃炎",
    "胃溃疡", "胆囊炎", "肠易激综合征", "胰腺炎", "便血", "黑便",
    "呕血", "肠梗阻", "吞咽困难", "反酸", "嗳气",
    # Obstetric / gynecologic
    "乳房胀痛", "乳腺增生", "妇科炎症", "子宫内膜炎", "痛经", "盆腔炎", "阴道炎",
    # Musculoskeletal
    "椎管狭窄", "腰椎穿刺", "腰痛",
    # Infectious
    "前列腺炎", "抗生素",
    # removed: 鼻炎 (extremely common self-reported condition; discussed constantly outside clinical notes)
    # Systemic symptoms
    "高热", "全身无力", "四肢无力", "面色苍白",
    "贫血", "寒战", "皮疹", "蛋白尿", "血尿", "尿频", "尿急",
    # Critical care / neurological
    "癫痫", "呼吸衰竭", "休克", "败血症", "低氧血症", "颅内出血",
    # Pathology / imaging
    # removed: 结节, 积液, 钙化, 梗阻 — common in report-interpretation requests and
    # patient questions about their own imaging; 占位/免疫组化/彩超提示 are stronger
    "占位", "免疫组化", "彩超提示",
    # Hepatology
    "肝硬化", "肝功能",
    # Signs / oncology
    "淋巴结转移",
    # Surgical / procedural
    "介入治疗", "开颅",
    # removed: 介入 (everyday Chinese verb "to intervene"; 介入治疗 above covers the clinical case)
    "换药", "引流", "TKA", "THA", "PACU",  # procedural (dressing/drain/joint-replacement/PACU)
    # Pain / mental health scores (mixed-language clinical notes)
    "NRS", "PHQ",
    # Common symptoms / signs (kept: unambiguous clinical exam findings only)
    # removed: 疼痛 (too generic; specific compounds 胸痛/腹痛/… already present)
    # removed: 肿胀, 红肿 (generic swelling/redness — common in patient self-reports)
    # removed: 咽喉肿痛 (top everyday self-reported complaint)
    # removed: 出血 (too generic; specific forms 脑出血/便血/呕血/颅内出血 already in set)
    "压痛", "无压痛", "反跳痛", "咽痛",
    "刺痛", "肿块",
    # Signs / lab
    "尿痛",
    # Clinical admin (exclusive to hospital documentation)
    "收入我科", "收治入院", "神志清", "门诊以",
    "绿色通道", "急性心肌梗死", "心跳骤停", "心脏骤停", "室颤", "抢救",
})

# ── Help / capability list ────────────────────────────────────────────────────
_HELP_KEYWORDS: frozenset[str] = frozenset({
    "帮助", "help", "?", "？", "功能列表", "怎么用", "使用说明",
    "有哪些功能", "能做什么", "能干嘛", "有什么功能", "怎么操作",
})

