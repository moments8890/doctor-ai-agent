#!/usr/bin/env python3
"""
生成 realworld_doctor_agent_chatlogs_e2e_v3.json：30个模板×20名患者=600病例。

设计要点：
  - 30个会话模板，覆盖不同操作序列×临床情景组合
  - 更强的断言：每个病例包含 expected_table_min_counts_by_doctor
  - 每个 must_include_any_of 组含5-8个具体临床术语（不含患者名）
  - 可复现：固定随机种子(seed=42)

Generate realworld_doctor_agent_chatlogs_e2e_v3.json (30 templates × 20 patients = 600 cases).
数据和模板构建函数定义在 _generate_v3_builders.py。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tests.fixtures.scripts._generate_v3_builders import (
    CLINICAL_SCENARIOS,
    OPERATION_NAMES,
    TEMPLATE_BUILDERS,
    TEMPLATE_DB_ASSERTIONS,
    TEMPLATE_SCENARIO_MAP,
    generate_patient_pool,
)

import random

ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v3.json"

RNG = random.Random(42)


# ─────────────────────────────────────────────────────────────────────────────
# GENERATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _generate_cases() -> list:
    """Generate all 600 cases using the 30 templates."""
    cases: list = []
    case_num = 0
    print("Generating v3 fixture: 30 templates × 20 patients = 600 cases\n")
    for tmpl_idx in range(1, 31):
        sc_key = TEMPLATE_SCENARIO_MAP[tmpl_idx]
        sc = CLINICAL_SCENARIOS[sc_key]
        builder = TEMPLATE_BUILDERS[tmpl_idx]
        db_assertions = TEMPLATE_DB_ASSERTIONS[tmpl_idx]
        op_name = OPERATION_NAMES[tmpl_idx]
        patient_pool = generate_patient_pool(20, RNG)
        for p_idx, patient in enumerate(patient_pool):
            case_num += 1
            name, gender, age = patient["name"], patient["gender"], patient["age"]
            chatlog = builder(name, gender, age, sc, RNG)
            case_id = f"REALWORLD-V3-{case_num:03d}"
            title = (
                f"V3 {op_name} × {sc['name']} — "
                f"{name} ({gender}/{age}岁) [T{tmpl_idx:02d}P{p_idx+1:02d}]"
            )
            cases.append({
                "case_id": case_id,
                "title": title,
                "template_idx": tmpl_idx,
                "operation_type": op_name,
                "clinical_scenario": sc_key,
                "chatlog": chatlog,
                "expectations": {
                    "must_not_timeout": True,
                    "expected_table_min_counts_global": {},
                    "expected_table_min_counts_by_doctor": db_assertions,
                    "must_include_any_of": [sc["keywords"]],
                },
            })
        print(f"  Template {tmpl_idx:02d} ({op_name} × {sc['name']}): 20 cases generated")
    return cases


def _write_output(cases: list) -> None:
    """Write cases to the output JSON file."""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Generation summary ===")
    print(f"  Total cases generated: {len(cases)}")
    print(f"  Templates: 30  |  Patients per template: 20")
    print(f"  Output: {OUT_PATH}")


def _validate_output(cases: list) -> None:
    """Validate generated cases; raise AssertionError on violations."""
    all_ids = [c["case_id"] for c in cases]
    assert len(all_ids) == len(set(all_ids)), "Duplicate case IDs detected!"
    for c in cases:
        exp = c["expectations"]
        assert exp["must_not_timeout"] is True
        assert "expected_table_min_counts_by_doctor" in exp, f"{c['case_id']} missing db assertion"
        assert "must_include_any_of" in exp, f"{c['case_id']} missing keyword assertion"
        kw_group = exp["must_include_any_of"][0]
        assert len(kw_group) >= 5, f"{c['case_id']} keyword group has <5 terms: {kw_group}"
        assert len(c["chatlog"]) >= 3, f"{c['case_id']} has <3 chatlog turns"
    print("  All validations passed.")
    kw_sizes = [len(c["expectations"]["must_include_any_of"][0]) for c in cases]
    turn_sizes = [len(c["chatlog"]) for c in cases]
    print(f"  Keyword group sizes: min={min(kw_sizes)}, max={max(kw_sizes)}")
    print(f"  Chatlog turn counts: min={min(turn_sizes)}, max={max(turn_sizes)}")


def _print_distributions(cases: list) -> None:
    """Print operation type and clinical scenario distributions."""
    op_dist = Counter(c["operation_type"] for c in cases)
    print(f"\n  Operation type distribution (each should be 20):")
    for op, cnt in sorted(op_dist.items()):
        print(f"    {op}: {cnt}")
    sc_dist = Counter(c["clinical_scenario"] for c in cases)
    print(f"\n  Clinical scenario distribution:")
    for sc_k, cnt in sorted(sc_dist.items()):
        print(f"    {sc_k} ({CLINICAL_SCENARIOS[sc_k]['name']}): {cnt}")


def main() -> None:
    """Entry point: generate, validate, and write the v3 fixture."""
    cases = _generate_cases()
    _write_output(cases)
    _validate_output(cases)
    _print_distributions(cases)


if __name__ == "__main__":
    main()
