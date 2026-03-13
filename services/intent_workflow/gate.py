"""Layer 5: Execution gate — safety checks before executing planned actions.

Rules:
1. Write intents with no patient binding -> block and ask for name.
2. Weak binding (candidate) from not_found source without location context -> block.
3. Weak binding with review flag -> allow but flag for confirmation.
4. Read intents -> always allow.
"""

from __future__ import annotations

import re

from services.ai.intent import Intent

from .models import (
    HERO_WRITE_INTENTS as _HERO_WRITE_INTENTS,
    ActionPlan,
    BindingDecision,
    EntityResolution,
    GateResult,
)

_LOCATION_CONTEXT_RE = re.compile(
    r"(?:ICU|PACU|CCU|NICU|急诊|抢救室|手术室|监护室|留观|绿色通道"
    r"|\d+床|\d+号床|[A-Z]?\d+病房|[A-Z]?\d+号)",
    re.IGNORECASE,
)

def check_gate(
    plan: ActionPlan,
    decision_intent: Intent,
    entities: EntityResolution,
    binding: BindingDecision,
    text: str,
) -> GateResult:
    """Check whether planned actions should proceed."""
    if decision_intent not in _HERO_WRITE_INTENTS:
        return GateResult(approved=True)

    # create_patient needs the shared handler to set pending-create state
    # when the doctor has not supplied a name yet.
    if decision_intent == Intent.create_patient and binding.status == "no_name":
        return GateResult(approved=True)

    # delete_patient: block when name was inherited from stale context
    # (session/history) rather than explicitly stated by the doctor.
    if decision_intent == Intent.delete_patient:
        _name_source = entities.patient_name.source if entities.patient_name else None
        if _name_source in ("session", "history"):
            name = binding.patient_name or "未知"
            return GateResult(
                approved=False,
                reason="delete_needs_explicit_name",
                clarification_message=f"您要删除患者【{name}】吗？请再次输入患者姓名以确认。",
            )

    # Multi-patient conflict -> ask which patient
    _multi = (entities.extra_data or {}).get("multi_patient_names")
    if _multi and len(_multi) >= 2:
        names_str = "、".join(f"【{n}】" for n in _multi)
        return GateResult(
            approved=False,
            reason="multi_patient_conflict",
            clarification_message=f"检测到多位患者：{names_str}，请问您要为哪位患者操作？",
        )

    # No patient context at all -> ask
    if binding.status == "no_name":
        return GateResult(
            approved=False,
            reason="no_patient_name",
            clarification_message="请问这位患者叫什么名字？",
        )

    # Not-found source without location context -> block
    if (
        binding.source == "not_found"
        and not _LOCATION_CONTEXT_RE.search(text or "")
    ):
        name = binding.patient_name or "未知"
        return GateResult(
            approved=False,
            reason="weak_attribution_no_location",
            clarification_message=f"未找到患者【{name}】，请先创建患者或明确指定患者姓名。",
        )

    # Weak binding -> allow but flag for confirmation
    if binding.needs_review:
        name = binding.patient_name or "未知"
        if binding.source == "candidate":
            msg = f"⚠️ 已为候选患者【{name}】生成病历草稿，请核实患者信息后确认保存。"
        elif binding.source == "not_found":
            msg = f"⚠️ 未找到【{name}】，已为新患者生成病历草稿，请核实后确认保存。"
        else:
            msg = None
        return GateResult(
            approved=True,
            requires_confirmation=True,
            reason="weak_attribution",
            clarification_message=msg,
        )

    return GateResult(approved=True)
