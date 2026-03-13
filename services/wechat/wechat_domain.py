"""
WeChat 意图处理层：菜单事件、患者列表、历史导入等 WeChat 专属逻辑。

Most intent handlers (create_patient, add_record, query_records, etc.) have
been moved to the shared layer at ``services/domain/intent_handlers/``.
name_lookup is still handled at the WeChat router level in
``routers/wechat_flows.py:handle_name_lookup()``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from db.crud import get_all_patients
from db.engine import AsyncSessionLocal
from utils.response_formatting import format_record
from utils.text_parsing import (
    explicit_name_or_none,
    looks_like_symptom_note,
)
from utils.log import log

# Re-export from sub-modules for backward compatibility
from services.wechat.wechat_export import (
    handle_export_records,
    handle_export_outpatient_report,
)
from services.wechat.wechat_import import (
    handle_import_history,
    _chunk_history_text,
    _preprocess_import_text,
    _format_import_preview,
    _mark_duplicates,
)


from utils.runtime_config import get_pending_record_ttl_minutes as _get_ttl
_DRAFT_TTL_MINUTES = _get_ttl()

_MENU_EVENT_REPLIES = {
    "DOCTOR_NEW_PATIENT": "🆕 请发送患者信息，例如：帮我建个新患者，张三，30岁男性。",
    "DOCTOR_ADD_RECORD": "📝 请发送病历描述，AI 将自动生成结构化病历并保存。",
    "DOCTOR_QUERY": "🔍 请发送患者姓名，例如：查询张三的病历。",
}


def extract_open_kfid(msg: Any) -> str:
    target = getattr(msg, "target", "")
    if isinstance(target, str):
        return target.strip()
    return ""


def extract_cdata(xml_str: str, tag: str) -> str:
    m = re.search(rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", xml_str)
    if m:
        return m.group(1)
    m = re.search(rf"<{tag}>([^<]+)</{tag}>", xml_str)
    return m.group(1) if m else ""



# save_pending_record is now in the shared handler layer
from services.domain.intent_handlers._confirm_pending import save_pending_record  # noqa: F401


async def handle_all_patients(doctor_id: str) -> str:
    async with AsyncSessionLocal() as session:
        patients = await get_all_patients(session, doctor_id)
    if not patients:
        return "📂 暂无患者记录。发送「新患者姓名，年龄性别」可创建第一位患者。"
    lines = [f"👥 共 {len(patients)} 位患者\n"]
    for i, p in enumerate(patients, 1):
        age_display = f"{datetime.now().year - p.year_of_birth}岁" if p.year_of_birth else ""
        parts = [x for x in [p.gender, age_display] if x]
        info = "·".join(parts)
        suffix = f"（{info}）" if info else ""
        lines.append(f"{i}. {p.name}{suffix}")
    lines.append("\n发「查询[姓名]」看病历")
    return "\n".join(lines)


async def handle_menu_event(event_key: str, doctor_id: str) -> str:
    if event_key == "DOCTOR_ALL_PATIENTS":
        return await handle_all_patients(doctor_id)
    return _MENU_EVENT_REPLIES.get(event_key, "请通过菜单或文字与我们互动。")


# WeCom KF message parsing helpers (re-exported from wechat_bg)
from services.wechat.wechat_bg import wecom_kf_msg_to_text, wecom_msg_is_processable, wecom_msg_time
