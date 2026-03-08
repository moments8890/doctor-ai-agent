"""
Train a TF-IDF + logistic regression binary classifier for Tier-3 routing.

Usage:
    python scripts/train_tier3_classifier.py [--out services/ai/tier3_classifier.pkl]

Output: a pickle file containing a sklearn Pipeline (TfidfVectorizer → LogisticRegression).

The classifier is used as the final gate in _is_clinical_tier3() in fast_router.py.
It fires ONLY when all keyword + regex guards would return True, so it only needs to
distinguish real clinical notes from the hard-floor cases that keywords can't handle.

Training data
─────────────
Positive (clinical notes):
  - CHIP-CDEE train + dev  (1,971 discharge event sentences)
  - Yidu-S4K training part 1 + 2 + test  (full EMR discharge records)

Negative (patient / lay messages):
  - MedDialog-CN patient turns  (sampled — 2.7M total, use 100k)
  - Huatuo consultation questions  (sampled — 4.3M total, use 100k)
  - webMedQA questions  (12k total, use all)

Expected output: ~2-5% FP on hard-floor datasets, sub-millisecond inference.
"""

from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
from pathlib import Path

# ── Data loading ──────────────────────────────────────────────────────────────

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "train" / "data"


def load_chip_cdee() -> list[str]:
    texts: list[str] = []
    for fname in ("CHIP-CDEE_train.json", "CHIP-CDEE_dev.json"):
        p = DATA / "CHIP-CDEE" / fname
        if not p.exists():
            print(f"  [warn] {p} not found, skipping", file=sys.stderr)
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for item in data:
            t = item.get("text", "").strip()
            if t:
                texts.append(t)
    print(f"  CHIP-CDEE: {len(texts)} records")
    return texts


def load_yidu_s4k() -> list[str]:
    texts: list[str] = []
    s4k_dir = DATA / "yidu_s4k"

    # Training txt files (JSONL, UTF-8 BOM, one JSON per line)
    for fname in ("subtask1_training_part1.txt", "subtask1_training_part2.txt"):
        p = s4k_dir / fname
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line).get("originalText", "").strip()
                if t:
                    texts.append(t)
            except json.JSONDecodeError:
                pass

    # Test set (JSONL, same format)
    test_p = s4k_dir / "subtask1_test_set_with_answer.json"
    if test_p.exists():
        for line in test_p.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line).get("originalText", "").strip()
                if t:
                    texts.append(t)
            except json.JSONDecodeError:
                pass

    print(f"  Yidu-S4K: {len(texts)} records")
    return texts


def load_meddialog_patient(max_samples: int = 100_000) -> list[str]:
    texts: list[str] = []
    p = DATA / "meddialog" / "zh_train.json"
    if not p.exists():
        print("  [warn] meddialog/zh_train.json not found, skipping", file=sys.stderr)
        return texts

    print("  Loading MedDialog-CN (this may take a moment)...", flush=True)
    dialogues = json.loads(p.read_text(encoding="utf-8"))

    rng = random.Random(42)
    rng.shuffle(dialogues)

    for dialogue in dialogues:
        if len(texts) >= max_samples:
            break
        if not isinstance(dialogue, list):
            continue
        for turn in dialogue:
            if len(texts) >= max_samples:
                break
            if isinstance(turn, str) and turn.startswith("病人："):
                t = turn[3:].strip()
                if len(t) >= 5:
                    texts.append(t)

    print(f"  MedDialog-CN patient: {len(texts)} turns (capped at {max_samples})")
    return texts


def load_huatuo_consultation(max_samples: int = 100_000) -> list[str]:
    texts: list[str] = []
    p = DATA / "huatuo_consultation_qa" / "train_datasets.jsonl"
    if not p.exists():
        print("  [warn] huatuo_consultation_qa/train_datasets.jsonl not found, skipping", file=sys.stderr)
        return texts

    print("  Loading Huatuo consultation (streaming)...", flush=True)
    seen = 0
    with p.open(encoding="utf-8") as f:
        for line in f:
            if len(texts) >= max_samples:
                break
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                qs = item.get("questions", [])
                if qs and isinstance(qs, list):
                    t = qs[0].strip()
                    if len(t) >= 5:
                        texts.append(t)
                        seen += 1
            except json.JSONDecodeError:
                pass

    print(f"  Huatuo consultation: {len(texts)} questions (capped at {max_samples})")
    return texts


def load_webmedqa() -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for fname in ("medQA.test.txt", "medQA.valid.txt"):
        p = DATA / "webmedqa" / fname
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            t = parts[3].strip()
            if t and t not in seen:
                seen.add(t)
                texts.append(t)
    print(f"  webMedQA: {len(texts)} questions")
    return texts


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="services/ai/tier3_classifier.pkl")
    parser.add_argument("--max-neg", type=int, default=100_000,
                        help="Max negative samples per source (default: 100k)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import cross_val_score
    import numpy as np

    rng = random.Random(args.seed)

    print("\n=== Loading positive samples (clinical notes) ===")
    pos = load_chip_cdee() + load_yidu_s4k()
    print(f"Total positive: {len(pos)}")

    print("\n=== Loading negative samples (patient messages) ===")
    neg = (
        load_meddialog_patient(args.max_neg)
        + load_huatuo_consultation(args.max_neg)
        + load_webmedqa()
    )
    print(f"Total negative: {len(neg)}")

    # Balance: downsample negative to 5× positive (keeps more signal than 1:1)
    max_neg = min(len(neg), len(pos) * 5)
    rng.shuffle(neg)
    neg = neg[:max_neg]
    print(f"Negative after balancing (5:1): {len(neg)}")

    X = pos + neg
    y = [1] * len(pos) + [0] * len(neg)

    # Shuffle
    combined = list(zip(X, y))
    rng.shuffle(combined)
    X, y = zip(*combined)

    print("\n=== Training TF-IDF + Logistic Regression ===")
    print(f"Total samples: {len(X)} ({sum(y)} positive, {len(y)-sum(y)} negative)")

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",   # character n-grams with word boundaries
            ngram_range=(2, 4),   # bigrams to 4-grams; captures clinical phrases
            max_features=100_000,
            sublinear_tf=True,    # log(1+tf) — reduces dominance of very frequent n-grams
            min_df=2,             # ignore n-grams appearing in fewer than 2 samples
        )),
        ("clf", LogisticRegression(
            C=1.0,
            max_iter=1000,
            solver="lbfgs",
            class_weight="balanced",  # compensate for any remaining class imbalance
            random_state=args.seed,
        )),
    ])

    # 5-fold CV for a quick sanity check
    print("Running 5-fold cross-validation...")
    scores = cross_val_score(pipeline, X, y, cv=5, scoring="f1", n_jobs=-1)
    print(f"F1 (5-fold CV): {scores.mean():.3f} ± {scores.std():.3f}")

    # Train on full data
    print("Training on full dataset...")
    pipeline.fit(X, y)

    # Quick self-evaluation
    y_pred = pipeline.predict(X)
    y_arr = np.array(y)
    tp = ((y_pred == 1) & (y_arr == 1)).sum()
    fp = ((y_pred == 1) & (y_arr == 0)).sum()
    fn = ((y_pred == 0) & (y_arr == 1)).sum()
    tn = ((y_pred == 0) & (y_arr == 0)).sum()
    print(f"Train set: TP={tp}, FP={fp}, FN={fn}, TN={tn}")
    print(f"Train precision: {tp/(tp+fp):.3f}, recall: {tp/(tp+fn):.3f}")

    # Save
    out_path = BASE / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        pickle.dump(pipeline, f, protocol=5)
    print(f"\nSaved to {out_path}")

    # Feature importance: top clinical vs patient n-grams
    tfidf = pipeline.named_steps["tfidf"]
    clf = pipeline.named_steps["clf"]
    feature_names = tfidf.get_feature_names_out()
    coefs = clf.coef_[0]
    top_clinical = sorted(zip(coefs, feature_names), reverse=True)[:20]
    top_patient = sorted(zip(coefs, feature_names))[:20]
    print("\nTop clinical n-grams (→ add_record):")
    for coef, feat in top_clinical:
        print(f"  {feat!r:20s}  {coef:+.3f}")
    print("\nTop patient n-grams (→ LLM):")
    for coef, feat in top_patient:
        print(f"  {feat!r:20s}  {coef:+.3f}")


if __name__ == "__main__":
    main()
