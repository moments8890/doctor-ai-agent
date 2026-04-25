#!/usr/bin/env python3
"""Backfill ai_suggestions evidence/risk_signals/trigger_rule_ids from legacy detail prose.

LOCKED PLAN: option B with verification — extracts candidate evidence from
legacy `detail` prose using Groq LLM, then VERIFIES each evidence item has
substring overlap with the parent record's structured fields. Items that
don't trace back to actual record facts are DROPPED.

This is the only safe form of detail-to-evidence migration. Without
verification, the LLM can invent atomic facts ("发热38.5℃") that aren't in
the record — exactly the fabrication problem the new schema was designed
to prevent.

Idempotent: skips rows where evidence_json is already populated.
Read-only on records — only writes to ai_suggestions.{evidence_json,
risk_signals_json, trigger_rule_ids_json}.

Usage:
    ENVIRONMENT=development PYTHONPATH=src .venv/bin/python \\
      scripts/backfill_evidence_from_detail.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))


PROMPT_TEMPLATE = """从医生写的诊断 detail 散文中，提取两类原子事实（仅返回JSON）：

1. evidence: 来自当前患者真实记录的临床事实（已观察到的）
2. risk_signals: 何时升级/复诊的具体监测信号（前瞻性预警，未发生）

患者记录（事实来源）:
{record_facts}

医生 detail 散文:
{detail_prose}

输出格式（仅JSON，无其他文字）:
{{"evidence": ["事实1", "事实2"], "risk_signals": ["监测信号1", "监测信号2"]}}

规则:
- 每个 evidence 必须出现在患者记录中（直接引用或同义词）
- evidence 拒绝纯教科书定义、纯诊断推断（"符合典型表现"等）
- risk_signals 必须是前瞻性监测条件，不可包含已观察到的事实
- 若某类无符合条件的项，返回空数组 []
"""


def _verify_evidence(item: str, record_text: str) -> bool:
    """Verify evidence item is grounded in record. Strict 3-char substring overlap."""
    if not item or not record_text or len(item.strip()) < 2:
        return False
    item_clean = item.strip()
    # Direct substring (most common case for grounded items)
    if item_clean in record_text:
        return True
    # Strip qualifiers like "持续X天" — check core fragment
    # Try 3+ char substrings of the item against the record
    for i in range(len(item_clean) - 2):
        for j in range(i + 3, len(item_clean) + 1):
            if item_clean[i:j] in record_text:
                # At least 3 chars of the item appear verbatim in the record
                return True
    return False


def _verify_risk_signal(signal: str, record_text: str) -> bool:
    """Verify risk_signal is forward-looking (NOT already in record).

    Risk signals describe what to watch for — they should NOT yet be present.
    If a candidate risk_signal substring-matches the record, it's actually
    evidence (already-observed), not a future signal — drop it.
    """
    if not signal or len(signal.strip()) < 3:
        return False
    sig = signal.strip()
    # If the signal already appears as a fact in the record, it's misclassified
    if sig in record_text:
        return False
    return True


def _build_record_text(record: Dict) -> str:
    """Concatenate all structured fields into a verification-source string."""
    parts = []
    for key in ("chief_complaint", "present_illness", "past_history",
                "physical_exam", "auxiliary_exam"):
        v = (record.get(key) or "").strip()
        if v:
            parts.append(v)
    return " | ".join(parts)


def _extract_kb_ids_from_detail(detail: str, cited_knowledge_ids_json: Optional[str]) -> List[str]:
    """Build trigger_rule_ids from existing cited_knowledge_ids OR [KB-N] markers in prose."""
    ids: List[int] = []
    if cited_knowledge_ids_json:
        try:
            parsed = json.loads(cited_knowledge_ids_json)
            if isinstance(parsed, list):
                ids.extend(int(x) for x in parsed if isinstance(x, (int, str)))
        except (ValueError, TypeError):
            pass
    # Also scan detail prose for [KB-N] markers
    for m in re.finditer(r"\[KB-(\d+)\]", detail or ""):
        ids.append(int(m.group(1)))
    # Dedupe + format as "KB-N" strings
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(f"KB-{i}")
    return out


async def _llm_extract(record_facts: str, detail: str) -> Tuple[List[str], List[str]]:
    """Call Groq LLM with strict extraction prompt. Returns (evidence, risk_signals)."""
    from agent.llm import llm_call
    prompt = PROMPT_TEMPLATE.format(record_facts=record_facts, detail_prose=detail)
    messages = [
        {"role": "system", "content": "你是医疗信息提取助手。严格按JSON返回。"},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await llm_call(
            messages=messages,
            op_name="backfill_extract",
            env_var="ROUTING_LLM",
            temperature=0.1,
            max_tokens=1024,
            json_mode=True,
        )
    except Exception as exc:
        print(f"  ⚠ LLM call failed: {exc!s:.120}")
        return [], []
    # Parse JSON (may have <think> tags or markdown fences stripped already)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
        evidence = [str(x).strip() for x in obj.get("evidence", []) if x]
        risk_signals = [str(x).strip() for x in obj.get("risk_signals", []) if x]
        return evidence, risk_signals
    except (ValueError, TypeError) as exc:
        print(f"  ⚠ JSON parse failed: {exc} — raw[:120]={raw[:120]!r}")
        return [], []


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N rows (0=all)")
    parser.add_argument("--db", default="patients.db", help="SQLite DB path")
    args = parser.parse_args()

    # Load Groq key
    runtime_path = _REPO / "config" / "runtime.json"
    if runtime_path.is_file():
        rt = json.loads(runtime_path.read_text())
        key = rt.get("categories", {}).get("llm", {}).get("settings", {}).get("GROQ_API_KEY", {}).get("value")
        if key and not os.environ.get("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = key
            os.environ["OPENAI_API_KEY"] = key  # llm_call client uses OPENAI_API_KEY env
    os.environ.setdefault("ENVIRONMENT", "development")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    # Find rows needing backfill
    rows = list(con.execute("""
        SELECT s.id, s.record_id, s.section, s.detail, s.cited_knowledge_ids,
               r.chief_complaint, r.present_illness, r.past_history,
               r.physical_exam, r.auxiliary_exam
          FROM ai_suggestions s
          LEFT JOIN medical_records r ON r.id = s.record_id
         WHERE s.evidence_json IS NULL
           AND s.detail IS NOT NULL
           AND length(s.detail) > 0
         ORDER BY s.id
    """))

    if args.limit > 0:
        rows = rows[: args.limit]

    print(f"Found {len(rows)} suggestion rows needing backfill")
    if args.dry_run:
        print("Dry run — printing plan, no writes.")

    stats = {
        "total": len(rows),
        "extracted": 0,
        "skipped_no_record": 0,
        "evidence_emitted": 0,
        "evidence_dropped_unverified": 0,
        "risk_emitted": 0,
        "risk_dropped_already_in_record": 0,
        "rows_with_zero_evidence": 0,
        "rows_with_zero_risk": 0,
    }

    for i, row in enumerate(rows, 1):
        sug_id = row["id"]
        detail = row["detail"] or ""
        record_text = _build_record_text(dict(row))
        if not record_text:
            stats["skipped_no_record"] += 1
            print(f"  [{i}/{len(rows)}] sug_id={sug_id} — no record text, skipping")
            continue

        candidate_evidence, candidate_risks = await _llm_extract(record_text, detail)

        # VERIFY each evidence item against record (the safety gate)
        verified_evidence = [e for e in candidate_evidence if _verify_evidence(e, record_text)]
        dropped_evidence = [e for e in candidate_evidence if e not in verified_evidence]
        stats["evidence_emitted"] += len(verified_evidence)
        stats["evidence_dropped_unverified"] += len(dropped_evidence)
        if not verified_evidence:
            stats["rows_with_zero_evidence"] += 1

        # VERIFY risk_signals are NOT already in record (forward-looking only)
        verified_risks = [r for r in candidate_risks if _verify_risk_signal(r, record_text)]
        dropped_risks = [r for r in candidate_risks if r not in verified_risks]
        stats["risk_emitted"] += len(verified_risks)
        stats["risk_dropped_already_in_record"] += len(dropped_risks)
        if not verified_risks:
            stats["rows_with_zero_risk"] += 1

        # Build trigger_rule_ids from existing cited_knowledge_ids
        trigger_ids = _extract_kb_ids_from_detail(detail, row["cited_knowledge_ids"])

        stats["extracted"] += 1
        prefix = "[DRY] " if args.dry_run else ""
        print(f"  {prefix}[{i}/{len(rows)}] sug_id={sug_id} section={row['section']} "
              f"evidence={len(verified_evidence)}(+{len(dropped_evidence)} dropped) "
              f"risks={len(verified_risks)}(+{len(dropped_risks)} dropped) "
              f"triggers={len(trigger_ids)}")
        if verified_evidence and i <= 3:
            print(f"      evidence: {verified_evidence}")
        if dropped_evidence and i <= 3:
            print(f"      DROPPED:  {dropped_evidence}  (no record overlap)")

        if not args.dry_run:
            con.execute("""
                UPDATE ai_suggestions
                   SET evidence_json = ?,
                       risk_signals_json = ?,
                       trigger_rule_ids_json = ?
                 WHERE id = ?
            """, (
                json.dumps(verified_evidence, ensure_ascii=False) if verified_evidence else None,
                json.dumps(verified_risks, ensure_ascii=False) if verified_risks else None,
                json.dumps(trigger_ids, ensure_ascii=False) if trigger_ids else None,
                sug_id,
            ))

    if not args.dry_run:
        con.commit()
    con.close()

    print()
    print("=== Summary ===")
    for k, v in stats.items():
        print(f"  {k:40s} {v}")

    fab_rate = (stats["evidence_dropped_unverified"]
                / max(1, stats["evidence_emitted"] + stats["evidence_dropped_unverified"])
                * 100)
    print(f"\n  Fabrication-block rate: {fab_rate:.1f}% of LLM-extracted evidence items")
    print(f"  ({stats['evidence_dropped_unverified']} unverified items would have been")
    print(f"   stored as 'evidence' without the verification gate — exactly the bug we caught earlier.)")
    return 0


if __name__ == "__main__":
    import asyncio
    raise SystemExit(asyncio.run(main()))
