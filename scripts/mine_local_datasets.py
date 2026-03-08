"""
从本地医疗数据集提取临床关键词，扩展 fast_router.py 的 Tier 3 关键词列表。

支持数据集:
  - RAG-精选医疗问答_onecolumn_80k.csv  (80k curated medical Q&A)
  - CMedQA2/question.csv + answer.csv    (120k patient Q&A)
  - CMExam/data/train.csv               (medical licensing exam MCQs)

Usage:
    source .venv/bin/activate
    python scripts/mine_local_datasets.py --data-dir /Volumes/ORICO/doctor-ai-agent/train/data
    python scripts/mine_local_datasets.py --data-dir /Volumes/ORICO/doctor-ai-agent/train/data --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Config ────────────────────────────────────────────────────────────────────
MIN_LEN = 2
MAX_LEN = 10
MIN_FREQ = 5         # min occurrences across all datasets to be included
MAX_TERMS_APPLY = 80 # max terms to auto-apply to fast_router

# Patterns that indicate a clinical signal (used to score candidate terms)
_CLINICAL_CTX_RE = re.compile(
    r"诊断|治疗|症状|检查|手术|用药|病史|病情|患者|就诊|复查|化验|影像|CT|MRI|B超"
)

# Generic words that should be excluded even if frequent in medical text
_STOP_TERMS = frozenset({
    # Generic clinical process words (too vague for routing)
    "患者", "医生", "医院", "治疗", "检查", "手术", "建议", "症状",
    "病情", "病史", "用药", "药物", "检验", "结果", "报告", "指标",
    "医疗", "门诊", "住院", "科室", "复查", "就诊", "数据", "数值",
    "疾病", "功能", "原因", "表现", "作用", "效果", "影响",
    # Greetings / conversational
    "你好", "您好", "谢谢", "祝健康", "祝你健康", "祝您健康",
    "祝早日康复", "祝你早日康复", "祝您早日康复", "你好朋友",
    "请问", "谢谢了", "多谢",
    # Patient question phrases
    "怎么办", "怎么回事", "是怎么回事", "这是怎么回事", "该怎么办",
    "我该怎么办", "是什么原因", "有什么办法", "怎么治疗", "如何治疗",
    "根据你的描述", "根据您的描述", "根据", "我怀孕", "我的情况",
    "吃什么药", "么回事", "是怎么", "病时间及原因",
    # Exam / template phrases
    "知识点", "错误的是", "正确的是", "为本题正确答案", "为本题的正确答案",
    "本题考查", "年考试指南未明确说明", "除另有规定外", "病例分析",
    "最可能的诊断是", "指导意见", "全部症状", "发病时间及原因",
    "中国药典", "药品管理法", "个品种", "中成药应用", "方剂应用",
    "性状鉴别", "主治病证", "主治",
    # Too generic
    "可以", "需要", "注意", "可能", "一般", "情况", "问题", "方面",
    "引起", "导致", "出现", "进行", "发现", "感觉", "一定", "应该",
    "比较", "不是", "没有", "正常", "身体", "时候", "已经", "自己",
    "还是", "这种", "那么", "或者", "但是", "如果", "所以", "因为",
    "然后", "还有", "个月", "天了", "分钟", "小时", "一般来说",
    "根据", "因此", "另外", "男性", "女性", "规定", "正常吗",
    "正常值", "意见建议", "病情分析", "治疗情况", "对症治疗",
    "查体", "患者信息", "实验室检查", "超检查",
    # Lifestyle advice (not clinical diagnosis/symptom terms)
    "多喝水", "注意休息", "注意保暖", "加强营养", "增强体质", "多休息",
    "保持心情舒畅", "祝早日",
})

# A term must contain at least one clinical root to be a candidate
_CLINICAL_ROOT_RE = re.compile(
    r"炎|癌|瘤|症|病|痛|肿|栓|梗|囊|结|痿|疝|畸|萎|脓|积液|损伤"
    r"|出血|骨折|感染|溃疡|坏死|硬化|狭窄|穿孔|粘连|扭转"
    r"|肺|肝|肾|心|脑|胃|肠|胆|脾|胰|膀|子宫|卵巢|甲状|乳腺"
    r"|血糖|血压|血脂|血红|白细胞|红细胞|血小板|肌酐|尿素|转氨酶"
    r"|切除|穿刺|活检|造影|内镜|扫描|放疗|化疗|透析"
    r"|晕|咳|喘|悸|麻|胀|泻|秘|呕|渴|烦|乏力|无力|苍白|水肿"
)

# Chinese term extractor: 2-10 consecutive Chinese characters
_ZH_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,10}")


def _extract_terms(text: str) -> list[str]:
    """Extract Chinese candidate terms from text."""
    return [t for t in _ZH_TERM_RE.findall(text) if t not in _STOP_TERMS]


def load_rag_80k(data_dir: Path) -> Counter:
    """Load RAG-精选医疗问答_onecolumn_80k.csv."""
    path = data_dir / "baidu" / "RAG-精选医疗问答_onecolumn_80k.csv"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return Counter()

    counts: Counter = Counter()
    rows = 0
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if row:
                counts.update(_extract_terms(row[0]))
                rows += 1
    print(f"  RAG 80k: {rows} rows, {len(counts)} unique terms")
    return counts


def load_cmedqa2(data_dir: Path) -> Counter:
    """Load CMedQA2 questions + answers."""
    q_path = data_dir / "cmedqa2" / "question.csv"
    a_path = data_dir / "cmedqa2" / "answer.csv"
    if not q_path.exists():
        print(f"  SKIP: {q_path} not found")
        return Counter()

    counts: Counter = Counter()
    rows = 0
    for path in [q_path, a_path]:
        if not path.exists():
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    counts.update(_extract_terms(row[1]))
                    rows += 1
    print(f"  CMedQA2: {rows} rows, {len(counts)} unique terms")
    return counts


def load_cmexam(data_dir: Path, max_rows: int = 60_000) -> Counter:
    """Load CMExam train.csv — use Question + Explanation columns."""
    path = data_dir / "cmexam" / "data" / "train.csv"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return Counter()

    counts: Counter = Counter()
    rows = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("Question", "") + " " + row.get("Explanation", ""))
            counts.update(_extract_terms(text))
            rows += 1
            if rows >= max_rows:
                break
    print(f"  CMExam: {rows} rows, {len(counts)} unique terms")
    return counts


def load_baidu_list(data_dir: Path, max_rows: int = 100_000) -> Counter:
    """Load Baidu list train_list.txt — tab-separated [id, question, answer] triples."""
    path = data_dir / "baidu" / "list" / "train_list.txt"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return Counter()

    counts: Counter = Counter()
    rows = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().split("\t")
            # Extract both question (parts[1]) and answer (parts[2]) text
            for idx in (1, 2):
                if idx < len(parts) and parts[idx]:
                    counts.update(_extract_terms(parts[idx]))
            rows += 1
            if rows >= max_rows:
                break
    print(f"  Baidu list: {rows} rows, {len(counts)} unique terms")
    return counts


def load_baidu_finetune_sample(data_dir: Path, sample: int = 10_000) -> Counter:
    """Load a sample of Baidu finetune train_zh_0.json (too large to load all)."""
    path = data_dir / "baidu" / "medical_data" / "finetune" / "train_zh_0.json"
    if not path.exists():
        print(f"  SKIP: {path} not found")
        return Counter()

    counts: Counter = Counter()
    rows = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                text = obj.get("instruction", "") + " " + obj.get("output", "")
                counts.update(_extract_terms(text))
            except json.JSONDecodeError:
                continue
            rows += 1
            if rows >= sample:
                break
    print(f"  Baidu finetune (sample {sample}): {rows} rows, {len(counts)} unique terms")
    return counts


def load_existing_keywords() -> frozenset[str]:
    """Load current Tier 3 keywords from fast_router.py."""
    router_path = Path(__file__).resolve().parents[1] / "services" / "ai" / "fast_router.py"
    text = router_path.read_text(encoding="utf-8")
    m = re.search(r"_CLINICAL_KW_TIER3.*?frozenset\(\{(.*?)\}\)", text, re.DOTALL)
    if not m:
        return frozenset()
    return frozenset(re.findall(r'"([^"]+)"', m.group(1)))


def score_term(term: str, freq: int) -> float:
    """Score a term for clinical relevance. Higher = more likely to be clinical."""
    score = freq
    # Boost multi-character clinical patterns
    if re.search(r"炎|症|病|痛|癌|瘤|结|梗|塞|栓|肿|囊|息肉|增生|手术|切除", term):
        score *= 2
    if re.search(r"高|低|增|减|异常|阳性|阴性", term):
        score *= 1.5
    # Penalty for very generic terms
    if len(term) <= 2 and not re.search(r"炎|癌|痛|肿|瘤", term):
        score *= 0.5
    return score


def filter_candidates(
    counts: Counter,
    existing: frozenset[str],
    min_freq: int,
) -> list[tuple[str, int, float]]:
    """Return (term, freq, score) for new candidate terms.

    Strict filter: must contain a clinical root word. This eliminates
    greetings, Q&A templates, exam phrases that dominate the raw counts.
    """
    results = []
    for term, freq in counts.items():
        if freq < min_freq:
            continue
        if term in existing:
            continue
        if term in _STOP_TERMS:
            continue
        # Must be purely Chinese
        if not re.match(r"^[\u4e00-\u9fff]+$", term):
            continue
        if len(term) < MIN_LEN or len(term) > MAX_LEN:
            continue
        # STRICT: must contain a clinical root
        if not _CLINICAL_ROOT_RE.search(term):
            continue
        s = score_term(term, freq)
        results.append((term, freq, s))
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def apply_to_fast_router(candidates: list[tuple[str, int, float]], max_terms: int) -> None:
    """Append top candidates to _CLINICAL_KW_TIER3 in fast_router.py."""
    router_path = Path(__file__).resolve().parents[1] / "services" / "ai" / "fast_router.py"
    text = router_path.read_text(encoding="utf-8")

    m = re.search(
        r"(_CLINICAL_KW_TIER3: frozenset\[str\] = frozenset\(\{)(.*?)(\}\))",
        text,
        re.DOTALL,
    )
    if not m:
        print("ERROR: Could not find _CLINICAL_KW_TIER3 in fast_router.py")
        return

    top = candidates[:max_terms]
    terms_str = ",\n    ".join(f'"{t}"' for t, _, _ in top)
    new_block = (
        m.group(1)
        + m.group(2).rstrip()
        + f",\n    # Local-dataset-expanded ({len(top)} terms)\n    {terms_str},\n"
        + m.group(3)
    )
    router_path.write_text(text.replace(m.group(0), new_block), encoding="utf-8")
    print(f"\n✅ Updated fast_router.py — added {len(top)} terms to _CLINICAL_KW_TIER3")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine clinical keywords from local medical datasets")
    parser.add_argument("--data-dir", default="/Volumes/ORICO/doctor-ai-agent/train/data",
                        help="Root directory of train/data (default: /Volumes/ORICO/...)")
    parser.add_argument("--min-freq", type=int, default=MIN_FREQ,
                        help=f"Min frequency across all datasets (default: {MIN_FREQ})")
    parser.add_argument("--top", type=int, default=100,
                        help="Show top N candidates (default: 100)")
    parser.add_argument("--apply", action="store_true",
                        help="Auto-apply top terms to fast_router.py (default: dry run)")
    parser.add_argument("--output", default="data/local_dataset_keywords.json",
                        help="Save candidates to JSON (default: data/local_dataset_keywords.json)")
    parser.add_argument("--no-baidu-finetune", action="store_true",
                        help="Skip Baidu finetune (1.3GB) even in sample mode")
    parser.add_argument("--no-baidu-list", action="store_true",
                        help="Skip Baidu list QA (226k pairs)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"ERROR: data-dir not found: {data_dir}")
        sys.exit(1)

    print("Loading datasets...")
    counts: Counter = Counter()
    counts.update(load_rag_80k(data_dir))
    counts.update(load_cmedqa2(data_dir))
    counts.update(load_cmexam(data_dir))
    if not args.no_baidu_list:
        counts.update(load_baidu_list(data_dir))
    if not args.no_baidu_finetune:
        counts.update(load_baidu_finetune_sample(data_dir))

    print(f"\nTotal unique terms across all datasets: {len(counts)}")

    existing = load_existing_keywords()
    print(f"Existing Tier 3 keywords: {len(existing)}")

    candidates = filter_candidates(counts, existing, args.min_freq)
    print(f"New candidates (freq >= {args.min_freq}): {len(candidates)}")

    # Save all candidates
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"candidates": [{"term": t, "freq": f, "score": round(s, 1)} for t, f, s in candidates]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved {len(candidates)} candidates to {out}")

    # Display top N
    print(f"\n{'Term':<12} {'Freq':>6} {'Score':>7}  {'Category'}")
    print("-" * 50)
    for term, freq, score in candidates[:args.top]:
        cat = ""
        if re.search(r"炎|肺|肝|肾|心|脑|胃|肠|血|尿|骨", term):
            cat = "organ/disease"
        elif re.search(r"手术|切除|穿刺|活检|造影|内镜|扫描", term):
            cat = "procedure"
        elif re.search(r"素|酸|碱|酶|蛋白|激素|抗体|因子", term):
            cat = "biochem"
        elif re.search(r"痛|晕|咳|喘|烧|麻|肿|胀|悸", term):
            cat = "symptom"
        print(f"{term:<12} {freq:>6} {score:>7.0f}  {cat}")

    if args.apply:
        apply_to_fast_router(candidates, MAX_TERMS_APPLY)
    else:
        print(f"\nRun with --apply to add top {MAX_TERMS_APPLY} terms to fast_router.py")


if __name__ == "__main__":
    main()
