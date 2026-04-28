#!/usr/bin/env python3
"""Ensure a fixed test patient (nickname=test, passcode=123456) exists
under the seeded test doctor (also nickname=test).

Patient nickname uniqueness is scoped per-doctor, so the patient and
doctor can share the nickname `test` without collision — the unified
login disambiguates by `role` (and `doctor_id` for patient).

Usage:
    PYTHONPATH=src ENVIRONMENT=development \\
      PATIENTS_DB_PATH=/tmp/e2e_test.db \\
      python scripts/ensure_test_patient.py

Idempotent. Wired into `scripts/validate-v2-e2e.sh` preflight, runs after
`ensure_test_doctor.py`.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

NICKNAME = "test"
PASSCODE = "123456"
GENDER = "男"
DOCTOR_NICKNAME = "test"  # the seed doctor created by ensure_test_doctor.py


async def main():
    from utils.app_config import load_config_from_json
    _, vals = load_config_from_json()
    for k, v in vals.items():
        if k not in os.environ:
            os.environ[k] = v

    from sqlalchemy import select
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from utils.hashing import hash_passcode, verify_passcode

    async with AsyncSessionLocal() as db:
        doctor = (
            await db.execute(
                select(Doctor).where(Doctor.nickname == DOCTOR_NICKNAME).limit(1)
            )
        ).scalar_one_or_none()
        if doctor is None:
            print(
                f"ERROR: test doctor (nickname={DOCTOR_NICKNAME}) not found. "
                f"Run scripts/ensure_test_doctor.py first."
            )
            sys.exit(1)

        existing = (
            await db.execute(
                select(Patient).where(
                    Patient.doctor_id == doctor.doctor_id,
                    Patient.nickname == NICKNAME,
                ).limit(1)
            )
        ).scalar_one_or_none()

        if existing is None:
            patient = Patient(
                doctor_id=doctor.doctor_id,
                name=NICKNAME,
                nickname=NICKNAME,
                passcode_hash=hash_passcode(PASSCODE),
                gender=GENDER,
            )
            db.add(patient)
            await db.commit()
            await db.refresh(patient)
            print(
                f"Created test patient: nickname={NICKNAME} passcode={PASSCODE} "
                f"patient_id={patient.id} doctor_id={doctor.doctor_id}"
            )
        else:
            changed = []
            if not verify_passcode(PASSCODE, existing.passcode_hash):
                existing.passcode_hash = hash_passcode(PASSCODE)
                existing.passcode_version = (existing.passcode_version or 1) + 1
                changed.append("passcode rehashed")
            if existing.gender != GENDER:
                existing.gender = GENDER
                changed.append(f"gender={GENDER}")
            if changed:
                await db.commit()
                print(
                    f"Updated test patient (patient_id={existing.id}): "
                    f"{', '.join(changed)}"
                )
            else:
                print(
                    f"Test patient already valid (patient_id={existing.id} "
                    f"doctor_id={doctor.doctor_id})"
                )


if __name__ == "__main__":
    asyncio.run(main())
