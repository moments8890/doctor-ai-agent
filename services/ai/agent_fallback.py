"""
正则兜底路由：当 LLM 调用失败或未返回工具调用时，通过关键词规则推断意图。
包含患者姓名提取、意图关键词匹配等本地回退逻辑，无需网络请求。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from services.ai.intent import Intent, IntentResult

# ---------------------------------------------------------------------------
# Name extraction patterns and blocklist
# ---------------------------------------------------------------------------

_NAME_PATTERNS = [
    re.compile(r"(?:新患者|新病人|查询)\s*[:：，,\s]*([\u4e00-\u9fff]{2,4})"),
    re.compile(r"(?:患者|病人)\s*([\u4e00-\u9fff]{2,4})(?:[，,。:：\s]|男|女|$)"),
    re.compile(r"^([\u4e00-\u9fff]{2,4})(?:门诊记录|复查|，|,|。|\s)"),
    re.compile(r"([\u4e00-\u9fff]{2,4})门诊记录"),
]

_BAD_NAME_TOKENS = {
    "患者", "病人", "新患者", "新病人", "门诊", "复查", "记录", "查询", "提醒",
    "胸痛", "胸闷", "心悸", "咳嗽", "头痛", "发热", "化疗", "术后", "治疗", "安排",
}

_CLINICAL_KEYWORDS = [
    "胸痛", "胸闷", "心悸", "气短", "头痛", "发热", "咳嗽",
    "心电图", "CT", "MRI", "BNP", "EF", "ST", "PCI", "化疗", "靶向", "诊断",
    "治疗", "复查", "门诊", "术后", "高血压", "肿瘤", "肺癌",
]

_CN_NUM_MAP = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _extract_name_gender_age(text: str) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """从文本中提取患者姓名、性别、年龄。"""
    name = None
    for pattern in _NAME_PATTERNS:
        m = pattern.search(text)
        if m:
            candidate = m.group(1)
            if candidate and candidate not in _BAD_NAME_TOKENS:
                name = candidate
                break
    gender_m = re.search(r"(男|女)", text)
    age_m = re.search(r"(\d{1,3})\s*岁", text)
    gender = gender_m.group(1) if gender_m else None
    age = int(age_m.group(1)) if age_m else None
    return name, gender, age


def _parse_occurrence_index(text: str) -> Optional[int]:
    """解析「第N个」中的序号，支持汉字和阿拉伯数字。"""
    m = re.search(r"第\s*([一二三四五六七八九十两\d]+)\s*个", text)
    if not m:
        return None
    raw = m.group(1)
    if raw in _CN_NUM_MAP:
        return _CN_NUM_MAP[raw]
    if raw.isdigit():
        return int(raw)
    return None


def _fallback_clinical(text: str, name: Optional[str], gender: Optional[str], age: Optional[int]) -> Optional[IntentResult]:
    """若文本含临床关键词，返回 unknown + clarify（不假设 add_record），否则返回 None。

    Principle: When LLM fails and we only have keyword evidence, we should
    ask the doctor to clarify rather than assume they want to write a record.
    """
    if any(k in text for k in _CLINICAL_KEYWORDS):
        return IntentResult(
            intent=Intent.unknown,
            patient_name=name,
            gender=gender,
            age=age,
            chat_reply="检测到临床内容，请问您需要记录病历还是有其他需要？",
        )
    return None


def _fallback_from_keywords(text: str, lower: str, name: Optional[str], gender: Optional[str], age: Optional[int], occurrence_index: Optional[int]) -> IntentResult:
    """按关键词顺序匹配非临床意图，返回最先匹配的 IntentResult。"""
    if any(k in text for k in ["所有患者", "患者列表", "病人列表", "全部患者"]):
        return IntentResult(intent=Intent.list_patients, patient_name=name)

    if any(k in text for k in ["删除患者", "删除病人", "删除", "移除患者", "移除病人", "删掉患者", "删掉病人"]):
        return IntentResult(
            intent=Intent.delete_patient,
            patient_name=name,
            extra_data={"occurrence_index": occurrence_index},
        )

    if any(k in text for k in ["任务", "待办", "提醒"]):
        return IntentResult(intent=Intent.list_tasks, patient_name=name)

    if re.search(r"(完成|标记完成)\s*\d+", text):
        task_id_m = re.search(r"(\d+)", text)
        return IntentResult(
            intent=Intent.complete_task,
            patient_name=name,
            extra_data={"task_id": int(task_id_m.group(1)) if task_id_m else None},
        )

    if any(k in text for k in ["查询", "历史病历", "病历记录", "调取病历"]):
        return IntentResult(intent=Intent.query_records, patient_name=name)

    if any(k in text for k in ["创建", "新患者", "新病人"]):
        return IntentResult(intent=Intent.create_patient, patient_name=name, gender=gender, age=age)

    if any(k in text for k in ["刚才", "上一条", "写错", "有误", "记错", "改为", "改成", "更正"]):
        return IntentResult(intent=Intent.update_record, patient_name=name, confidence=0.7)

    if any(k in text for k in ["修改", "更新", "更改"]) and any(k in text for k in ["年龄", "性别"]):
        return IntentResult(intent=Intent.update_patient, patient_name=name, gender=gender, age=age, confidence=0.7)

    if any(k in text for k in ["导入", "历史病历", "[PDF:", "[Word:", "全部就诊"]):
        return IntentResult(intent=Intent.import_history, patient_name=name, confidence=0.7)

    if any(k in lower for k in ["hello", "hi", "你好"]):
        return IntentResult(intent=Intent.unknown, chat_reply="您好！有什么可以帮您？")

    return IntentResult(intent=Intent.unknown, patient_name=name, gender=gender, age=age)


def fallback_intent_from_text(text: str) -> IntentResult:
    """LLM 调用失败时的本地正则兜底路由，按优先级依次匹配意图。"""
    lower = text.lower()
    name, gender, age = _extract_name_gender_age(text)
    occurrence_index = _parse_occurrence_index(text)

    # Clinical content takes precedence even when "查询"/"提醒" also appear.
    clinical = _fallback_clinical(text, name, gender, age)
    if clinical is not None:
        return clinical

    return _fallback_from_keywords(text, lower, name, gender, age, occurrence_index)
