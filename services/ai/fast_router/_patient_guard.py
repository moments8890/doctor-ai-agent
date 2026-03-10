"""fast_router 患者提问检测守卫：正则模式组与判断函数。

Patient-question guard patterns for fast_router.
No intra-package dependencies — safe to import directly everywhere.
"""

from __future__ import annotations

import re

# ── Tier 3 patient-question guards ───────────────────────────────────────────
# Patient questions from lay users (CMedQA2 analysis: 45% FP rate without guards).
# The original single monolithic regex has been decomposed into named sub-groups
# for maintainability. Behaviour is identical — _is_patient_question() ORs them all.

# Group 1: Colloquial question phrases — "what should I do", "is it normal?", etc.
# Sources: CMedQA2, CHIP-STS, IMCS-DAC
_QG_COLLOQUIAL_RE = re.compile(
    r"怎么办|怎么回事|是怎么回事|该怎么|是什么原因|有什么办法|有什么方法"
    r"|怎么治疗|如何治疗|会不会|能不能|吃什么药|是什么病"
    r"|有什么关系|正常吗|严重吗|有没有问题|是否严重"
    r"|怎样治疗|怎样用药|怎样处理|怎样调理"
    r"|该如何|该怎样|应该怎么"
    r"|是不是|能否"
    r"|吃什么"
    r"|怎么样[？。]?\s*$"
    r"|如何[？。]?\s*$"
    r"|什么意思[？。]?\s*$"
)

# Group 2: Duration / choice / inquiry patterns (IMCS-DAC)
# "咳嗽几天了", "是夜间严重还是白天严重", "有没有咳嗽"
_QG_DURATION_INQUIRY_RE = re.compile(
    r"几天了$|多久了$|多长时间|多少天了$"
    r"|是.{1,8}还是"
    r"|有没有"
)

# Group 3: Question-ending particles and causal questions
# These particles almost never end a real clinical dictation
_QG_ENDING_PARTICLE_RE = re.compile(
    r"了吗[？?]?$|吗[？?]?$|呢[？?]?$"
    r"|吧[。！？]?\s*$|呀[。！？]?\s*$|么[？！]?\s*$"
    r"|引起的[。？]?\s*$"
    r"|[？?]\s*$"
)

# Group 4: Consultation-seeking openers and patient gratitude (MedDialog-CN / CMID)
_QG_CONSULT_OPENER_RE = re.compile(
    r"请问|请指教|请教|请.*帮.*解答|请.*分析"
    r"|(?:问一下|请教一下|咨询一下|想咨询|想请教|想问一下)"
    r"|(?:求助|求解答|帮我看看|帮忙看看|帮我分析)"
    r"|(?:感谢|谢谢|万分感谢)(?:医生|大夫|您|你)"
)

# Group 5: Patient addressing the doctor by name/title
# "医生您好", "王主任，您好", "李教授您好"
_QG_DOCTOR_ADDR_RE = re.compile(
    r"医生您好|医生你好|大夫您好|大夫你好"
    r"|[\u4e00-\u9fff]{1,4}(?:主任|教授)[，,]?您好"
)

# Group 6: First-person family-member reference (MedDialog-CN)
# "我妈妈…", "我父亲…" — near-absent in clinical dictation
_QG_FAMILY_REF_RE = re.compile(
    r"我(?:妈|爸|母亲|父亲|女儿|儿子|老公|老婆|爱人|孩子|宝宝|小孩|家人|丈夫|妻子)"
)

# Group 7: Knowledge / disease query suffixes (Baidu finetune, CHIP-STS)
# "高血压的治疗方法", "肺癌的并发症有", "xxx有什么症状吗"
_QG_KNOWLEDGE_QUERY_RE = re.compile(
    r"的鉴别诊断$|的并发症$|的并发症有|的症状有哪些|的诊断依据|的发病机制|的病因$|的病因有"
    r"|的治疗方法|的处理原则|的预防措施|的检查方法"
    r"|的定义[？。]?\s*$|的危害[？。]?\s*$|的影响[？。]?\s*$|的护理[？。]?\s*$"
    r"|有什么.*(?:吗|呢)[？?]?\s*$"
)

# Group 8: MCQ stems — explicit question words in exam questions (CMExam)
# "下列哪项", "哪种药物", "正确的是", "最佳方案是"
_QG_MCQ_STEM_RE = re.compile(
    r"^下列|^以下(?:哪|各)项|正确的是$|错误的是$|不正确的是$|不包括$"
    r"|属于.*的是$|应首选$|最可能.*诊断$|最佳.*是$"
    r"|哪种|哪项|哪个|哪类|哪些"
    r"|何药|何种|何法"
)

# Group 9: MCQ answer endings without doctor anchor — non-vignette CMExam questions
# Vignette patterns (starting with "患者，男，N岁…") are handled by _TIER3_EXAM_ENDING_RE.
# These endings appear in standalone MCQs that don't trigger the doctor anchor.
_QG_MCQ_ENDING_RE = re.compile(
    r"考虑的是[：:]?\s*$|的(?:疾病|症状|体征|病因|改变|类型)是[：:]?\s*$"
    r"|(?:特点|原因|表现|机制|体征|检查|热型)是[：:]?\s*$"
    r"|(?:最?常?多?)见于\s*$|可见于\s*$|常伴有\s*$|放射至\s*$"
    r"|治疗应首选\s*$|意义的是[：:]?\s*$"
    r"|(?:药物|成药|方剂|措施|方法|方案|证候|证型|治法|病原体)是\s*$"
    r"|(?:并发症|不良反应)是\s*$|诊断为\s*$|部位在\s*$"
    r"|是[：:]?\s*$|为[：:]?\s*$|属于\s*$|体位\s*$|类型\s*$"
    r"|出现\s*$|宜用\s*$|选用\s*$|宜选用\s*$|不宜用\s*$"
)

# Group 10: Structured patient portal format + demographic tag (Baidu list, CHIP-MDCFNPC)
# "全部症状：…", "(男，45岁)" at message end
_QG_PATIENT_PORTAL_RE = re.compile(
    r"全部症状[：:]|发病时间及原因|治疗情况[：:]|发病时间[：:]"
    r"|[（(](?:男|女)[，,]?\s*\d+岁[）)][。！]?\s*$"
)

# Group 11: Baidu encyclopedia Q+A format — question word before ？ + long answer after
# Requires a question word before ？ to avoid matching BP "170/？mmhg" or differential "肿瘤？"
_QG_BAIDU_ENCYC_RE = re.compile(
    r"^.{0,35}(?:什么|如何|怎么|怎样|会.{0,8}吗|能.{0,8}吗|多久|可以|为什么|是否).{0,15}[？?].{20,}"
)


def _is_patient_question(text: str) -> bool:
    """Return True if the text matches any patient-question guard pattern.

    Checks all 11 named sub-groups. Replaces the former monolithic
    ``_TIER3_QUESTION_RE`` for maintainability; semantics are identical.
    """
    return bool(
        _QG_COLLOQUIAL_RE.search(text)
        or _QG_DURATION_INQUIRY_RE.search(text)
        or _QG_ENDING_PARTICLE_RE.search(text)
        or _QG_CONSULT_OPENER_RE.search(text)
        or _QG_DOCTOR_ADDR_RE.search(text)
        or _QG_FAMILY_REF_RE.search(text)
        or _QG_KNOWLEDGE_QUERY_RE.search(text)
        or _QG_MCQ_STEM_RE.search(text)
        or _QG_MCQ_ENDING_RE.search(text)
        or _QG_PATIENT_PORTAL_RE.search(text)
        or _QG_BAIDU_ENCYC_RE.search(text)
    )
