#!/usr/bin/env python3
"""Group ai_suggestions by prompt_hash and compute acceptance / edit / reject rates.

First-pass quality-loop harvester: lets us answer "did my prompt change help?"
by comparing acceptance rates across prompt_hash values.

Usage:
    ENVIRONMENT=development PYTHONPATH=src \
      scripts/harvest_prompt_quality.py

    # Filter to one doctor:
    scripts/harvest_prompt_quality.py --doctor doc_001

    # Only suggestions in a given section:
    scripts/harvest_prompt_quality.py --section differential

Output: one row per (prompt_hash, section) group with counts + ratios.
Rows with null prompt_hash are historical (pre-migration) and grouped as
'(none)'. Rows where a section has only a handful of suggestions aren't
statistically meaningful — flagged with a `*` when n < 10.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("ENVIRONMENT", "development")

from sqlalchemy import func, select  # noqa: E402


async def main(doctor_filter: str | None, section_filter: str | None) -> int:
    from db.engine import AsyncSessionLocal
    from db.models.ai_suggestion import AISuggestion

    async with AsyncSessionLocal() as db:
        stmt = select(
            AISuggestion.prompt_hash,
            AISuggestion.section,
            AISuggestion.decision,
            func.count().label("n"),
        )
        if doctor_filter:
            stmt = stmt.where(AISuggestion.doctor_id == doctor_filter)
        if section_filter:
            stmt = stmt.where(AISuggestion.section == section_filter)
        stmt = stmt.group_by(
            AISuggestion.prompt_hash,
            AISuggestion.section,
            AISuggestion.decision,
        )
        rows = (await db.execute(stmt)).all()

    # Pivot into (prompt_hash, section) → decision counts.
    agg: dict[tuple[str, str], dict[str, int]] = {}
    for prompt_hash, section, decision, n in rows:
        key = (prompt_hash or "(none)", section)
        bucket = agg.setdefault(key, {"confirmed": 0, "rejected": 0, "edited": 0, "custom": 0, "undecided": 0, "total": 0})
        if decision in bucket:
            bucket[decision] += n
        else:  # NULL decision — doctor hasn't decided yet
            bucket["undecided"] += n
        bucket["total"] += n

    if not agg:
        print("no ai_suggestions rows found for the given filters")
        return 0

    # Sort by prompt_hash (newest prompt usually has newer hash — but we don't
    # have a version timestamp, so alphabetical is fine as a stable order),
    # then section. Historical '(none)' sinks to the bottom.
    def sort_key(k: tuple[str, str]) -> tuple[int, str, str]:
        ph, sec = k
        return (1 if ph == "(none)" else 0, ph, sec)

    cols = ("prompt_hash", "section", "n", "conf", "rej", "edit", "custom", "pend", "accept%", "edit%", "rej%")
    widths = [12, 14, 6, 6, 6, 6, 7, 6, 8, 7, 7]
    print("".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-" * sum(widths))

    for key in sorted(agg.keys(), key=sort_key):
        ph, sec = key
        b = agg[key]
        total = b["total"]
        # "Accept" = confirmed (doctor took AI's suggestion as-is).
        # "Edit" = editied (doctor kept the shape but rewrote).
        # "Rej" = rejected.
        # Pending + custom excluded from denominators — not decisions on the
        # AI row itself. Custom rows are doctor-written, not AI-written.
        decided = b["confirmed"] + b["rejected"] + b["edited"]
        accept_pct = f"{100 * b['confirmed'] / decided:.0f}%" if decided else "-"
        edit_pct = f"{100 * b['edited'] / decided:.0f}%" if decided else "-"
        rej_pct = f"{100 * b['rejected'] / decided:.0f}%" if decided else "-"
        n_marker = f"{total}{'*' if total < 10 else ''}"
        vals = [ph, sec, n_marker, str(b["confirmed"]), str(b["rejected"]), str(b["edited"]), str(b["custom"]), str(b["undecided"]), accept_pct, edit_pct, rej_pct]
        print("".join(v.ljust(w) for v, w in zip(vals, widths)))

    print("\n* = n<10, not statistically meaningful")
    print("Percentages use (confirmed + rejected + edited) as denominator; custom + undecided excluded.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--doctor", help="filter to one doctor_id")
    p.add_argument("--section", choices=["differential", "workup", "treatment"], help="filter to one section")
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(args.doctor, args.section)))
