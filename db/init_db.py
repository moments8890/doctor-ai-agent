"""
数据库初始化：创建所有表。Schema 演进由 Alembic (alembic upgrade head) 管理。
"""

import db.models  # noqa: F401 — ensure models are registered before create_all
import re
from db.engine import Base, engine, AsyncSessionLocal
from db.models import Doctor, Patient, MedicalRecordDB, DoctorTask, NeuroCaseDB, DoctorContext, PatientLabel
from sqlalchemy import select


async def create_tables() -> None:
    """Create all tables from ORM metadata (idempotent for new installs).

    Schema evolution (ADD COLUMN, indexes) is handled by Alembic migrations
    run separately via _run_alembic_migrations() in main.py startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_prompts() -> None:
    """Seed all AI prompts to DB on first startup (idempotent).

    New keys are only written if the row doesn't exist yet, so DB edits made
    via the admin UI are never overwritten.  Exception: ``structuring.neuro_cvd``
    is always upserted so expanded field definitions reach production on deploy.
    """
    from services.ai.structuring import _SEED_PROMPT, _CONSULTATION_SUFFIX, _FOLLOWUP_SUFFIX
    from services.ai.neuro_structuring import _SEED_PROMPT as _NEURO_SEED, _FAST_CVD_PROMPT
    from services.ai.agent import _SYSTEM_PROMPT, _SYSTEM_PROMPT_COMPACT
    from services.ai.memory import _COMPRESS_PROMPT_TEMPLATE
    from services.ai.vision import _SYSTEM_PROMPT as _VISION_PROMPT
    from services.ai.transcription import _MEDICAL_PROMPT, _CONSULTATION_PROMPT
    from services.ai.intent import SYSTEM_PROMPT as _INTENT_PROMPT
    from services.patient.score_extraction import _EXTRACTION_PROMPT
    from services.wechat.patient_pipeline import _PATIENT_SYSTEM_PROMPT
    from services.export.outpatient_report import _EXTRACT_PROMPT
    from db.crud import get_system_prompt, upsert_system_prompt

    # Seed-only entries: only write when the key is missing (preserves DB edits).
    _SEED_ONLY: list[tuple[str, str]] = [
        ("agent.routing",                   _SYSTEM_PROMPT),
        ("agent.routing.compact",            _SYSTEM_PROMPT_COMPACT),
        ("agent.intent_classifier",          _INTENT_PROMPT),
        ("structuring",                      _SEED_PROMPT),
        ("structuring.consultation_suffix",  _CONSULTATION_SUFFIX),
        ("structuring.followup_suffix",      _FOLLOWUP_SUFFIX),
        ("structuring.fast_cvd",             _FAST_CVD_PROMPT),
        ("memory.compress",                  _COMPRESS_PROMPT_TEMPLATE),
        ("vision.ocr",                       _VISION_PROMPT),
        ("transcription.medical",            _MEDICAL_PROMPT),
        ("transcription.consultation",       _CONSULTATION_PROMPT),
        ("extraction.specialty_scores",      _EXTRACTION_PROMPT),
        ("patient.chat",                     _PATIENT_SYSTEM_PROMPT),
        ("report.extract",                   _EXTRACT_PROMPT),
    ]

    async with AsyncSessionLocal() as db:
        for key, content in _SEED_ONLY:
            existing = await get_system_prompt(db, key)
            if not existing:
                await upsert_system_prompt(db, key, content)

        # Always upsert neuro_cvd so expanded field definitions reach production on deploy.
        await upsert_system_prompt(db, "structuring.neuro_cvd", _NEURO_SEED)


async def backfill_doctors_registry() -> int:
    """Populate doctors table from historical tables (idempotent)."""
    wechat_re = re.compile(r"^(?:wm|wx|ww|wo)[A-Za-z0-9_-]{6,}$")
    doctor_ids = set()
    doctor_sources = [
        Patient.doctor_id,
        MedicalRecordDB.doctor_id,
        DoctorTask.doctor_id,
        NeuroCaseDB.doctor_id,
        DoctorContext.doctor_id,
        PatientLabel.doctor_id,
    ]

    async with AsyncSessionLocal() as db:
        for col in doctor_sources:
            rows = (await db.execute(select(col).where(col.is_not(None)))).scalars().all()
            for value in rows:
                if isinstance(value, str) and value.strip():
                    doctor_ids.add(value.strip())

        existing_rows = (await db.execute(select(Doctor))).scalars().all()
        existing = {row.doctor_id for row in existing_rows}
        missing = sorted(doctor_ids - existing)
        for doctor_id in missing:
            is_wechat = bool(wechat_re.match(doctor_id))
            db.add(
                Doctor(
                    doctor_id=doctor_id,
                    channel="wechat" if is_wechat else "app",
                    wechat_user_id=doctor_id if is_wechat else None,
                )
            )

        # Backfill existing rows with identity metadata where possible.
        updated_existing = False
        seen_wechat = set()
        for row in existing_rows:
            if not isinstance(row.doctor_id, str):
                continue
            doctor_id = row.doctor_id.strip()
            if not doctor_id:
                continue
            is_wechat = bool(wechat_re.match(doctor_id))
            if not getattr(row, "channel", None):
                row.channel = "wechat" if is_wechat else "app"
                updated_existing = True
            if is_wechat and not getattr(row, "wechat_user_id", None) and doctor_id not in seen_wechat:
                row.wechat_user_id = doctor_id
                updated_existing = True
            if getattr(row, "wechat_user_id", None):
                seen_wechat.add(str(row.wechat_user_id))
        if missing or updated_existing:
            await db.commit()
        return len(missing)
