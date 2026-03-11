"""
聊天路由常量：正则表达式、提示词模板和解析工具函数。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional


# ── Pattern-match constants ──────────────────────────────────────────────────

COMPLETE_RE = re.compile(r'^\s*完成\s*(\d+)\s*$')
DELETE_BY_ID_RE = re.compile(r'^\s*(?:删除|删掉|移除)\s*(?:患者|病人)?\s*(?:ID|id)\s*(\d+)\s*$')
DELETE_PATIENT_RE = re.compile(
    r'^\s*(?:删除|删掉|移除)\s*(?:第\s*([一二三四五六七八九十两\d]+)\s*个\s*)?(?:患者|病人)?\s*([\u4e00-\u9fff]{2,20})\s*$'
)
SCHEDULE_APPOINTMENT_RE = re.compile(
    r'^\s*(?:给|为)?\s*([\u4e00-\u9fff]{2,20}?)(?:安排)?(?:预约|复诊|约诊)\s*(.+?)\s*$'
)
PATIENT_COUNT_RE = re.compile(
    r"(我(?:现有|现在)?(?:有|管理)?多少(?:位)?(?:病人|患者)|现在有几个(?:病人|患者)|(?:病人|患者)总数)"
)
CONTEXT_SAVE_RE = re.compile(r'^\s*(?:总结上下文|保存上下文)(?:[:：]\s*(.*))?\s*$')
GREETING_RE = re.compile(
    r"^(?:你好|您好|hi|hello|嗨|哈喽|早上好|下午好|晚上好|早|在吗|在不在)[！!？?。，,\s]*$",
    re.IGNORECASE,
)
MENU_NUMBER_RE = re.compile(r"^\s*([1-7])\s*$")
VOICE_TRANSCRIPTION_PREFIX_RE = re.compile(r"^语音转文字[：:]\s*")

CN_ORDINAL = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

# ── Reply templates ───────────────────────────────────────────────────────────

UNCLEAR_INTENT_REPLY = "没太理解您的意思，能说得更具体一些吗？发送「帮助」可查看完整功能列表。"

HELP_REPLY = (
    "📥 导入患者（最常用）\n"
    "  直接发送 PDF / 图片 — 自动识别并创建\n"
    "  粘贴聊天记录 — 将微信问诊记录直接发过来，自动提取患者信息和病历\n"
    "  支持：出院小结、门诊病历、检验报告、问诊截图\n\n"
    "📋 患者管理\n"
    "  创建[姓名] — 创建新患者\n"
    "  查看[姓名] — 查看患者病历\n"
    "  删除[姓名] — 删除患者\n"
    "  患者列表 — 显示全部患者\n\n"
    "📝 病历\n"
    "  [描述病情] — 自动保存结构化病历\n"
    "  补充：... — 补充当前患者记录\n"
    "  刚才写错了，应该是... — 修正上一条\n\n"
    "📌 任务\n"
    "  待办任务 — 查看所有任务\n"
    "  完成 3 — 标记任务#3完成\n"
    "  3个月后随访 — 安排随访提醒\n\n"
    "📊 其他\n"
    "  开始问诊 — 开启结构化问诊流程\n"
    "  PDF:患者姓名 — 导出病历PDF"
)

WARM_GREETING_REPLY = (
    "您好！我是您的专属医助，很高兴为您服务。\n\n"
    "我可以帮您：\n"
    "• 建立患者档案（如：新患者张三，男，45岁）\n"
    "• 快速录入门诊病历（如：张三，胸痛2小时）\n"
    "• 查询患者历史记录（如：查询张三）\n"
    "• 管理待办任务和随访提醒\n\n"
    "请直接说您想做什么，或描述患者情况开始录入。"
)

MENU_PROMPTS = {
    "1": "好的，请提供新患者的姓名和基本信息。\n示例：张三，男，45岁",
    "2": "好的，请说明患者姓名和本次病情。\n示例：张三，胸痛2小时",
    "3": "好的，请告诉我要查询的患者姓名。\n示例：查询张三",
    "5": "好的，请告诉我要删除的患者姓名。\n示例：删除张三",
    "7": "好的，请提供患者姓名和随访时间。\n示例：张三 3个月后随访",
}

# ── Parsing helpers ───────────────────────────────────────────────────────────

def parse_delete_patient_target(
    text: str,
) -> tuple[Optional[int], Optional[str], Optional[int]]:
    """Parse delete command into (patient_id_by_num, name, occurrence_index)."""
    by_id = DELETE_BY_ID_RE.match((text or "").strip())
    if by_id:
        return int(by_id.group(1)), None, None

    by_name = DELETE_PATIENT_RE.match((text or "").strip())
    if not by_name:
        return None, None, None
    ordinal_raw, patient_name = by_name.group(1), by_name.group(2)
    occurrence_index = None
    if ordinal_raw:
        occurrence_index = CN_ORDINAL.get(ordinal_raw)
        if occurrence_index is None and ordinal_raw.isdigit():
            occurrence_index = int(ordinal_raw)
    return None, patient_name.strip(), occurrence_index


# ── Content classification hints ─────────────────────────────────────────────

CLINICAL_CONTENT_HINTS = (
    "胸痛", "胸闷", "心悸", "头痛", "发热", "咳嗽", "气短",
    "ST", "PCI", "BNP", "EF", "诊断", "治疗", "复查", "化疗", "靶向",
)

TREATMENT_HINTS = (
    "用药", "开药", "处方", "给予", "服用", "口服", "静滴", "输液",
    "手术", "PCI", "pci", "CTA", "cta", "介入", "化疗", "放疗", "靶向", "治疗", "方案", "plan",
)

REMINDER_IN_MSG_RE = re.compile(
    r"(?:下午|明天|早上|晚上|今天|稍后|待会|一会儿?)?[，,\s]*提醒我\s*(.{2,20}?)(?:[。！\s]|$)"
)

CREATE_PREAMBLE_RE = re.compile(
    r"^(?:帮我?|请)?(?:录入|建立|新建|创建)"
    r"(?:.*?(?:新病人|新患者|患者|病人))?"
    r"\s*[，,]?\s*[\u4e00-\u9fff]{2,4}\s*[，,]?"
    r"(?:\s*[男女](?:性)?\s*[，,]?)?"
    r"(?:\s*\d+\s*岁\s*[，,。]?)?\s*",
    re.DOTALL,
)

SUPPORTED_AUDIO_TYPES = frozenset({
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm",
    "audio/ogg", "audio/flac", "audio/m4a", "audio/x-m4a",
})

SUPPORTED_IMAGE_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/gif",
})


def normalize_human_datetime(raw: str) -> Optional[str]:
    """Normalize a Chinese date/time string to ISO-8601."""
    candidate = (raw or "").strip()
    if not candidate:
        return None

    normalized = (
        candidate.replace("年", "-")
        .replace("月", "-")
        .replace("日", " ")
        .replace("时", ":")
        .replace("分", "")
        .replace("/", "-")
        .strip()
    )
    normalized = re.sub(r"\s+", " ", normalized)

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(normalized, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=9, minute=0, second=0)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None
