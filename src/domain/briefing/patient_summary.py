"""Patient AI summary — 1-2 sentence clinical snapshot.

Regenerated incrementally each time a new record lands for a patient. Result
is stored on ``patients.ai_summary`` so the UI can render instantly without
an LLM call per page open.

Usage:
    await regenerate_patient_summary(patient_id=123, db=session)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from utils.log import log


# ── LLM response model ──────────────────────────────────────────────


class PatientSummaryResponse(BaseModel):
    summary: str


# ── Fact pack ───────────────────────────────────────────────────────


_STRUCTURED_KEYS = [
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "family_history",
    "personal_history",
    "physical_exam",
    "auxiliary_exam",
    "diagnosis",
    "treatment_plan",
    "orders_followup",
]


async def _load_patient(db: AsyncSession, patient_id: int) -> Optional[Patient]:
    stmt = select(Patient).where(Patient.id == patient_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def _load_recent_records(
    db: AsyncSession, patient_id: int, limit: int = 5
) -> list[MedicalRecordDB]:
    stmt = (
        select(MedicalRecordDB)
        .where(MedicalRecordDB.patient_id == patient_id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


def _build_fact_block(patient: Patient, records: list[MedicalRecordDB]) -> str:
    """Produce a compact text block the LLM can summarise.

    MedicalRecordDB stores the clinical fields as top-level columns
    (diagnosis, past_history, allergy_history, …), not nested under a
    ``structured`` attribute — so we read them directly via getattr.
    """
    lines = [f"患者：{patient.name}"]
    if patient.gender:
        lines.append(f"性别：{patient.gender}")
    if patient.year_of_birth:
        age = datetime.now().year - patient.year_of_birth
        lines.append(f"年龄：{age}岁")

    for idx, r in enumerate(records):
        date = r.created_at.strftime("%Y-%m-%d") if r.created_at else ""
        type_label = r.record_type or "记录"
        lines.append(f"\n── 记录 {idx + 1}（{type_label} · {date}）──")

        has_structured = False
        for key in _STRUCTURED_KEYS:
            val = getattr(r, key, None)
            if val and str(val).strip():
                has_structured = True
                lines.append(f"{key}：{val}")

        # Fallback to raw content if no structured fields
        if not has_structured and r.content:
            lines.append(f"content：{r.content[:400]}")
    return "\n".join(lines)


def _build_messages(fact_block: str) -> list[dict]:
    # 2026-04-27 prompt rewrite (Codex r3 verdict): the previous prompt
    # produced "structured restatement" — restated diagnosis/treatment/
    # allergy that the page's 临床资料 card already shows. Doctor-facing
    # value of this card lives in synthesis the structured cards CAN'T
    # express: cross-visit narrative, field-spanning risk concerns,
    # trajectory. Anything else returns empty so the UI can hide.
    return [
        {
            "role": "system",
            "content": (
                "你是临床AI助手。这条摘要只用于医生在患者详情页顶部快速理解病情，"
                "页面下方已有「临床资料」卡（独立显示诊断、用药、过敏、既往史、家族史），"
                "页面下方已有「需要你处理」「待回复」等动作卡（显示待审核/待回复事项）。\n"
                "你的输出只允许包含以下三种「综合性」内容之一或组合，且每条必须基于 patient_facts："
                "\n1. 跨次就诊叙事：用 1-2 句话描述近 N 次门诊连起来的故事"
                "（例：'近3次门诊主诉头痛持续，调整为新止痛方案后症状改善'）；"
                "\n2. 字段间风险关联：把多个字段连起来构成一个临床关注点"
                "（例：'糖尿病 + 反复头痛 + 青霉素过敏 — 用药需避开青霉素，建议明确血糖控制'）；"
                "\n3. 病情趋势：症状是 改善 / 加重 / 稳定（仅当多次记录支持时）。"
                "\n严禁：复述单条记录的诊断、用药、过敏、就诊次数（这些下方已有），"
                "客套话，编造未知信息，AI口吻（'AI建议'/'我认为'）。"
                "\n若 patient_facts 不足以做出上述任何一种综合，返回空字符串。"
                "\n语言：中文，不超过 80 字。"
            ),
        },
        {
            "role": "user",
            "content": f"<patient_facts>\n{fact_block}\n</patient_facts>",
        },
    ]


# ── Public API ──────────────────────────────────────────────────────


async def regenerate_patient_summary(
    *, patient_id: int, db: AsyncSession
) -> Optional[str]:
    """Regenerate ``ai_summary`` for one patient. Returns the new summary text,
    or None on failure (DB untouched on failure).
    """
    patient = await _load_patient(db, patient_id)
    if not patient:
        return None
    records = await _load_recent_records(db, patient_id, limit=5)
    if not records:
        # Nothing to summarise — clear any stale summary so UI shows fallback.
        patient.ai_summary = None
        patient.ai_summary_at = datetime.now(timezone.utc)
        patient.ai_summary_model = None
        await db.flush()
        return None

    fact_block = _build_fact_block(patient, records)
    messages = _build_messages(fact_block)

    try:
        from agent.llm import structured_call

        env_var = "CONVERSATION_LLM" if os.environ.get("CONVERSATION_LLM") else "ROUTING_LLM"
        result = await structured_call(
            response_model=PatientSummaryResponse,
            messages=messages,
            op_name="patient_summary.generate",
            env_var=env_var,
            temperature=0.2,
            max_tokens=1024,
        )
    except Exception as e:  # noqa: BLE001 — LLM failures shouldn't block record save
        log(f"[patient_summary] LLM failed for patient={patient_id}: {e}")
        return None

    summary_text = (result.summary or "").strip()
    if not summary_text:
        return None

    patient.ai_summary = summary_text
    patient.ai_summary_at = datetime.now(timezone.utc)
    patient.ai_summary_model = os.environ.get(env_var) or env_var
    await db.flush()
    log(f"[patient_summary] regenerated patient={patient_id} len={len(summary_text)}")
    return summary_text
