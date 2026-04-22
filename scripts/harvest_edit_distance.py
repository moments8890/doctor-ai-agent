#!/usr/bin/env python3
"""Surface every doctor edit on AI output — drafts and suggestions.

Second half of the quality-loop harvester set (companion to
harvest_prompt_quality.py which groups by prompt_hash). This one
focuses on the *edit* signal: whenever a doctor kept the AI's
shape but rewrote the content, we want to see it.

Output is sorted by edit ratio — structural rewrites float to the
top, so the doctor (or a later automation) can promote the most
instructive rewrites into tests/prompts/cases/*.yaml as regression
cases.

Usage:
    ENVIRONMENT=development PYTHONPATH=src \\
      scripts/harvest_edit_distance.py

    # Structural edits only (ratio >= 0.3):
    scripts/harvest_edit_distance.py --min-ratio 0.3

    # Filter to one doctor:
    scripts/harvest_edit_distance.py --doctor doc_001

    # Only message_drafts (skip ai_suggestions):
    scripts/harvest_edit_distance.py --source drafts
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

os.environ.setdefault("ENVIRONMENT", "development")

from sqlalchemy import select  # noqa: E402


def edit_ratio(a: str, b: str) -> float:
    """Char-level similarity — 1.0 means identical, 0.0 means totally different.

    Uses difflib's ratio (Ratcliff/Obershelp). Edit distance is ``1 - ratio``,
    which is what we print. Good enough for sorting "which edits changed the
    most" without pulling in a Levenshtein dep.
    """
    if not a and not b:
        return 0.0
    return 1.0 - difflib.SequenceMatcher(None, a, b).ratio()


def char_diff_preview(a: str, b: str, width: int = 80) -> str:
    """One-line preview showing where text diverged."""
    sm = difflib.SequenceMatcher(None, a, b)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            if i2 - i1 > 12:
                out.append(f"…{a[i1:i1+5]}…")
            else:
                out.append(a[i1:i2])
        elif op == "delete":
            out.append(f"[-{a[i1:i2]}-]")
        elif op == "insert":
            out.append(f"[+{b[j1:j2]}+]")
        elif op == "replace":
            out.append(f"[-{a[i1:i2]}-/+{b[j1:j2]}+]")
    s = "".join(out)
    return s if len(s) <= width else s[:width - 1] + "…"


async def harvest_drafts(doctor_filter: str | None, min_ratio: float) -> list[dict]:
    from db.engine import AsyncSessionLocal
    from db.models.message_draft import MessageDraft

    stmt = select(MessageDraft).where(MessageDraft.edited_text.isnot(None))
    if doctor_filter:
        stmt = stmt.where(MessageDraft.doctor_id == doctor_filter)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(stmt)).scalars().all()

    out = []
    for r in rows:
        a = r.draft_text or ""
        b = r.edited_text or ""
        if a == b:
            continue
        ratio = edit_ratio(a, b)
        if ratio < min_ratio:
            continue
        out.append({
            "source": "draft",
            "id": r.id,
            "doctor_id": r.doctor_id,
            "prompt_hash": getattr(r, "prompt_hash", None),
            "len_before": len(a),
            "len_after": len(b),
            "ratio": ratio,
            "preview": char_diff_preview(a, b),
        })
    return out


async def harvest_suggestions(doctor_filter: str | None, min_ratio: float) -> list[dict]:
    from db.engine import AsyncSessionLocal
    from db.models.ai_suggestion import AISuggestion

    stmt = select(AISuggestion).where(AISuggestion.edited_text.isnot(None))
    if doctor_filter:
        stmt = stmt.where(AISuggestion.doctor_id == doctor_filter)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(stmt)).scalars().all()

    out = []
    for r in rows:
        a = r.content or ""
        b = r.edited_text or ""
        if a == b:
            continue
        ratio = edit_ratio(a, b)
        if ratio < min_ratio:
            continue
        out.append({
            "source": f"sugg/{r.section}",
            "id": r.id,
            "doctor_id": r.doctor_id,
            "prompt_hash": getattr(r, "prompt_hash", None),
            "len_before": len(a),
            "len_after": len(b),
            "ratio": ratio,
            "preview": char_diff_preview(a, b),
        })
    return out


async def main(args) -> int:
    results = []
    if args.source in ("both", "drafts"):
        results.extend(await harvest_drafts(args.doctor, args.min_ratio))
    if args.source in ("both", "suggestions"):
        results.extend(await harvest_suggestions(args.doctor, args.min_ratio))

    if not results:
        print("No doctor edits found matching the filter.")
        print("(When doctors begin editing AI drafts/suggestions, they'll surface here sorted by edit ratio.)")
        return 0

    results.sort(key=lambda r: r["ratio"], reverse=True)

    cols = ("source", "id", "doctor", "hash", "len_b→a", "ratio", "preview")
    widths = [12, 6, 16, 10, 10, 6, 70]
    print("".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-" * sum(widths))
    for r in results:
        row = [
            r["source"],
            str(r["id"]),
            (r["doctor_id"] or "")[:14],
            (r["prompt_hash"] or "(none)")[:9],
            f"{r['len_before']}→{r['len_after']}",
            f"{r['ratio']:.2f}",
            r["preview"],
        ]
        print("".join(str(v).ljust(w) for v, w in zip(row, widths)))

    print()
    print(f"Total: {len(results)} edits. ratio 1.00 = completely rewritten, 0.00 = identical.")
    print("[-xxx-] = removed, [+xxx+] = added, [-x-/+y+] = replaced. … = long stretch of unchanged text.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--doctor", help="filter to one doctor_id")
    p.add_argument("--source", choices=["both", "drafts", "suggestions"], default="both")
    p.add_argument("--min-ratio", type=float, default=0.0, help="skip edits with ratio below this (0.0 = show all)")
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(args)))
