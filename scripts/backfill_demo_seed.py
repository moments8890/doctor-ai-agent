#!/usr/bin/env python3
"""Inspect / seed / cleanup demo data across all doctors.

Three modes:
    --inspect         Audit only. Print per-doctor stats and flag anomalies.
                      No writes.
    (default)         Apply rich demo seed to every doctor that doesn't already
                      have it. Idempotent; real data is preserved.
    --cleanup         Remove all seed data (both thin preseed + rich demo).
                      Does NOT touch real doctor-created rows.

Usage examples:

    # Local dev — audit state
    ENVIRONMENT=development PYTHONPATH=src \\
        .venv/bin/python scripts/backfill_demo_seed.py --inspect

    # Local dev — apply seed
    ENVIRONMENT=development PYTHONPATH=src \\
        .venv/bin/python scripts/backfill_demo_seed.py

    # Production (Tencent, inside backend container)
    PYTHONPATH=src python scripts/backfill_demo_seed.py --prod --inspect
    PYTHONPATH=src python scripts/backfill_demo_seed.py --prod

Flags:
    --dry-run    List what would change; no writes.
    --only ID    Process a single doctor_id (for spot-testing).
    --prod       Require ENVIRONMENT=production (safety check).
    --inspect    Audit mode; no writes, prints per-doctor summary.
    --cleanup    Remove all seed data instead of adding it.
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


async def _audit_doctor(db, doctor_id: str):
    """Return dict of counts + anomaly flags for a single doctor."""
    from sqlalchemy import select, func
    from db.models.patient import Patient
    from db.models.records import MedicalRecordDB
    from db.models.doctor import DoctorKnowledgeItem
    from db.models.message_draft import MessageDraft
    from db.models.patient_message import PatientMessage
    from db.models.ai_suggestion import AISuggestion
    from db.models.tasks import DoctorTask

    async def count(model, extra_where=None):
        stmt = select(func.count()).select_from(model).where(model.doctor_id == doctor_id)
        if extra_where is not None:
            stmt = stmt.where(extra_where)
        return (await db.execute(stmt)).scalar_one()

    # Totals
    patients_total = await count(Patient)
    records_total = await count(MedicalRecordDB)
    kb_total = await count(DoctorKnowledgeItem)
    drafts_total = await count(MessageDraft)
    messages_total = await count(PatientMessage)
    suggs_total = await count(AISuggestion)
    tasks_total = await count(DoctorTask)

    # Seeded vs real counts (split by seed_source)
    patients_thin = await count(Patient, Patient.seed_source == "onboarding_preseed")
    patients_demo = await count(Patient, Patient.seed_source == "onboarding_demo")
    patients_real = await count(Patient, Patient.seed_source.is_(None))
    kb_thin = await count(DoctorKnowledgeItem, DoctorKnowledgeItem.seed_source == "onboarding_preseed")
    kb_demo = await count(DoctorKnowledgeItem, DoctorKnowledgeItem.seed_source == "onboarding_demo")
    kb_real = await count(DoctorKnowledgeItem, DoctorKnowledgeItem.seed_source.is_(None))

    # Anomaly checks
    flags = []

    # Orphan records (patient_id doesn't match any patient)
    orphan_records = (await db.execute(
        select(func.count()).select_from(MedicalRecordDB).where(
            MedicalRecordDB.doctor_id == doctor_id,
            ~MedicalRecordDB.patient_id.in_(select(Patient.id).where(Patient.doctor_id == doctor_id)),
        )
    )).scalar_one()
    if orphan_records:
        flags.append(f"orphan_records={orphan_records}")

    # 体验患者 leaked (shouldn't be in prod doctors' lists after onboarding)
    tiyan_count = (await db.execute(
        select(func.count()).select_from(Patient).where(
            Patient.doctor_id == doctor_id,
            Patient.name.like("体验患者%"),
        )
    )).scalar_one()
    if tiyan_count:
        flags.append(f"tiyan_patients={tiyan_count}")

    # Records with no chief_complaint AND no content (empty record)
    empty_records = (await db.execute(
        select(func.count()).select_from(MedicalRecordDB).where(
            MedicalRecordDB.doctor_id == doctor_id,
            (MedicalRecordDB.chief_complaint.is_(None) | (MedicalRecordDB.chief_complaint == "")),
            (MedicalRecordDB.content.is_(None) | (MedicalRecordDB.content == "")),
        )
    )).scalar_one()
    if empty_records:
        flags.append(f"empty_records={empty_records}")

    # Drafts with empty text
    empty_drafts = (await db.execute(
        select(func.count()).select_from(MessageDraft).where(
            MessageDraft.doctor_id == doctor_id,
            (MessageDraft.draft_text.is_(None) | (MessageDraft.draft_text == "")),
        )
    )).scalar_one()
    if empty_drafts:
        flags.append(f"empty_drafts={empty_drafts}")

    return {
        "patients_total": patients_total,
        "patients_thin": patients_thin,
        "patients_demo": patients_demo,
        "patients_real": patients_real,
        "records_total": records_total,
        "kb_total": kb_total,
        "kb_thin": kb_thin,
        "kb_demo": kb_demo,
        "kb_real": kb_real,
        "drafts_total": drafts_total,
        "messages_total": messages_total,
        "suggs_total": suggs_total,
        "tasks_total": tasks_total,
        "flags": flags,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", metavar="DOCTOR_ID", help="Process a single doctor")
    parser.add_argument("--prod", action="store_true", help="Require ENVIRONMENT=production")
    parser.add_argument("--inspect", action="store_true", help="Audit only (no writes)")
    parser.add_argument("--cleanup", action="store_true", help="Delete all seed data")
    args = parser.parse_args()

    if args.prod and os.environ.get("ENVIRONMENT") != "production":
        print("ERROR: --prod requires ENVIRONMENT=production", file=sys.stderr)
        return 2

    if args.inspect and args.cleanup:
        print("ERROR: --inspect and --cleanup are mutually exclusive", file=sys.stderr)
        return 2

    from db.engine import AsyncSessionLocal
    from db.models.doctor import Doctor
    from sqlalchemy import select

    from channels.web.doctor_dashboard.preseed_service import (
        cleanup_seed_data,
        is_demo_seeded,
        seed_demo_data_rich,
    )

    async with AsyncSessionLocal() as db:
        query = select(Doctor.doctor_id, Doctor.name)
        if args.only:
            query = query.where(Doctor.doctor_id == args.only)
        rows = (await db.execute(query)).all()

    mode = "INSPECT" if args.inspect else ("CLEANUP" if args.cleanup else "SEED")
    suffix = " [DRY RUN]" if args.dry_run else ""
    print(f"backfill_demo_seed [{mode}]: {len(rows)} doctor(s){suffix}")
    print()

    # Tallies
    seeded = already = failed = cleaned = 0
    # Audit aggregates
    total = {
        "patients_total": 0, "patients_thin": 0, "patients_demo": 0, "patients_real": 0,
        "records_total": 0, "kb_total": 0, "kb_thin": 0, "kb_demo": 0, "kb_real": 0,
        "drafts_total": 0, "messages_total": 0, "suggs_total": 0, "tasks_total": 0,
    }
    flagged_doctors = []

    if args.inspect:
        print(f"  {'doctor_id':22} {'name':20} {'pat(real/thin/demo)':20} {'rec':>5} {'kb(r/t/d)':>12} {'draft':>5} {'flags'}")
        print(f"  {'-' * 110}")

    for row in rows:
        doctor_id, name = row[0], row[1] or "(unnamed)"
        async with AsyncSessionLocal() as db:
            try:
                if args.inspect:
                    info = await _audit_doctor(db, doctor_id)
                    for k in total:
                        total[k] += info[k]
                    if info["flags"]:
                        flagged_doctors.append((doctor_id, name, info["flags"]))
                    print(
                        f"  {doctor_id[:22]:22} {name[:20]:20} "
                        f"{info['patients_real']}/{info['patients_thin']}/{info['patients_demo']:<15} "
                        f"{info['records_total']:>5} "
                        f"{info['kb_real']}/{info['kb_thin']}/{info['kb_demo']:<8} "
                        f"{info['drafts_total']:>5} "
                        f"{','.join(info['flags']) if info['flags'] else ''}"
                    )

                elif args.cleanup:
                    if args.dry_run:
                        cleaned += 1
                        print(f"  WOULD CLEAN {doctor_id[:20]:20} {name:20}")
                        continue
                    await cleanup_seed_data(db, doctor_id)
                    await db.commit()
                    cleaned += 1
                    print(f"  clean  {doctor_id[:20]:20} {name:20}")

                else:  # seed mode
                    if await is_demo_seeded(db, doctor_id):
                        already += 1
                        print(f"  skip   {doctor_id[:20]:20} {name:20} (already has demo)")
                        continue
                    if args.dry_run:
                        seeded += 1
                        print(f"  WOULD  {doctor_id[:20]:20} {name:20}")
                        continue
                    result = await seed_demo_data_rich(db, doctor_id)
                    await db.commit()
                    seeded += 1
                    print(f"  seed   {doctor_id[:20]:20} {name:20} + "
                          f"{len(result.knowledge_items)} KB, {len(result.patients)} patients")
            except Exception as exc:
                failed += 1
                await db.rollback()
                print(f"  FAIL   {doctor_id[:20]:20} {name:20} {exc}", file=sys.stderr)

    print()
    if args.inspect:
        print(f"Totals across {len(rows)} doctors:")
        print(f"  patients: {total['patients_total']} "
              f"(real={total['patients_real']}, thin={total['patients_thin']}, demo={total['patients_demo']})")
        print(f"  records:  {total['records_total']}")
        print(f"  KBs:      {total['kb_total']} "
              f"(real={total['kb_real']}, thin={total['kb_thin']}, demo={total['kb_demo']})")
        print(f"  drafts:   {total['drafts_total']}")
        print(f"  messages: {total['messages_total']}")
        print(f"  suggestions: {total['suggs_total']}")
        print(f"  tasks:    {total['tasks_total']}")
        if flagged_doctors:
            print(f"\nDoctors with anomalies ({len(flagged_doctors)}):")
            for did, nm, fl in flagged_doctors:
                print(f"  {did:22} {nm:20} {', '.join(fl)}")
        else:
            print("\nNo anomalies flagged.")
    elif args.cleanup:
        print(f"Result: {cleaned} cleaned, {failed} failed (of {len(rows)} total).")
    else:
        print(f"Result: {seeded} seeded, {already} already had demo, {failed} failed "
              f"(of {len(rows)} total).")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
