"""
从 CBLUE 数据集提取高频临床词汇，扩展 fast_router.py 的 Tier 3 关键词列表。

Usage:
    source .venv/bin/activate
    python scripts/expand_clinical_keywords.py

Output:
    - 打印新发现的临床词汇（按频率排序）
    - 写入 data/cblue_clinical_keywords.json
    - 可选：--apply 直接更新 fast_router.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Entity types we care about ────────────────────────────────────────────────
# CMeEE entity type codes → description
KEEP_TYPES = {
    "sym",  # symptom 症状
    "dis",  # disease 疾病
    "dru",  # drug 药物
    "pro",  # procedure 医疗操作
    "dep",  # department 科室
}

# Min chars — skip single-char and overly generic terms
MIN_LEN = 2
# Min frequency across dataset to be included
MIN_FREQ = 3
# Max chars — skip sentences accidentally tagged as entities
MAX_LEN = 12


def _parse_entities(entities_str: str) -> list[tuple[str, str]]:
    """Parse CMeEE entity string into (type, name) pairs.

    Format: "实体1：类型sym，实体名：头痛\n实体2：类型dis，实体名：高血压\n"
    """
    results = []
    for match in re.finditer(r"类型(\w+)，实体名：([^\n]+)", entities_str):
        etype = match.group(1).strip()
        ename = match.group(2).strip()
        results.append((etype, ename))
    return results


def load_cmeee() -> Counter:
    """Load CMeEE dataset and count entity frequencies."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: datasets not installed. Run: pip install datasets")
        sys.exit(1)

    print("Downloading CMeEE from HuggingFace (wyp/cblue-cmeee)...")
    ds = load_dataset("wyp/cblue-cmeee")

    counts: Counter = Counter()
    total = 0
    for split in ds.values():
        for row in split:
            pairs = _parse_entities(row.get("entities", ""))
            for etype, ename in pairs:
                if etype in KEEP_TYPES and MIN_LEN <= len(ename) <= MAX_LEN:
                    counts[ename] += 1
                    total += 1

    print(f"  Parsed {total} entity mentions, {len(counts)} unique terms")
    return counts


def load_cdn() -> Counter:
    """Load CDN dataset — normalized diagnosis terms."""
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit(1)

    print("Downloading CDN from HuggingFace (wyp/cblue-cdn)...")
    ds = load_dataset("wyp/cblue-cdn")

    counts: Counter = Counter()
    for split in ds.values():
        for row in split:
            # Both raw and normalized terms are useful
            for field in ("text", "normalized_result"):
                term = row.get(field, "").strip()
                if MIN_LEN <= len(term) <= MAX_LEN:
                    counts[term] += 1

    print(f"  Parsed {len(counts)} unique diagnosis terms")
    return counts


def load_existing_keywords() -> frozenset[str]:
    """Load the current Tier 3 keywords from fast_router.py."""
    router_path = Path(__file__).resolve().parents[1] / "services" / "ai" / "fast_router.py"
    text = router_path.read_text(encoding="utf-8")
    # Extract the frozenset literal
    m = re.search(r"_CLINICAL_KW_TIER3.*?frozenset\(\{(.*?)\}\)", text, re.DOTALL)
    if not m:
        return frozenset()
    raw = m.group(1)
    # Extract all quoted strings
    return frozenset(re.findall(r'"([^"]+)"', raw))


def filter_new_terms(counts: Counter, existing: frozenset[str], min_freq: int) -> list[tuple[str, int]]:
    """Return terms not already in fast_router, sorted by frequency."""
    new_terms = [
        (term, freq)
        for term, freq in counts.most_common()
        if freq >= min_freq
        and term not in existing
        and not any(c.isdigit() or c in "（）()[]【】" for c in term)
    ]
    return new_terms


def apply_to_fast_router(new_terms: list[tuple[str, int]], dry_run: bool = True) -> None:
    """Append new terms to _CLINICAL_KW_TIER3 in fast_router.py."""
    router_path = Path(__file__).resolve().parents[1] / "services" / "ai" / "fast_router.py"
    text = router_path.read_text(encoding="utf-8")

    # Find the closing brace of _CLINICAL_KW_TIER3
    insert_marker = "# ── _CLINICAL_KW_TIER3 end ──"
    if insert_marker not in text:
        # Find last line before the closing }) of the frozenset
        m = re.search(r"(_CLINICAL_KW_TIER3: frozenset\[str\] = frozenset\(\{)(.*?)(\}\))",
                      text, re.DOTALL)
        if not m:
            print("ERROR: Could not locate _CLINICAL_KW_TIER3 in fast_router.py")
            return

        # Group terms by category for readability
        terms_str = ",\n    ".join(f'"{t}"' for t, _ in new_terms[:60])  # cap at 60
        new_block = m.group(1) + m.group(2).rstrip() + f",\n    # CBLUE-expanded\n    {terms_str},\n" + m.group(3)

        if dry_run:
            print("\n[DRY RUN] Would add to _CLINICAL_KW_TIER3:")
            for term, freq in new_terms[:20]:
                print(f"  {term!r}  (freq={freq})")
            if len(new_terms) > 20:
                print(f"  ... and {len(new_terms) - 20} more")
        else:
            router_path.write_text(text.replace(m.group(0), new_block), encoding="utf-8")
            print(f"Updated fast_router.py — added {min(60, len(new_terms))} terms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand fast router clinical keywords from CBLUE")
    parser.add_argument("--min-freq", type=int, default=MIN_FREQ,
                        help=f"Minimum entity frequency to include (default: {MIN_FREQ})")
    parser.add_argument("--top", type=int, default=80,
                        help="Show top N new terms (default: 80)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually update fast_router.py (default: dry run)")
    parser.add_argument("--output", type=str, default="data/cblue_clinical_keywords.json",
                        help="Save extracted terms to this JSON file")
    args = parser.parse_args()

    # Load data
    cmeee_counts = load_cmeee()
    cdn_counts = load_cdn()

    # Merge counts
    merged: Counter = Counter()
    merged.update(cmeee_counts)
    merged.update(cdn_counts)

    # Compare against existing keywords
    existing = load_existing_keywords()
    print(f"\nExisting Tier 3 keywords: {len(existing)}")

    new_terms = filter_new_terms(merged, existing, args.min_freq)
    print(f"New terms found (freq >= {args.min_freq}): {len(new_terms)}")

    # Save to file
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"terms": [{"term": t, "freq": f} for t, f in new_terms]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved to {out_path}")

    # Print top N
    print(f"\n=== Top {args.top} new clinical terms ===")
    print(f"{'Term':<15} {'Freq':>6}")
    print("-" * 25)
    for term, freq in new_terms[:args.top]:
        print(f"{term:<15} {freq:>6}")

    # Apply or dry-run
    apply_to_fast_router(new_terms, dry_run=not args.apply)

    if not args.apply:
        print("\nRun with --apply to update fast_router.py")


if __name__ == "__main__":
    main()
