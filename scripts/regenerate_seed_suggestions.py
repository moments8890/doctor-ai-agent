#!/usr/bin/env python3
"""Regenerate AI suggestions for seeded medical records via real LLM.

The rich-demo seed previously inserted hand-written AISuggestion rows that
left evidence_json / risk_signals_json / cited_knowledge_ids empty, so the
review UI showed bare 诊断 titles without 依据 / 风险监测 chips.

This script:
  1. Finds all medical_records tagged seed_source='onboarding_demo'
  2. Deletes their existing seed AISuggestion rows
  3. Calls run_diagnosis() for each — which produces real LLM-generated
     differentials/workup/treatment with evidence + risk fields populated
  4. Tags the freshly-created suggestions with seed_source='onboarding_demo'
     so future --cleanup runs can remove them cleanly

Usage:
    # Production
    cd /home/ubuntu/doctor-ai-agent && \\
      ENVIRONMENT=production PYTHONPATH=src \\
      .venv/bin/python scripts/regenerate_seed_suggestions.py --prod

    # Local dev
    ENVIRONMENT=development PYTHONPATH=src \\
      .venv/bin/python scripts/regenerate_seed_suggestions.py

Flags:
    --prod        Require ENVIRONMENT=production (safety)
    --only-doctor ID   Process records for one doctor only
    --limit N     Cap regenerations at N records (smoke-test)
    --dry-run     Print what would happen, no LLM calls
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("ENVIRONMENT", "development")

# main.py merges config/runtime.json into os.environ at import time (so LLM
# provider keys + STRUCTURING_LLM are visible). Replicate that here so this
# standalone script picks up the same config.
from utils.app_config import load_config_from_json  # noqa: E402

_, _config_values = load_config_from_json()
for _key, _value in _config_values.items():
    os.environ.setdefault(_key, _value)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prod", action="store_true")
    parser.add_argument("--only-doctor", metavar="DOCTOR_ID")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.prod and os.environ.get("ENVIRONMENT") != "production":
        print("ERROR: --prod requires ENVIRONMENT=production", file=sys.stderr)
        return 2

    from sqlalchemy import select, delete, update

    from db.engine import AsyncSessionLocal
    from db.models.records import MedicalRecordDB
    from db.models.ai_suggestion import AISuggestion
    from domain.diagnosis import run_diagnosis

    # ── 1. Find seeded records ──────────────────────────────────────
    async with AsyncSessionLocal() as db:
        stmt = (
            select(MedicalRecordDB.id, MedicalRecordDB.doctor_id)
            .where(MedicalRecordDB.seed_source.in_(("onboarding_demo", "onboarding_preseed")))
            .order_by(MedicalRecordDB.doctor_id, MedicalRecordDB.id)
        )
        if args.only_doctor:
            stmt = stmt.where(MedicalRecordDB.doctor_id == args.only_doctor)
        rows = (await db.execute(stmt)).all()

    if args.limit:
        rows = rows[: args.limit]

    print(f"Found {len(rows)} seeded record(s) to regenerate")
    if not rows:
        return 0

    if args.dry_run:
        for record_id, doctor_id in rows:
            print(f"  DRY  doctor={doctor_id} record={record_id}")
        return 0

    # ── 2. Wipe existing seed suggestions ───────────────────────────
    async with AsyncSessionLocal() as db:
        deleted = (await db.execute(
            delete(AISuggestion).where(AISuggestion.seed_source.in_(("onboarding_demo", "onboarding_preseed")))
        )).rowcount
        await db.commit()
    print(f"Cleared {deleted} stale seed suggestion(s)")

    # ── 3. Regenerate via run_diagnosis ─────────────────────────────
    success = failed = 0
    t0 = time.monotonic()
    for record_id, doctor_id in rows:
        try:
            result = await run_diagnosis(doctor_id=doctor_id, record_id=record_id)
            if isinstance(result, dict) and result.get("status") == "failed":
                failed += 1
                print(f"  FAIL  doctor={doctor_id} record={record_id}: {result.get('error')}")
                continue
            # Tag the freshly-created suggestions so cleanup can find them.
            # Inherit the parent record's seed_source so preseed-vs-demo split
            # is preserved.
            async with AsyncSessionLocal() as db:
                rec_source = (await db.execute(
                    select(MedicalRecordDB.seed_source).where(MedicalRecordDB.id == record_id)
                )).scalar_one_or_none() or "onboarding_demo"
                tagged = (await db.execute(
                    update(AISuggestion)
                    .where(AISuggestion.record_id == record_id)
                    .where(AISuggestion.seed_source.is_(None))
                    .values(seed_source=rec_source)
                )).rowcount
                await db.commit()
            success += 1
            print(f"  ok    doctor={doctor_id} record={record_id} (+{tagged} suggestions)")
        except Exception as exc:
            failed += 1
            print(f"  EXC   doctor={doctor_id} record={record_id}: {exc}")

    elapsed = time.monotonic() - t0
    print(f"\nDone in {elapsed:.1f}s — {success} succeeded, {failed} failed (of {len(rows)}).")
    return 1 if failed and success == 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
