#!/usr/bin/env python3
"""Backfill rich demo data onto every existing doctor.

Runs `seed_demo_data_rich` once per doctor. Idempotent — doctors who already
have the rich seed (tagged `seed_source=onboarding_demo`) are skipped.
Doctors keep their own real patients/records/KBs; demo data coexists.

Usage (local dev):
    ENVIRONMENT=development PYTHONPATH=src \\
        .venv/bin/python scripts/backfill_demo_seed.py

Usage (production — Tencent, inside the backend container):
    PYTHONPATH=src python scripts/backfill_demo_seed.py --prod

Flags:
    --dry-run    List what would be seeded; no writes.
    --only ID    Only process the given doctor_id (for spot-testing).
    --prod       Require ENVIRONMENT=production (safety check).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("ENVIRONMENT", "development")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", metavar="DOCTOR_ID", help="Process a single doctor")
    parser.add_argument("--prod", action="store_true", help="Require ENVIRONMENT=production")
    args = parser.parse_args()

    if args.prod and os.environ.get("ENVIRONMENT") != "production":
        print("ERROR: --prod requires ENVIRONMENT=production", file=sys.stderr)
        return 2

    # Imports deferred so ENVIRONMENT is set first
    from db.engine import AsyncSessionLocal
    from db.models.doctor import Doctor
    from sqlalchemy import select

    from channels.web.doctor_dashboard.preseed_service import (
        is_demo_seeded,
        seed_demo_data_rich,
    )

    seeded = 0
    already = 0
    failed = 0
    target_count = 0

    async with AsyncSessionLocal() as db:
        query = select(Doctor.doctor_id, Doctor.name)
        if args.only:
            query = query.where(Doctor.doctor_id == args.only)
        rows = (await db.execute(query)).all()
        target_count = len(rows)

    print(f"backfill_demo_seed: {target_count} doctor(s) to check"
          f"{' [DRY RUN]' if args.dry_run else ''}")

    for row in rows:
        doctor_id = row[0]
        name = row[1] or "(unnamed)"
        async with AsyncSessionLocal() as db:
            try:
                if await is_demo_seeded(db, doctor_id):
                    already += 1
                    print(f"  skip  {doctor_id[:20]:20} {name:20} (already has demo)")
                    continue

                if args.dry_run:
                    seeded += 1
                    print(f"  WOULD {doctor_id[:20]:20} {name:20}")
                    continue

                result = await seed_demo_data_rich(db, doctor_id)
                await db.commit()
                seeded += 1
                print(f"  seed  {doctor_id[:20]:20} {name:20} "
                      f"+ {len(result.knowledge_items)} KB, "
                      f"{len(result.patients)} patients")
            except Exception as exc:
                failed += 1
                await db.rollback()
                print(f"  FAIL  {doctor_id[:20]:20} {name:20} {exc}", file=sys.stderr)

    print()
    print(f"Result: {seeded} seeded, {already} already had demo, {failed} failed "
          f"(of {target_count} total).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
