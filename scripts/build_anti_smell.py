#!/usr/bin/env python3
"""Build anti-AI-smell phrase artifact from corpus.

For each candidate phrase (commonly produced by LLMs), compute its
occurrence rate in real Chinese doctor data (MedDG multi-turn,
meddialog single-turn QA). Phrases that appear <0.05% in real data
are HARD-BANNED. Phrases 0.05%-1% are SOFT (avoid as closers, OK
in specific context). Above 1% means real doctors actually say it.

Output: data/style/anti_smell.json
Usage: PYTHONPATH=src .venv/bin/python scripts/build_anti_smell.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List

CORPUS_SAMPLE = Path(".context/corpus_sample")
OUT = Path("data/style/anti_smell.json")

# Candidate AI-smell phrases (LLM tells observed across many systems).
# Includes greeting variants, hedge closers, generic platitudes, and
# the imcs21 service-script tells Codex flagged.
CANDIDATES = [
    # Hard-zero candidates (expect <0.05% in real data)
    "希望对您有帮助",
    "希望我的回答对您有帮助",
    "综上所述",
    "祝您身体健康",
    "祝您早日康复",
    "愿您早日康复",
    "如有不适请及时就医",
    "如有不适及时就医",
    "请咨询专业医生",
    "请咨询医生",
    "请遵医嘱",
    "仅供参考",
    "请按时服药",
    "为了更好地为您提供服务",
    "为了更好的提供服务",
    "我是您的接诊医生",
    "祝您生活愉快",
    "祝您身体安康",
    # Generic platitudes (expect <1%, soft-block when chained)
    "多喝水",
    "注意休息",
    "清淡饮食",
    "保持心情愉悦",
    "劳逸结合",
    "避免熬夜",
    "适当运动",
    # Greeting/closer variants
    "您好！",
    "您好，",
    "亲，",
    "亲！",
    # Filler / preamble
    "根据您的描述",
    "根据您所描述的情况",
    "您所描述的",
    "您描述的症状",
    # Listing markers
    "首先，",
    "其次，",
    "最后，",
    "以下几点",
    "以下几方面",
    # Disclaimers
    "建议您",  # very weak hedge
    "如有疑问",
    "随时联系",
]


def load_doctor_turns_meddg(path: Path) -> List[str]:
    turns: List[str] = []
    with path.open() as f:
        for line in f:
            obj = json.loads(line)
            t = obj.get("doctor_turn", "")
            if t:
                turns.append(t)
    return turns


def load_doctor_turns_meddialog(path: Path) -> List[str]:
    turns: List[str] = []
    with path.open() as f:
        for line in f:
            obj = json.loads(line)
            t = obj.get("doctor", "")
            if t:
                turns.append(t)
    return turns


def classify(rate_meddg: float, rate_meddialog: float) -> str:
    """Return 'hard' (<0.05%), 'soft' (0.05-1%), or 'allowed' (>1%)."""
    max_rate = max(rate_meddg, rate_meddialog)
    if max_rate < 0.05:
        return "hard"
    if max_rate < 1.0:
        return "soft"
    return "allowed"


def main() -> int:
    meddg_path = CORPUS_SAMPLE / "meddg_doctor_turns.jsonl"
    meddialog_path = CORPUS_SAMPLE / "meddialog_pairs.jsonl"
    if not meddg_path.exists() or not meddialog_path.exists():
        print("ERROR: corpus samples missing. Run the dump script first.")
        return 1

    meddg_turns = load_doctor_turns_meddg(meddg_path)
    meddialog_turns = load_doctor_turns_meddialog(meddialog_path)
    print(f"Corpus: {len(meddg_turns)} MedDG turns, {len(meddialog_turns)} meddialog turns")

    results: Dict[str, Dict] = {}
    for phrase in CANDIDATES:
        n_meddg = sum(1 for t in meddg_turns if phrase in t)
        n_meddialog = sum(1 for t in meddialog_turns if phrase in t)
        rate_meddg = n_meddg / len(meddg_turns) * 100
        rate_meddialog = n_meddialog / len(meddialog_turns) * 100
        verdict = classify(rate_meddg, rate_meddialog)
        results[phrase] = {
            "meddg_count": n_meddg,
            "meddg_rate_pct": round(rate_meddg, 4),
            "meddialog_count": n_meddialog,
            "meddialog_rate_pct": round(rate_meddialog, 4),
            "verdict": verdict,
        }

    # Aggregate by verdict
    hard = [p for p, r in results.items() if r["verdict"] == "hard"]
    soft = [p for p, r in results.items() if r["verdict"] == "soft"]
    allowed = [p for p, r in results.items() if r["verdict"] == "allowed"]

    artifact = {
        "version": "1.0.0",
        "generated_at": "2026-04-25",
        "corpus": {
            "meddg_doctor_turns": len(meddg_turns),
            "meddialog_doctor_turns": len(meddialog_turns),
            "source": "/Volumes/ORICO/doctor-ai-agent/train (sampled)",
        },
        "thresholds": {
            "hard_block_max_pct": 0.05,
            "soft_block_max_pct": 1.0,
        },
        "summary": {
            "hard_block_count": len(hard),
            "soft_block_count": len(soft),
            "allowed_count": len(allowed),
        },
        "hard_block": sorted(hard),
        "soft_block": sorted(soft),
        "allowed_in_context": sorted(allowed),
        "phrase_details": results,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
    print(f"\nWrote: {OUT}")
    print(f"  hard-block ({len(hard)}): {sorted(hard)}")
    print(f"  soft-block ({len(soft)}): {sorted(soft)}")
    print(f"  allowed ({len(allowed)}): {sorted(allowed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
