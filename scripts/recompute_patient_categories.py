#!/usr/bin/env python
"""CLI to recompute patient categories for all or one doctor's patients.

Usage:
    python scripts/recompute_patient_categories.py [--doctor-id ID] [--dry-run]

Exits with the count of changed rows as the exit code (capped at 255).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

# Ensure the project root is importable when run from scripts/
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Patient, MedicalRecordDB
from services.patient.patient_categorization import categorize_patient


async def _run(doctor_id: str | None, dry_run: bool) -> int:
    async with AsyncSessionLocal() as session:
        query = select(Patient)
        if doctor_id is not None:
            query = query.where(Patient.doctor_id == doctor_id)

        result = await session.execute(query)
        patients = list(result.scalars().all())

        changed = 0
        errors = 0
        for patient in patients:
            try:
                records_result = await session.execute(
                    select(MedicalRecordDB)
                    .where(
                        MedicalRecordDB.patient_id == patient.id,
                        MedicalRecordDB.doctor_id == patient.doctor_id,
                    )
                    .order_by(MedicalRecordDB.created_at.desc())
                )
                records = list(records_result.scalars().all())

                cat_result = categorize_patient(patient, records)

                old_cat = patient.primary_category
                new_cat = cat_result.primary_category
                label = "CHANGED" if old_cat != new_cat else "same"
                print(
                    f"  [{label}] patient_id={patient.id} name={patient.name!r}"
                    f" {old_cat!r} → {new_cat!r}"
                    f" tags={json.dumps(cat_result.category_tags, ensure_ascii=False)}"
                )
                if old_cat != new_cat:
                    changed += 1

                if not dry_run:
                    patient.primary_category = new_cat
                    patient.category_tags = json.dumps(cat_result.category_tags, ensure_ascii=False)
                    patient.category_computed_at = cat_result.computed_at
                    patient.category_rules_version = cat_result.rules_version

            except Exception as exc:  # noqa: BLE001
                print(f"  [ERROR] patient_id={patient.id}: {exc}", file=sys.stderr)
                errors += 1

        if not dry_run:
            await session.commit()

    mode = "(dry-run)" if dry_run else ""
    print(
        f"\nDone {mode}: total={len(patients)}, changed={changed}, errors={errors}"
    )
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute patient categories.")
    parser.add_argument("--doctor-id", default=None, help="Restrict to one doctor.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing.")
    args = parser.parse_args()

    changed = asyncio.run(_run(args.doctor_id, args.dry_run))
    sys.exit(min(changed, 255))


if __name__ == "__main__":
    main()
