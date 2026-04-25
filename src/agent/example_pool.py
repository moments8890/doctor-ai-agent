"""Example pool — keyword-routed retrieval of complaint-clustered exemplars.

Loads the curated pool from ``data/style/example_pool.json`` (built by
``scripts/build_example_pool.py``). At runtime, given a patient message,
picks the primary complaint cluster + at most one secondary cluster
(per Codex round-2: never 3-way union — too much exemplar anchoring).

Returns deterministic top-ranked examples (per Codex round-2 correction:
NOT random sampling — random injects style instability).

Usage:
    from agent.example_pool import select_examples
    exs = select_examples("肚子疼三天了", k=3)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.log import log

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_POOL_PATH = _REPO_ROOT / "data" / "style" / "example_pool.json"

_cache: Optional[Dict[str, Any]] = None

# Mirror of COMPLAINT_CLUSTERS in scripts/build_example_pool.py.
# Keep in sync — drives runtime routing.
_COMPLAINT_KEYWORDS: Dict[str, List[str]] = {
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


def _load_pool() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        if _POOL_PATH.is_file():
            _cache = json.loads(_POOL_PATH.read_text(encoding="utf-8"))
        else:
            log(f"[example_pool] not found at {_POOL_PATH} — L5 disabled", level="warning")
            _cache = {"clusters": {}}
    return _cache


def reload() -> None:
    """Force re-read of the artifact (test/dev)."""
    global _cache
    _cache = None


def _score_clusters(text: str) -> List[tuple[str, int]]:
    """Return [(cluster, hit_count)] sorted by hit_count desc."""
    if not text:
        return []
    scored = []
    for cluster, keywords in _COMPLAINT_KEYWORDS.items():
        hits = sum(1 for k in keywords if k in text)
        if hits > 0:
            scored.append((cluster, hits))
    scored.sort(key=lambda x: (-x[1], x[0]))  # most hits first, then alphabetical
    return scored


def select_examples(
    patient_text: str,
    k: int = 3,
    min_hits: int = 1,
) -> List[Dict[str, Any]]:
    """Pick deterministic top-ranked examples for the patient's complaint.

    Returns up to *k* examples drawn from:
    - primary cluster (most keyword hits)
    - one secondary cluster if patient is multi-complaint (per Codex round-2)

    If no cluster matches with >= *min_hits* keyword hits, returns []
    (per Codex round-1: better zero examples than wrong-cluster anchoring).
    """
    if not patient_text or k <= 0:
        return []
    pool = _load_pool()
    clusters = pool.get("clusters", {})
    if not clusters:
        return []

    scored = _score_clusters(patient_text)
    if not scored or scored[0][1] < min_hits:
        log(f"[example_pool] no cluster match for: {patient_text[:60]!r}")
        return []

    primary = scored[0][0]
    secondary = scored[1][0] if len(scored) > 1 and scored[1][1] >= 2 else None

    out: List[Dict[str, Any]] = []
    if secondary:
        n_primary = max(1, k - 1)
        n_secondary = k - n_primary
        out.extend(clusters.get(primary, [])[:n_primary])
        out.extend(clusters.get(secondary, [])[:n_secondary])
        log(f"[example_pool] picked {len(out)} examples: primary={primary}({n_primary}) + secondary={secondary}({n_secondary})")
    else:
        out.extend(clusters.get(primary, [])[:k])
        log(f"[example_pool] picked {len(out)} examples: cluster={primary}")

    return out


def format_examples_block(examples: List[Dict[str, Any]]) -> str:
    """Format examples as a prompt block for L5 injection."""
    if not examples:
        return ""
    lines = ["以下是来自真实医生的回复示例（参考语气、长度、用词，不要照搬内容）："]
    for i, ex in enumerate(examples, 1):
        lines.append(f"")
        lines.append(f"示例{i}:")
        lines.append(f"患者：{ex.get('patient', '')[:200]}")
        lines.append(f"医生：{ex.get('doctor', '')[:200]}")
    return "\n".join(lines)
