from __future__ import annotations

from typing import Any, Optional


def _t(s: str | None, n: int = 35) -> str:
    """Truncate string for mobile display."""
    if not s:
        return ""
    return s[:n] + "…" if len(s) > n else s


def format_record(record: Any) -> str:
    """Return a compact mobile-friendly structured medical record string."""
    lines = ["📋 病历记录\n"]
    lines.append(f"主诉：{_t(record.chief_complaint, 35)}")
    if record.history_of_present_illness:
        lines.append(f"现病史：{_t(record.history_of_present_illness, 35)}")
    if record.past_medical_history:
        lines.append(f"既往史：{_t(record.past_medical_history, 35)}")
    if record.physical_examination:
        lines.append(f"体格检查：{_t(record.physical_examination, 35)}")
    if record.auxiliary_examinations:
        lines.append(f"辅助检查：{_t(record.auxiliary_examinations, 35)}")
    if record.diagnosis:
        lines.append(f"诊断：{_t(record.diagnosis, 35)}")
    if record.treatment_plan:
        lines.append(f"治疗方案：{_t(record.treatment_plan, 35)}")
    if record.follow_up_plan:
        lines.append(f"随访计划：{_t(record.follow_up_plan, 35)}")
    return "\n".join(lines)


def format_draft_preview(record: Any, patient_name: Optional[str] = None) -> str:
    """Return a compact draft preview with confirmation instructions."""
    if patient_name:
        header = f"📋 病历草稿 - 【{patient_name}】"
    else:
        header = "📋 病历草稿"
    lines = [header, ""]
    lines.append(f"主诉：{_t(record.chief_complaint, 35)}")
    if record.diagnosis:
        lines.append(f"诊断：{_t(record.diagnosis, 35)}")
    if record.treatment_plan:
        lines.append(f"治疗方案：{_t(record.treatment_plan, 35)}")
    if record.follow_up_plan:
        lines.append(f"随访：{_t(record.follow_up_plan, 35)}")
    lines.append("")
    lines.append("「确认」保存  「取消」放弃")
    return "\n".join(lines)
