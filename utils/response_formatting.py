from __future__ import annotations

import json
from typing import Any, List, Optional


def _parse_tags(record: Any) -> List[str]:
    """Return tags as a list regardless of whether the record is Pydantic or ORM."""
    raw = getattr(record, "tags", None)
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def format_record(record: Any) -> str:
    """Return a mobile-friendly clinical note string."""
    lines = ["📋 病历记录\n"]
    lines.append(getattr(record, "content", None) or "—")
    tags = _parse_tags(record)
    if tags:
        lines.append("\n🏷 " + "  ".join(tags))
    return "\n".join(lines)


def format_draft_preview(record: Any, patient_name: Optional[str] = None) -> str:
    """Return a draft preview with confirmation prompt."""
    header = f"📋 病历草稿 - 【{patient_name}】" if patient_name else "📋 病历草稿"
    lines = [header, ""]
    lines.append(getattr(record, "content", None) or "—")
    tags = _parse_tags(record)
    if tags:
        lines.append("🏷 " + "  ".join(tags))
    scores = getattr(record, "specialty_scores", None) or []
    if scores:
        lines.append("")
        lines.append("📊 量表评分（请核对原始记录）")
        for s in scores:
            score_type = s.get("score_type", "?")
            score_value = s.get("score_value")
            raw_text = s.get("raw_text", "")
            if score_value is not None:
                lines.append(f'  • {score_type}：{score_value}  ("{raw_text}")')
            else:
                lines.append(f'  • {score_type}  ("{raw_text}")')
    lines.extend(["", "「确认」保存 · 「撤销」放弃"])
    return "\n".join(lines)
