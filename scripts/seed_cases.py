#!/usr/bin/env python
# scripts/seed_cases.py
"""Load seed neurosurgery cases from markdown into case_history table."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db.engine import AsyncSessionLocal
from db.models.case_history import CaseHistory
from domain.knowledge.embedding import embed, preload_embedding_model
from sqlalchemy import select

SEED_DOCTOR_ID = "__seed__"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "seed_neurosurgery_cases.md"

FIELD_MAP = {
    "主诉": "chief_complaint",
    "现病史": "present_illness",
    "诊断": "final_diagnosis",
    "关键症状": "key_symptoms",
    "治疗": "treatment",
    "转归": "outcome",
}


def parse_cases(text: str) -> List[Dict[str, str]]:
    """Parse markdown into list of case dicts."""
    cases = []
    # Split by ## headers (case boundaries)
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    for section in sections[1:]:  # skip content before first ##
        lines = section.strip().split("\n")
        if not lines:
            continue
        case: Dict[str, str] = {"_title": lines[0].strip()}
        for line in lines[1:]:
            line = line.strip()
            if not line or line == "---":
                continue
            # Match **field：** value or **field:** value
            m = re.match(r"\*\*(.+?)[：:]\*\*\s*(.*)", line)
            if m:
                zh_field = m.group(1).strip()
                value = m.group(2).strip()
                en_field = FIELD_MAP.get(zh_field)
                if en_field:
                    case[en_field] = value
        if "chief_complaint" in case:
            cases.append(case)
    return cases


async def seed():
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found")
        sys.exit(1)

    text = DATA_FILE.read_text(encoding="utf-8")
    cases = parse_cases(text)
    print(f"Parsed {len(cases)} cases from {DATA_FILE.name}")

    # Preload embedding model
    preload_embedding_model()

    async with AsyncSessionLocal() as session:
        inserted = 0
        for case in cases:
            cc = case.get("chief_complaint", "")
            # Check idempotency
            existing = (await session.execute(
                select(CaseHistory).where(
                    CaseHistory.doctor_id == SEED_DOCTOR_ID,
                    CaseHistory.chief_complaint == cc,
                )
            )).scalar_one_or_none()
            if existing:
                print(f"  SKIP (exists): {cc[:30]}")
                continue

            # Build embedding
            pi = case.get("present_illness", "")
            diag = case.get("final_diagnosis", "")
            treat = case.get("treatment", "")
            embed_text = cc
            if pi:
                embed_text += " " + pi
            if diag:
                embed_text += f" 诊断：{diag}"
            if treat:
                embed_text += f" 治疗：{treat}"

            try:
                vec = embed(embed_text)
                embedding_json = json.dumps(vec)
            except Exception as e:
                print(f"  WARN: embedding failed for {cc[:30]}: {e}")
                embedding_json = None

            # Parse key_symptoms
            ks_raw = case.get("key_symptoms", "")
            ks_list = [s.strip() for s in re.split(r"[,，]", ks_raw) if s.strip()] if ks_raw else []

            entry = CaseHistory(
                doctor_id=SEED_DOCTOR_ID,
                chief_complaint=cc,
                present_illness=pi or None,
                final_diagnosis=diag or None,
                key_symptoms=json.dumps(ks_list, ensure_ascii=False) if ks_list else None,
                treatment=treat or None,
                outcome=case.get("outcome") or None,
                confidence_status="confirmed",
                embedding=embedding_json,
                embedding_model="BAAI/bge-m3",
            )
            session.add(entry)
            inserted += 1
            print(f"  ADD: {cc[:40]}")

        await session.commit()
        print(f"\nDone: {inserted} cases inserted, {len(cases) - inserted} skipped")


if __name__ == "__main__":
    # Load runtime config first
    os.environ.setdefault("EMBEDDING_PROVIDER", "local")
    from utils.runtime_config import load_runtime_json
    load_runtime_json()
    asyncio.run(seed())
