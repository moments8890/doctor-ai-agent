"""One-shot backfill: regenerate ai_summary for every patient that has records.

Run after the f4a2c17b9d10 migration. Iterates through patients sequentially
and regenerates their AI summary via the same path save_record uses. Safe to
re-run — already-summarised patients are refreshed in-place.

Usage:
    cd src && ENVIRONMENT=development ../.venv/bin/python \
        -m scripts.backfill_patient_summary \
        [--doctor-id DOCTOR_ID] [--limit N] [--only-empty]

    --doctor-id:  only backfill patients for this doctor
    --limit:      process at most N patients (default: no limit)
    --only-empty: skip patients that already have an ai_summary
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from domain.briefing.patient_summary import regenerate_patient_summary


async def _patients_with_records(
    db: AsyncSession,
    doctor_id: Optional[str],
    only_empty: bool,
) -> list[Patient]:
    stmt = (
        select(Patient)
        .join(MedicalRecordDB, MedicalRecordDB.patient_id == Patient.id)
        .distinct()
        .order_by(Patient.id.asc())
    )
    if doctor_id:
        stmt = stmt.where(Patient.doctor_id == doctor_id)
    if only_empty:
        stmt = stmt.where(Patient.ai_summary.is_(None))
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--doctor-id", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-empty", action="store_true")
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        patients = await _patients_with_records(
            session, args.doctor_id, args.only_empty
        )

    if args.limit:
        patients = patients[: args.limit]

    print(f"Backfilling {len(patients)} patients...")
    ok, failed = 0, 0
    for i, p in enumerate(patients, start=1):
        try:
            async with AsyncSessionLocal() as session:
                summary = await regenerate_patient_summary(
                    patient_id=p.id, db=session
                )
                await session.commit()
            status = "✓" if summary else "·"
            print(f"  [{i}/{len(patients)}] {status} patient={p.id} {p.name}")
            if summary:
                ok += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  [{i}/{len(patients)}] ✗ patient={p.id} {p.name} — {e}")

    print(f"\nDone. {ok} regenerated · {failed} failed · {len(patients) - ok - failed} empty")


if __name__ == "__main__":
    asyncio.run(main())
