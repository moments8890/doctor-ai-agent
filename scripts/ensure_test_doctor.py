#!/usr/bin/env python3
"""Ensure a fixed test doctor (nickname=test, passcode=123456) exists.

Used by the E2E suite so every test logs in as the same doctor instead of
registering a fresh one each time. Removes the state-pollution / rate-limit
failures that surface when many specs register doctors in sequence.

Usage:
    PYTHONPATH=src ENVIRONMENT=development \\
      PATIENTS_DB_PATH=/tmp/e2e_test.db \\
      python scripts/ensure_test_doctor.py

Idempotent. Run before the suite (validate-v2-e2e.sh wires this in as a
preflight step).
"""

import asyncio
import os
import secrets
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

NICKNAME = "test"
PASSCODE = "123456"


async def main():
    from utils.app_config import load_config_from_json
    _, vals = load_config_from_json()
    for k, v in vals.items():
        if k not in os.environ:
            os.environ[k] = v

    from sqlalchemy import select
    from db.engine import AsyncSessionLocal
    from db.models.doctor import Doctor
    from utils.hashing import hash_passcode, verify_passcode

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                select(Doctor).where(Doctor.nickname == NICKNAME).limit(1)
            )
        ).scalar_one_or_none()

        if existing is None:
            doctor_id = f"inv_{secrets.token_urlsafe(9)}"
            db.add(Doctor(
                doctor_id=doctor_id,
                name=NICKNAME,
                nickname=NICKNAME,
                passcode_hash=hash_passcode(PASSCODE),
            ))
            await db.commit()
            print(f"Created test doctor: nickname={NICKNAME} passcode={PASSCODE} doctor_id={doctor_id}")
        else:
            # Verify existing passcode still matches; rehash only if drifted.
            if not verify_passcode(PASSCODE, existing.passcode_hash):
                existing.passcode_hash = hash_passcode(PASSCODE)
                existing.passcode_version = (existing.passcode_version or 1) + 1
                await db.commit()
                print(f"Updated test doctor passcode (doctor_id={existing.doctor_id})")
            else:
                print(f"Test doctor already valid (doctor_id={existing.doctor_id})")


if __name__ == "__main__":
    asyncio.run(main())
