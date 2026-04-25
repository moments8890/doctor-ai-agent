#!/usr/bin/env python3
"""Build curated complaint-clustered example pool from MedDG + meddialog.

Implements the curation gate from project_ai_smell_plan_2026-04-25:
- Length 8-200 chars
- Drop platform-promo (微信/vx/私信/http://)
- Drop turns containing hard-block phrases (anti-smell)
- Drop pure acknowledgment turns unless paired with concrete next step
- Drop multi-question (>1 ?) or list-format turns
- Dedupe near-duplicates (exact match)
- Empathy floor: drop dismissiveness phrases

Then cluster by chief-complaint keyword (per Codex round 4: only 5
specialties are corpus-supported — GI/respiratory/peds/OBGYN/derm).

Output: data/style/example_pool.json
Usage: PYTHONPATH=src .venv/bin/python scripts/build_example_pool.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

CORPUS = Path(".context/corpus_sample")
ANTI_SMELL = Path("data/style/anti_smell.json")
OUT = Path("data/style/example_pool.json")

# Complaint clusters — keyword sets per topic. Per Codex round 4, MedDG
# has usable volume (>=200 examples) only for these GI clusters.
COMPLAINT_CLUSTERS: Dict[str, List[str]] = {
    "diarrhea":        ["拉稀", "拉肚子", "腹泻", "稀便", "水样便", "拉的稀"],
    "abdominal_pain":  ["腹痛", "肚子疼", "肚子痛", "胃疼", "胃痛", "胃部不适",
                        "胃不舒服", "胃难受", "胃还有点疼", "肚子不舒服", "肚子难受",
                        "上腹", "下腹", "脐周"],
    "nausea_vomit":    ["恶心", "想吐", "呕吐", "吐了", "反胃"],
    "constipation":    ["便秘", "排便困难", "大不出来", "拉不出来"],
    "fever":           ["发烧", "发热", "体温高", "发低烧", "高烧"],
    "cough":           ["咳嗽", "干咳", "咳痰", "老咳", "一直咳"],
    "headache":        ["头痛", "头疼", "偏头痛", "头晕", "头胀"],
    "chest_pain":      ["胸痛", "胸闷", "心绞痛", "胸口疼", "胸口不舒服", "心慌"],
    "rash":            ["皮疹", "红疹", "起疹", "皮肤痒", "湿疹", "起红点"],
    "menstrual":       ["月经", "经期", "痛经", "例假", "大姨妈"],
    "pregnancy":       ["怀孕", "孕妇", "孕期", "宫内", "怀了"],
}

# Pure-acknowledgment turns (drop unless paired with concrete next step)
PURE_ACK = re.compile(r"^(嗯+\.?|好的\.?|是的\.?|可以\.?|了解\.?)$")

# Concrete next-step markers — if a turn has acknowledgment AND one of these,
# it's a useful exemplar (e.g. "嗯。多久了？" or "好的。先观察。")
NEXT_STEP_MARKERS = ["？", "?", "建议", "做个", "检查", "可以", "先", "观察", "去医院"]

# Empathy floor: dismissiveness phrases (drop)
DISMISSIVE = ["不知道", "我也没办法", "看运气", "无解", "不好说"]

# Platform-promo / spam
PROMO = ["微信", "vx", "私信", "加我", "联系我", "http://", "https://", "qq", "QQ"]


def load_anti_smell_phrases() -> List[str]:
    if not ANTI_SMELL.is_file():
        return []
    art = json.loads(ANTI_SMELL.read_text(encoding="utf-8"))
    return art.get("hard_block", [])


def is_curated(text: str, banned: List[str]) -> tuple[bool, str]:
    """Return (keep, reject_reason). reject_reason='' if keep."""
    if not text:
        return False, "empty"
    n = len(text)
    if n < 8:
        return False, "too_short"
    if n > 200:
        return False, "too_long"
    for p in PROMO:
        if p in text:
            return False, f"promo:{p}"
    for p in banned:
        if p in text:
            return False, f"banned_phrase:{p}"
    for p in DISMISSIVE:
        if p in text:
            return False, f"dismissive:{p}"
    if PURE_ACK.match(text.strip()) and not any(m in text for m in NEXT_STEP_MARKERS):
        return False, "pure_ack"
    n_q = text.count("？") + text.count("?")
    if n_q > 2:
        return False, "multi_question"
    if re.search(r"^\s*(\d[\.\)、]|首先|其次|最后)", text):
        return False, "list_format"
    list_markers = sum(1 for m in re.findall(r"\d[\.\)、]", text))
    if list_markers > 2:
        return False, "list_format_inline"
    return True, ""


def classify_complaint(patient_text: str) -> List[str]:
    """Return all matching complaint cluster keys."""
    matches = []
    for cluster, keywords in COMPLAINT_CLUSTERS.items():
        if any(k in patient_text for k in keywords):
            matches.append(cluster)
    return matches


def main() -> int:
    banned = load_anti_smell_phrases()
    print(f"Loaded {len(banned)} hard-block phrases for filtering")

    # Load both corpora
    meddg_pairs = []
    with (CORPUS / "meddg_doctor_turns.jsonl").open() as f:
        for line in f:
            o = json.loads(line)
            meddg_pairs.append({
                "patient": o.get("patient_prior", ""),
                "doctor":  o.get("doctor_turn", ""),
                "is_first_doctor_turn": o.get("is_first_doctor_turn", False),
                "source": "meddg",
            })
    meddialog_pairs = []
    with (CORPUS / "meddialog_pairs.jsonl").open() as f:
        for line in f:
            o = json.loads(line)
            meddialog_pairs.append({
                "patient": o.get("patient", ""),
                "doctor":  o.get("doctor", ""),
                "is_first_doctor_turn": True,  # meddialog is single-turn QA
                "source": "meddialog",
            })

    all_pairs = meddg_pairs + meddialog_pairs
    print(f"Loaded {len(meddg_pairs)} MedDG + {len(meddialog_pairs)} meddialog pairs = {len(all_pairs)} total")

    # Curate
    reject_reasons = Counter()
    seen_doctor_turns = set()
    curated = []
    for pair in all_pairs:
        if not pair["patient"] or not pair["doctor"]:
            reject_reasons["empty_pair"] += 1
            continue
        keep, reason = is_curated(pair["doctor"], banned)
        if not keep:
            reject_reasons[reason] += 1
            continue
        # Dedupe exact-match doctor turns (style-pool diversity)
        if pair["doctor"] in seen_doctor_turns:
            reject_reasons["duplicate"] += 1
            continue
        seen_doctor_turns.add(pair["doctor"])
        curated.append(pair)

    print(f"\nCuration: {len(curated)}/{len(all_pairs)} kept ({100*len(curated)/len(all_pairs):.1f}%)")
    print("Top reject reasons:")
    for r, n in reject_reasons.most_common(10):
        print(f"  {n:5d}  {r}")

    # Cluster
    clusters: Dict[str, List[Dict]] = defaultdict(list)
    unclustered = 0
    for pair in curated:
        topics = classify_complaint(pair["patient"])
        if not topics:
            unclustered += 1
            continue
        # Append to all matching clusters (multi-complaint patient)
        for t in topics:
            clusters[t].append({
                "patient": pair["patient"][:300],
                "doctor": pair["doctor"][:300],
                "is_first_doctor_turn": pair["is_first_doctor_turn"],
                "source": pair["source"],
            })

    # Sort each cluster by source diversity then length variety,
    # cap at 50 per cluster (deterministic top-ranked, per round-2 codex correction)
    for k in clusters:
        clusters[k].sort(key=lambda x: (x["source"], len(x["doctor"])))
        clusters[k] = clusters[k][:50]

    cluster_counts = {k: len(v) for k, v in clusters.items()}
    usable = {k: n for k, n in cluster_counts.items() if n >= 10}
    sparse = {k: n for k, n in cluster_counts.items() if n < 10}

    artifact = {
        "version": "1.0.0",
        "generated_at": "2026-04-25",
        "corpus": {
            "meddg_pairs": len(meddg_pairs),
            "meddialog_pairs": len(meddialog_pairs),
        },
        "curation": {
            "input_total": len(all_pairs),
            "kept": len(curated),
            "kept_pct": round(100 * len(curated) / len(all_pairs), 2),
            "reject_reasons": dict(reject_reasons.most_common()),
        },
        "clusters_summary": {
            "usable_clusters_n>=10": usable,
            "sparse_clusters_n<10":  sparse,
            "unclustered": unclustered,
        },
        "clusters": dict(clusters),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
    print(f"\nWrote: {OUT}")
    print(f"  Usable clusters (n>=10): {usable}")
    print(f"  Sparse clusters (n<10):  {sparse}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
