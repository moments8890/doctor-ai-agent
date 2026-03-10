#!/usr/bin/env python
"""
患者风险重计算脚本 — 对指定医生（或所有医生）的患者批量重新计算风险字段。

用法：
    python scripts/recompute_patient_risk.py [--doctor-id ID] [--dry-run]

CLI to recompute patient risk fields for all or one doctor's patients.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB, Patient
from services.patient.patient_risk import compute_patient_risk


async def _process_patient_risk(session, patient, dry_run: bool) -> bool:
    """Recompute risk for a single patient; return True if risk level changed."""
    records_result = await session.execute(
        select(MedicalRecordDB)
        .where(MedicalRecordDB.patient_id == patient.id,
               MedicalRecordDB.doctor_id == patient.doctor_id)
        .order_by(MedicalRecordDB.created_at.desc())
    )
    records = list(records_result.scalars().all())
    risk = compute_patient_risk(patient, records)
    old = patient.primary_risk_level
    label = "CHANGED" if old != risk.primary_risk_level else "same"
    print(f"  [{label}] patient_id={patient.id} name={patient.name!r} "
          f"{old!r} -> {risk.primary_risk_level!r} "
          f"follow_up_state={risk.follow_up_state} "
          f"tags={json.dumps(risk.risk_tags, ensure_ascii=False)}")
    if not dry_run:
        patient.primary_risk_level = risk.primary_risk_level
        patient.risk_tags = json.dumps(risk.risk_tags, ensure_ascii=False)
        patient.risk_score = risk.risk_score
        patient.follow_up_state = risk.follow_up_state
        patient.risk_computed_at = risk.computed_at
        patient.risk_rules_version = risk.rules_version
    return old != risk.primary_risk_level


async def _run(doctor_id: Optional[str], dry_run: bool) -> int:
    """Recompute risk for all matching patients; return changed count."""
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
                if await _process_patient_risk(session, patient, dry_run):
                    changed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [ERROR] patient_id={patient.id}: {exc}", file=sys.stderr)
                errors += 1
        if not dry_run:
            await session.commit()
    mode = "(dry-run)" if dry_run else ""
    print(f"\nDone {mode}: total={len(patients)}, changed={changed}, errors={errors}")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompute patient risk fields.")
    parser.add_argument("--doctor-id", default=None, help="Restrict to one doctor.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing.")
    args = parser.parse_args()

    changed = asyncio.run(_run(args.doctor_id, args.dry_run))
    sys.exit(min(changed, 255))


if __name__ == "__main__":
    main()
