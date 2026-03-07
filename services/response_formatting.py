from __future__ import annotations

from typing import Any, Optional


def format_record(record: Any) -> str:
    """Return a fully-formatted structured medical record string."""
    lines = ["📋 结构化病历\n"]
    lines.append(f"【主诉】\n{record.chief_complaint}\n")
    if record.history_of_present_illness:
        lines.append(f"【现病史】\n{record.history_of_present_illness}\n")
    if record.past_medical_history:
        lines.append(f"【既往史】\n{record.past_medical_history}\n")
    if record.physical_examination:
        lines.append(f"【体格检查】\n{record.physical_examination}\n")
    if record.auxiliary_examinations:
        lines.append(f"【辅助检查】\n{record.auxiliary_examinations}\n")
    if record.diagnosis:
        lines.append(f"【诊断】\n{record.diagnosis}\n")
    if record.treatment_plan:
        lines.append(f"【治疗方案】\n{record.treatment_plan}\n")
    if record.follow_up_plan:
        lines.append(f"【随访计划】\n{record.follow_up_plan}")
    return "\n".join(lines)


def format_draft_preview(record: Any, patient_name: Optional[str] = None) -> str:
    """Return a formatted draft preview with confirmation instructions."""
    header = "📋 病历草稿（仅供参考，请核实）"
    if patient_name:
        header = f"📋 【{patient_name}】病历草稿（仅供参考，请核实）"
    lines = [header, ""]
    lines.append(f"主诉：{record.chief_complaint}")
    if record.history_of_present_illness:
        lines.append(f"现病史：{record.history_of_present_illness}")
    if record.diagnosis:
        lines.append(f"诊断：{record.diagnosis}")
    if record.treatment_plan:
        lines.append(f"治疗方案：{record.treatment_plan}")
    if record.follow_up_plan:
        lines.append(f"随访：{record.follow_up_plan}")
    lines.append("")
    lines.append("回复【确认】保存 | 回复【取消】放弃")
    return "\n".join(lines)
