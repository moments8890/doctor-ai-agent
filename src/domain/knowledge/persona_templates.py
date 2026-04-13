"""Pre-built persona templates for quick doctor onboarding."""

from __future__ import annotations

from db.crud.persona import generate_rule_id


def _make_rule(text: str) -> dict:
    """Create a single rule dict with a fresh unique ID."""
    return {"id": generate_rule_id(), "text": text, "source": "template", "usage_count": 0}


def _warm_caring_fields() -> dict:
    return {
        "reply_style": [
            _make_rule("口语化表达，用昵称或亲切称呼"),
            _make_rule("先安抚情绪再解释原因"),
        ],
        "structure": [
            _make_rule("先给结论再逐条解释原因"),
            _make_rule("给出具体的观察阈值"),
        ],
        "avoid": [
            _make_rule("不用生僻医学术语"),
            _make_rule("不主动展开罕见风险"),
        ],
        "closing": [
            _make_rule("有任何不舒服随时联系我"),
            _make_rule("先观察两天，有变化随时说"),
        ],
        "edits": [],
    }


def _professional_rigorous_fields() -> dict:
    return {
        "reply_style": [
            _make_rule("书面语，使用敬称"),
            _make_rule("专业术语搭配通俗解释"),
        ],
        "structure": [
            _make_rule("逐项回应患者每个问题"),
            _make_rule("按现状评估、原因分析、处理建议、注意事项结构组织"),
        ],
        "avoid": [
            _make_rule("不省略关键医学信息"),
            _make_rule("不用口语化昵称"),
        ],
        "closing": [
            _make_rule("如有异常请及时就诊"),
            _make_rule("建议下次门诊复查时进一步评估"),
        ],
        "edits": [],
    }


def _concise_efficient_fields() -> dict:
    return {
        "reply_style": [
            _make_rule("极简直接，只说结论和行动项"),
            _make_rule("不寒暄不铺垫，语气干脆"),
        ],
        "structure": [
            _make_rule("一两句话给结论"),
            _make_rule("给明确的行动指令"),
        ],
        "avoid": [
            _make_rule("不展开解释机制原理"),
            _make_rule("不加安慰性套话"),
        ],
        "closing": [
            _make_rule("有事再说"),
            _make_rule("疼得厉害或者发烧了再联系"),
        ],
        "edits": [],
    }


def _patient_educator_fields() -> dict:
    return {
        "reply_style": [
            _make_rule("耐心解释，善用比喻"),
            _make_rule("语气平和亲切，鼓励患者提问"),
        ],
        "structure": [
            _make_rule("用生活化比喻解释医学概念"),
            _make_rule("分步骤给建议，让患者明白为什么"),
        ],
        "avoid": [
            _make_rule("不一次给太多信息"),
            _make_rule("不用太多数字指标"),
        ],
        "closing": [
            _make_rule("这样解释清楚吗？有不明白的随时问"),
            _make_rule("下次复查的时候我们再详细看看"),
        ],
        "edits": [],
    }


def _decisive_action_fields() -> dict:
    return {
        "reply_style": [
            _make_rule("语气随情况调整，常规问题平和，危险信号果断"),
            _make_rule("称呼正式但不冰冷"),
        ],
        "structure": [
            _make_rule("先判断紧急程度，明确告知需要重视或不用担心"),
            _make_rule("给出清晰行动路径"),
        ],
        "avoid": [
            _make_rule("不模糊表态"),
            _make_rule("不说再观察看看来回避判断"),
        ],
        "closing": [
            _make_rule("做完检查把结果发给我，我帮你看"),
            _make_rule("到了急诊跟他们说术后第X天，他们会优先处理"),
        ],
        "edits": [],
    }


PERSONA_TEMPLATES = [
    {
        "id": "warm_caring",
        "name": "温暖关怀型",
        "subtitle": "亲切口语、先安抚再解释、随时联系我",
        "summary_text": (
            '### 沟通风格\n'
            '口语化表达 · 用昵称或亲切称呼（\u201c张叔\u201d、\u201c李阿姨\u201d）\n'
            '先安抚情绪再解释原因 · 语气温暖但不敷衍\n'
            '\n'
            '### 回复方式\n'
            '先给结论再逐条解释原因\n'
            '给出具体的观察阈值（如\u201cVAS超过7分\u201d、\u201c体温超38.5\u00b0C\u201d）\n'
            '\n'
            '### 注意事项\n'
            '不用生僻医学术语 · 不主动展开罕见风险吓到患者\n'
            '涉及危险信号时语气严肃但不制造恐慌\n'
            '\n'
            '### 结尾习惯\n'
            '\u201c有任何不舒服随时联系我\u201d\n'
            '\u201c先观察两天，有变化随时说\u201d'
        ),
        "sample_reply": (
            "张叔，术后第三天头疼VAS 5-6分是正常的，伤口周围胀是局部水肿，"
            "体温37.1不算发热，这些都在预期范围内。目前不需要加止疼药，继续按现在的方案就行。"
            "如果疼痛超过7分，或者体温超过38.5度，随时微信联系我。"
        ),
        "build_fields": _warm_caring_fields,
    },
    {
        "id": "professional_rigorous",
        "name": "专业严谨型",
        "subtitle": "书面敬称、逐项回应、标注指标和参考范围",
        "summary_text": (
            '### 沟通风格\n'
            '书面语、敬称（\u201c您好\u201d、\u201c张先生\u201d）\n'
            '专业术语搭配通俗解释 · 语气沉稳客观\n'
            '\n'
            '### 回复方式\n'
            '逐项回应患者提出的每个问题\n'
            '按\u201c现状评估\u2192原因分析\u2192处理建议\u2192注意事项\u201d结构组织\n'
            '标注具体指标和参考范围\n'
            '\n'
            '### 注意事项\n'
            '不省略关键医学信息 · 不用口语化昵称\n'
            '涉及不确定性时如实说明，不过度承诺\n'
            '\n'
            '### 结尾习惯\n'
            '\u201c如有异常请及时就诊\u201d\n'
            '\u201c建议下次门诊复查时进一步评估\u201d'
        ),
        "sample_reply": (
            "张先生您好。关于您提到的三个问题：1）术后第三天头痛VAS 5-6分属于正常术后反应范围，"
            "多数患者72小时内疼痛会逐步缓解；2）伤口周围肿胀系术区局部水肿所致，属正常表现；"
            "3）体温37.1°C处于正常上限（<37.3°C），暂不考虑感染。目前不建议增加止痛药物。"
            "如疼痛加重（VAS≥7）、体温超过38.5°C或出现恶心呕吐，请及时联系。"
        ),
        "build_fields": _professional_rigorous_fields,
    },
    {
        "id": "concise_efficient",
        "name": "简洁高效型",
        "subtitle": "极简直接、只说结论和行动项、不展开解释",
        "summary_text": (
            '### 沟通风格\n'
            '极简直接 · 只说结论和行动项\n'
            '不寒暄不铺垫 · 语气干脆\n'
            '\n'
            '### 回复方式\n'
            '一两句话给结论\n'
            '只在必要时简短解释\n'
            '给明确的行动指令\n'
            '\n'
            '### 注意事项\n'
            '不展开解释机制原理 · 不加安慰性套话\n'
            '危险信号直接说\u201c马上来医院\u201d\n'
            '\n'
            '### 结尾习惯\n'
            '\u201c有事再说\u201d\n'
            '\u201c疼得厉害或者发烧了再联系\u201d'
        ),
        "sample_reply": (
            "都正常的。VAS 5-6分术后第三天没问题，不用加药。体温37.1也正常。"
            "继续观察，疼得厉害或者烧起来了再联系。"
        ),
        "build_fields": _concise_efficient_fields,
    },
    {
        "id": "patient_educator",
        "name": "耐心科普型",
        "subtitle": "善用比喻、分步讲解、帮患者理解为什么",
        "summary_text": (
            '### 沟通风格\n'
            '耐心解释、善用比喻\n'
            '语气平和亲切 · 鼓励患者提问\n'
            '\n'
            '### 回复方式\n'
            '用生活化的比喻解释医学概念\n'
            '分步骤给建议，让患者明白\u201c为什么这样做\u201d\n'
            '适当科普，帮助患者建立自我管理能力\n'
            '\n'
            '### 注意事项\n'
            '不一次给太多信息 · 分主次讲\n'
            '不用太多数字指标，侧重帮患者理解逻辑\n'
            '\n'
            '### 结尾习惯\n'
            '\u201c这样解释清楚吗？有不明白的随时问\u201d\n'
            '\u201c下次复查的时候我们再详细看看\u201d'
        ),
        "sample_reply": (
            "张叔，您说的这三个情况我一个一个给您解释。头疼——手术相当于脑子里做了一次\u201c装修\u201d，"
            "周围组织需要时间恢复，术后三天疼到5-6分是正常的\u201c施工反应\u201d，一般一周左右会明显好转。"
            "伤口肿——就像皮肤磕了一下会鼓包一样，过几天会自己消。体温37.1——没到发烧的标准，"
            "属于身体在修复的正常反应。现在不需要加药，如果哪天觉得比现在疼了，或者开始发烧恶心，"
            "记得马上告诉我。这样说清楚了吗？"
        ),
        "build_fields": _patient_educator_fields,
    },
    {
        "id": "decisive_action",
        "name": "果断指挥型",
        "subtitle": "按紧急程度调语气、给清晰行动路径、不模糊表态",
        "summary_text": (
            '### 沟通风格\n'
            '语气随情况调整：常规问题平和，危险信号果断紧迫\n'
            '称呼正式但不冰冷\n'
            '\n'
            '### 回复方式\n'
            '先判断紧急程度，明确告知\u201c需要重视\u201d或\u201c不用担心\u201d\n'
            '给出清晰的行动路径（去哪里、做什么检查、带什么资料）\n'
            '危险信号给出时间要求（\u201c今天之内\u201d、\u201c立刻\u201d）\n'
            '\n'
            '### 注意事项\n'
            '不模糊表态 · 不说\u201c再观察看看\u201d来回避判断\n'
            '有把握的事直接说，没把握的明确建议进一步检查\n'
            '\n'
            '### 结尾习惯\n'
            '\u201c做完检查把结果发给我，我帮你看\u201d\n'
            '\u201c到了急诊跟他们说术后第X天，他们会优先处理\u201d'
        ),
        "sample_reply": (
            "术后第三天，这个疼痛程度和体温都在正常范围，不用担心。VAS 5-6分不需要加药，"
            "体温37.1不算发热。按现有方案继续。需要注意的是：如果疼痛突然加重超过7分，"
            "或者体温过38.5度，或者出现呕吐，马上联系我或直接去急诊。"
        ),
        "build_fields": _decisive_action_fields,
    },
]
