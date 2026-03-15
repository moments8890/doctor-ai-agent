#!/usr/bin/env python3
"""
断言补丁工具 — 原地修补 realworld_doctor_agent_chatlogs_e2e_v2.json 的断言字段。

patch_v2_assertions.py — Patch realworld_doctor_agent_chatlogs_e2e_v2.json in-place.

Patches applied:
  A. Add expected_table_min_counts_by_doctor to ALL cases
  B. Fix 10 zero-assertion duplicate-name/delete cases (add must_include_any_of)
  C. Fix CORRECTION-* cases with stronger must_include_any_of per corrected value
  D. (V2-101..1000) Clinical keywords are already decent; ensure 5+ terms per group

Backs up original to .bak before overwriting.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v2.json"
BAK_PATH = DATA_PATH.with_suffix(".json.bak")

# ─── Correction case patch map ────────────────────────────────────────────────
# Maps case_id → (must_include_any_of, must_not_include or None)
CORRECTION_PATCHES: dict[str, dict] = {
    "REALWORLD-V2-CORRECTION-001": {
        "must_include_any_of": [["女", "性别", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-002": {
        "must_include_any_of": [["54", "年龄", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-003": {
        "must_include_any_of": [["胸痛", "更正", "主诉"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-004": {
        "must_include_any_of": [["170", "更正", "血压"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-005": {
        "must_include_any_of": [["恶心", "发热", "畏光", "38.5"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-006": {
        "must_include_any_of": [["氯吡格雷", "更正", "用药"]],
        "must_not_include": ["阿司匹林"],
    },
    "REALWORLD-V2-CORRECTION-007": {
        "must_include_any_of": [["2100", "BNP", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-008": {
        "must_include_any_of": [["2周", "咳嗽", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-009": {
        "must_include_any_of": [["家族史", "冠心病", "父亲"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-010": {
        "must_include_any_of": [["16U", "胰岛素", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-011": {
        "must_include_any_of": [["STEMI", "明确", "PCI"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-012": {
        "must_include_any_of": [["青霉素", "过敏", "头孢"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-013": {
        "must_include_any_of": [["王明", "更正", "姓名"]],
        "must_not_include": ["王铭"],
    },
    "REALWORLD-V2-CORRECTION-014": {
        "must_include_any_of": [["气短", "更正", "主诉"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-015": {
        "must_include_any_of": [["女", "43", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-016": {
        "must_include_any_of": [["10", "NIHSS", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-017": {
        "must_include_any_of": [["CABG", "手术", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-018": {
        "must_include_any_of": [["8.1", "HbA1c", "更正"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-019": {
        "must_include_any_of": [["416", "肌酐", "eGFR", "CKD"]],
        "must_not_include": None,
    },
    "REALWORLD-V2-CORRECTION-020": {
        "must_include_any_of": [["室上性", "更正", "心动过速"]],
        "must_not_include": ["室性早搏"],
    },
}

# Duplicate-name/delete template cases (zero assertions)
DUPLICATE_DELETE_IDS = {
    "REALWORLD-V2-003",
    "REALWORLD-V2-013",
    "REALWORLD-V2-023",
    "REALWORLD-V2-033",
    "REALWORLD-V2-043",
    "REALWORLD-V2-053",
    "REALWORLD-V2-063",
    "REALWORLD-V2-073",
    "REALWORLD-V2-083",
    "REALWORLD-V2-093",
}

# Keywords for the duplicate-delete scenario
DUPLICATE_DELETE_KEYWORDS = [["删除", "创建", "心悸", "确认", "已删"]]


def _parse_case_number(case_id: str) -> int | None:
    """Return the numeric suffix of a REALWORLD-V2-NNN case_id, or None."""
    parts = case_id.split("-")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return None


def _is_correction_case(case_id: str) -> bool:
    return "CORRECTION" in case_id


def _is_main_case_range(num: int | None) -> bool:
    """Return True for V2-001..100 (first 100 non-correction cases)."""
    return num is not None and 1 <= num <= 100


def _is_clinical_case_range(num: int | None) -> bool:
    """Return True for V2-101..1000."""
    return num is not None and 101 <= num <= 1000


def _patch_table_counts(exp: dict, case_id: str, num) -> None:
    """补丁A：为缺少 expected_table_min_counts_by_doctor 的案例填充默认值。"""
    if "expected_table_min_counts_by_doctor" in exp:
        return
    is_dup = case_id in DUPLICATE_DELETE_IDS
    if is_dup:
        exp["expected_table_min_counts_by_doctor"] = {"patients": 1}
    elif _is_correction_case(case_id) or _is_main_case_range(num) or _is_clinical_case_range(num):
        exp["expected_table_min_counts_by_doctor"] = {"patients": 1, "medical_records": 1}


def _patch_duplicate_delete(exp: dict, case_id: str) -> None:
    """补丁B：为零断言的重复创建/删除案例添加 must_include_any_of。"""
    if case_id in DUPLICATE_DELETE_IDS and "must_include_any_of" not in exp:
        exp["must_include_any_of"] = DUPLICATE_DELETE_KEYWORDS


def _patch_correction(exp: dict, case_id: str) -> None:
    """补丁C：为更正案例强制设置精确的 must_include_any_of/must_not_include。"""
    if _is_correction_case(case_id) and case_id in CORRECTION_PATCHES:
        patch_info = CORRECTION_PATCHES[case_id]
        exp["must_include_any_of"] = patch_info["must_include_any_of"]
        if patch_info.get("must_not_include"):
            exp["must_not_include"] = patch_info["must_not_include"]


def patch_case(case: dict) -> dict:
    """对单个案例字典应用所有补丁，返回修改后的案例。"""
    case_id: str = case["case_id"]
    exp: dict = case["expectations"]
    num = _parse_case_number(case_id)
    _patch_table_counts(exp, case_id, num)
    _patch_duplicate_delete(exp, case_id)
    _patch_correction(exp, case_id)
    # Patch D: clinical 101-1000 keywords already ≥5 terms; no-op validation.
    return case


def _apply_all_patches(data: list) -> tuple:
    """对列表中所有案例应用补丁，返回 (patched_db, patched_keywords, patched_mni) 计数。"""
    patched_db = patched_kw = patched_mni = 0
    for i, case in enumerate(data):
        before_keys = set(case["expectations"].keys())
        before_mia = case["expectations"].get("must_include_any_of")
        data[i] = patch_case(case)
        after_keys = set(data[i]["expectations"].keys())
        after_mia = data[i]["expectations"].get("must_include_any_of")
        if "expected_table_min_counts_by_doctor" in after_keys - before_keys:
            patched_db += 1
        if before_mia != after_mia:
            patched_kw += 1
        if "must_not_include" in after_keys - before_keys:
            patched_mni += 1
    return patched_db, patched_kw, patched_mni


def _print_patch_summary(data: list, original_count: int,
                         patched_db: int, patched_kw: int, patched_mni: int) -> None:
    """打印补丁摘要并验证剩余违规案例。"""
    print()
    print("=== Patch summary ===")
    print(f"  Total cases:                         {len(data)}")
    print(f"  Cases unchanged:                     {original_count}")
    print(f"  [A] Added expected_table_min_counts_by_doctor: {patched_db}")
    print(f"  [B/C] Updated must_include_any_of:   {patched_kw}")
    print(f"  [C] Added must_not_include:           {patched_mni}")
    print()
    still_zero = [
        c["case_id"] for c in data
        if "must_include_any_of" not in c["expectations"] and "CORRECTION" not in c["case_id"]
    ]
    if still_zero:
        print(f"WARNING: {len(still_zero)} non-correction cases still lack must_include_any_of:")
        for cid in still_zero[:10]:
            print(f"    {cid}")
    else:
        print("All non-correction cases now have must_include_any_of.")
    missing_by_doctor = [
        c["case_id"] for c in data
        if "expected_table_min_counts_by_doctor" not in c["expectations"]
    ]
    if missing_by_doctor:
        print(f"WARNING: {len(missing_by_doctor)} cases still lack expected_table_min_counts_by_doctor:")
        for cid in missing_by_doctor[:10]:
            print(f"    {cid}")
    else:
        print("All cases now have expected_table_min_counts_by_doctor.")
    print()
    print(f"Output written to {DATA_PATH}")


def main() -> None:
    """命令行主入口：加载、备份、补丁、写回并打印摘要。"""
    raw = DATA_PATH.read_text(encoding="utf-8")
    data: list = json.loads(raw)
    original_count = len(data)
    print(f"Loaded {original_count} cases from {DATA_PATH.name}")
    shutil.copy2(DATA_PATH, BAK_PATH)
    print(f"Backup written to {BAK_PATH.name}")
    patched_db, patched_kw, patched_mni = _apply_all_patches(data)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_patch_summary(data, original_count, patched_db, patched_kw, patched_mni)


if __name__ == "__main__":
    main()
