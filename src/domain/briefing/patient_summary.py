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
    return [
        {
            "role": "system",
            "content": (
                "你是临床AI助手。用一两句中文总结这位患者当前的临床状态，"
                "面向医生阅读。包含关键诊断、用药、过敏风险和近期变化。"
                "不写寒暄；不超过80字；不臆造未知信息。"
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
