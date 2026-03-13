"""
使用 CMDD 数据集评估 vision.py OCR 精度。

CMDD 包含 240 张真实化验单扫描图像，以及单元格级别的文字标注 (labels_src.json)。
本脚本：
1. 随机抽取 N 张图像
2. 调用 vision.py extract_text_from_image
3. 对比提取文字与 ground truth
4. 计算字符级精度 (CER) 和关键字召回率

Usage:
    source .venv/bin/activate
    VISION_LLM=ollama ENVIRONMENT=development python scripts/eval_ocr_accuracy.py \
        --cmdd-dir /Volumes/ORICO/doctor-ai-agent/train/cmdd \
        --samples 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ENVIRONMENT", "development")


def _cer(ref: str, hyp: str) -> float:
    """Character Error Rate (edit distance / len(ref))."""
    if not ref:
        return 0.0
    import difflib
    matcher = difflib.SequenceMatcher(None, ref, hyp)
    ops = matcher.get_opcodes()
    errors = sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in ops
        if tag != "equal"
    )
    return errors / len(ref)


def _keyword_recall(ref_text: str, hyp_text: str) -> float:
    """Fraction of key terms in ref that also appear in hyp."""
    import re
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}", ref_text)
    if not tokens:
        return 1.0
    hits = sum(1 for t in tokens if t in hyp_text)
    return hits / len(tokens)


def load_annotations(cmdd_dir: Path) -> list[dict]:
    """Load CMDD labels_src.json — list of image annotations."""
    labels_path = cmdd_dir / "labels_src.json"
    with open(labels_path, encoding="utf-8") as f:
        data = json.load(f)
    return data


def annotation_to_ground_truth(ann: dict) -> str:
    """Concatenate all text cells from an annotation into ground-truth string."""
    cells = ann.get("annotations", [])
    texts = [c["text"] for c in cells if c.get("class") == "text" and c.get("text")]
    return "\n".join(texts)


def _build_annotation_index(annotations: list[dict], cmdd_dir: Path) -> dict[str, dict]:
    """Build a mapping from image filename to annotation dict.

    CMDD annotations typically contain an 'image' or 'filename' key that
    identifies the source image.  If neither is present, fall back to
    positional pairing but log a warning.
    """
    index: dict[str, dict] = {}
    for ann in annotations:
        # Try common keys that identify the source image
        fname = ann.get("image") or ann.get("filename") or ann.get("file")
        if fname:
            # Normalize to just the filename (strip any directory prefix)
            fname = Path(fname).name
            index[fname] = ann
    return index


async def eval_single(image_path: Path, ground_truth: str) -> dict:
    """Run OCR on one image and compute metrics."""
    from services.ai.vision import extract_text_from_image

    data = image_path.read_bytes()
    t0 = time.perf_counter()
    try:
        extracted = await extract_text_from_image(data, "image/jpeg")
        elapsed = time.perf_counter() - t0
        cer = _cer(ground_truth, extracted)
        recall = _keyword_recall(ground_truth, extracted)
        return {
            "image": image_path.name,
            "elapsed_s": round(elapsed, 2),
            "gt_chars": len(ground_truth),
            "ocr_chars": len(extracted),
            "cer": round(cer, 3),
            "keyword_recall": round(recall, 3),
            "gt_preview": ground_truth[:120],
            "ocr_preview": extracted[:120],
            "error": None,
        }
    except Exception as e:
        return {
            "image": image_path.name,
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "error": str(e),
            "cer": None,
            "keyword_recall": None,
        }


async def main_async(args: argparse.Namespace) -> None:
    cmdd_dir = Path(args.cmdd_dir)
    annotations = load_annotations(cmdd_dir)
    src_images = sorted((cmdd_dir / "src_image").glob("*.jpg"))

    print(f"CMDD: {len(annotations)} annotations, {len(src_images)} source images")
    print(f"Vision provider: {os.environ.get('VISION_LLM', 'ollama')}")

    # Build filename-based annotation index for reliable pairing
    ann_index = _build_annotation_index(annotations, cmdd_dir)

    if ann_index:
        # Pair by filename — reliable
        paired = [(img, ann_index[img.name]) for img in src_images if img.name in ann_index]
        if not paired:
            print("⚠️  No filename matches between annotations and images. "
                  "Falling back to positional pairing.")
            paired = [
                (src_images[i], annotations[i])
                for i in range(min(len(src_images), len(annotations)))
            ]
        else:
            print(f"  Paired by filename: {len(paired)} images matched")
    else:
        # No filename keys in annotations — fall back to positional pairing
        print("⚠️  Annotations lack image filename keys — using positional pairing. "
              "Results may be unreliable if sort orders diverge.")
        paired = [
            (src_images[i], annotations[i])
            for i in range(min(len(src_images), len(annotations)))
        ]

    print()

    # Sample N pairs
    n = min(args.samples, len(paired))
    sampled = random.sample(paired, n)

    results = []
    for i, (image_path, ann) in enumerate(sampled):
        gt = annotation_to_ground_truth(ann)

        print(f"[{i+1}/{n}] {image_path.name}  (GT: {len(gt)} chars)", end=" ... ", flush=True)
        result = await eval_single(image_path, gt)

        if result["error"]:
            print(f"ERROR: {result['error']}")
        else:
            print(f"CER={result['cer']:.1%}  recall={result['keyword_recall']:.1%}  {result['elapsed_s']}s")
            print(f"  GT:  {result['gt_preview']}")
            print(f"  OCR: {result['ocr_preview']}")
        results.append(result)

    # Summary
    print("\n" + "=" * 60)
    ok = [r for r in results if r["error"] is None]
    if ok:
        avg_cer = sum(r["cer"] for r in ok) / len(ok)
        avg_recall = sum(r["keyword_recall"] for r in ok) / len(ok)
        avg_time = sum(r["elapsed_s"] for r in ok) / len(ok)
        print(f"  Avg CER:            {avg_cer:.1%}  (lower is better)")
        print(f"  Avg keyword recall: {avg_recall:.1%}  (higher is better)")
        print(f"  Avg latency:        {avg_time:.1f}s")
        print(f"  Success rate:       {len(ok)}/{n}")
    else:
        print("  All samples failed — check VISION_LLM provider and model")

    # Save results
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Full results saved to: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate OCR accuracy against CMDD ground truth")
    parser.add_argument("--cmdd-dir", default="/Volumes/ORICO/doctor-ai-agent/train/cmdd",
                        help="Path to CMDD dataset directory")
    parser.add_argument("--samples", type=int, default=5,
                        help="Number of images to sample (default: 5)")
    parser.add_argument("--output", default="data/ocr_eval_results.json",
                        help="Save results JSON (default: data/ocr_eval_results.json)")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
