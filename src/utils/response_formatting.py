"""病历记录与草稿的移动端友好文本格式化工具。"""
from __future__ import annotations

import json
from typing import Any, List, Optional


def parse_tags(raw: Any) -> List[str]:
    """Parse a raw tags value (str JSON, list, or None) into a list of strings.

    This is the canonical tag-parsing helper. All modules that need to
    normalise tag data from DB columns or Pydantic fields should call this.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


# Backward-compatible alias kept for any callers using the old private name.
_parse_tags = parse_tags


def build_patient_info_line(patient: Any) -> Optional[str]:
    """Build a concise patient info line (e.g. '男  45岁') from a patient object.

    Used by both web and WeChat export paths to format the outpatient report
    header.  Returns None if no demographic data is available.
    """
    from datetime import date

    parts: list[str] = []
    if getattr(patient, "gender", None):
        parts.append(patient.gender)
    if getattr(patient, "year_of_birth", None):
        age = date.today().year - int(patient.year_of_birth)
        parts.append(f"{age}岁")
    return "  ".join(parts) if parts else None


def format_record(record: Any) -> str:
    """Return a mobile-friendly clinical note string."""
    lines = ["📋 病历记录\n"]
    lines.append(getattr(record, "content", None) or "—")
    tags = parse_tags(getattr(record, "tags", None))
    if tags:
        lines.append("\n🏷 " + "  ".join(tags))
    return "\n".join(lines)


