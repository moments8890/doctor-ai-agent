#!/usr/bin/env python3
"""
生成 realworld_doctor_agent_chatlogs_e2e_v2.json：将基础 100 个病例扩展至 1000 个（10倍）。

新增 10 种临床场景（每种 90 例）：
  A - 脑卒中 / 神经科       F - 呼吸科 / 肺科
  B - 出院小结              G - 心律失常管理
  C - 糖尿病 + 高血压慢病   H - 脓毒症 / 重症监护
  D - 术后随访              I - CKD / 肾科
  E - 肿瘤 / 化疗追踪       J - 精神心理

模板函数定义在同目录的 _generate_v2_templates_af.py 和 _generate_v2_templates_gj.py。
共享短语库在 _generate_v2_phrase_bank.py。

Expand realworld_doctor_agent_chatlogs_e2e_v2.json from 100 → 1000 cases (10x).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from tests.fixtures.scripts._generate_v2_phrase_bank import gen_unique_names
from tests.fixtures.scripts._generate_v2_templates_af import (
    tmpl_stroke,
    tmpl_discharge,
    tmpl_chronic,
    tmpl_postop,
    tmpl_oncology,
    tmpl_respiratory,
)
from tests.fixtures.scripts._generate_v2_templates_gj import (
    tmpl_arrhythmia,
    tmpl_sepsis,
    tmpl_renal,
    tmpl_mental,
)

ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = (
    ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v2.json"
)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — regenerate V2-101..1000 in-place
# ═══════════════════════════════════════════════════════════════════════════════
_TEMPLATES = [
    tmpl_stroke,
    tmpl_discharge,
    tmpl_chronic,
    tmpl_postop,
    tmpl_oncology,
    tmpl_respiratory,
    tmpl_arrhythmia,
    tmpl_sepsis,
    tmpl_renal,
    tmpl_mental,
]


def _generate_new_cases(original: list[dict], rng: random.Random, target: int) -> list[dict]:
    """Generate expanded cases using round-robin templates."""
    new_count = target - len(original)
    names = gen_unique_names(new_count, rng)
    new_cases: list[dict] = []
    for i, name in enumerate(names):
        case_num = len(original) + 1 + i
        tmpl_fn = _TEMPLATES[i % len(_TEMPLATES)]
        new_cases.append(tmpl_fn(name, case_num, rng))
    return new_cases


def _validate_cases(new_cases: list[dict]) -> None:
    """Validate generated cases; raise SystemExit on any violations."""
    errors = []
    for c in new_cases:
        chatlog = c.get("chatlog", [])
        doc_turns = [x for x in chatlog if x.get("speaker") == "doctor"]
        if len(chatlog) < 4:
            errors.append(f"{c['case_id']}: only {len(chatlog)} turns")
        if len(doc_turns) < 3:
            errors.append(f"{c['case_id']}: only {len(doc_turns)} doctor turns")
        if not c.get("expectations", {}).get("must_not_timeout"):
            errors.append(f"{c['case_id']}: missing must_not_timeout")
    if errors:
        print(f"VALIDATION ERRORS ({len(errors)}):")
        for e in errors[:10]:
            print(f"  {e}")
        raise SystemExit(1)


def _print_stats(new_cases: list[dict]) -> None:
    """Print turn-length and scenario distribution stats."""
    from collections import Counter
    turn_dist = Counter(len(c["chatlog"]) for c in new_cases)
    print("Turn-length distribution (new cases):")
    for k in sorted(turn_dist):
        print(f"  {k} turns: {turn_dist[k]}")
    kw_dist: dict[str, int] = {}
    for c in new_cases:
        k = c["expectations"]["must_include_any_of"][0][0]
        kw_dist[k] = kw_dist.get(k, 0) + 1
    print("Scenario distribution:")
    for k, v in sorted(kw_dist.items()):
        print(f"  {k}: {v}")


def main() -> None:
    data: list[dict] = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    original = [c for c in data if int(c["case_id"].split("-")[-1]) <= 100]
    assert len(original) == 100, f"Expected 100 original cases, found {len(original)}"
    print(f"Original cases kept: {len(original)}")

    rng = random.Random(42)
    target = 1000
    new_cases = _generate_new_cases(original, rng, target)
    result = original + new_cases
    assert len(result) == target

    _validate_cases(new_cases)
    DATA_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(result)} total cases ({len(new_cases)} new).")
    _print_stats(new_cases)


if __name__ == "__main__":
    main()
