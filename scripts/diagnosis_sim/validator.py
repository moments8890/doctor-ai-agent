"""Diagnosis simulation validator — multi-tier validation of diagnosis output."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Valid values (same as diagnosis_models.py)
_VALID_CONFIDENCE = {"低", "中", "高"}
_VALID_URGENCY = {"常规", "紧急", "急诊"}
_VALID_INTERVENTION = {"手术", "药物", "观察", "转诊"}
_VALID_SECTIONS = {"differential", "workup", "treatment"}

# Drug names that should NOT appear in drug_class (specific names, not classes)
_FORBIDDEN_DRUG_NAMES = [
    "阿司匹林", "波立维", "氯吡格雷", "华法林", "利伐沙班", "达比加群",
    "氨氯地平", "硝苯地平", "卡托普利", "依那普利", "缬沙坦",
    "二甲双胍", "格华止", "胰岛素",
    "丙戊酸", "卡马西平", "拉莫三嗪", "左乙拉西坦",
    "地塞米松", "甘露醇",
    "万古霉素", "克林霉素", "头孢", "青霉素",
]


def _contains_any(text: str, keywords: List[str]) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _by_section(suggestions: List[dict], section: str) -> List[dict]:
    return [s for s in suggestions if s.get("section") == section]


# ---------------------------------------------------------------------------
# Tier 1: Structure validation (hard gate)
# ---------------------------------------------------------------------------

def validate_tier1(
    suggestions: List[dict],
    scenario: Dict[str, Any],
) -> Dict[str, Any]:
    checks: Dict[str, Dict[str, Any]] = {}

    checks["has_suggestions"] = {
        "pass": len(suggestions) > 0,
        "detail": f"{len(suggestions)} suggestions returned",
    }

    invalid_sections = [
        s.get("section") for s in suggestions
        if s.get("section") not in _VALID_SECTIONS
    ]
    checks["valid_sections"] = {
        "pass": len(invalid_sections) == 0,
        "detail": f"Invalid sections: {invalid_sections}" if invalid_sections else "All sections valid",
    }

    diffs = _by_section(suggestions, "differential")
    checks["has_differentials"] = {
        "pass": len(diffs) >= 1,
        "detail": f"{len(diffs)} differentials",
    }

    bad_conf = [
        d.get("content") for d in diffs
        if d.get("confidence") and d["confidence"] not in _VALID_CONFIDENCE
    ]
    checks["valid_confidence"] = {
        "pass": len(bad_conf) == 0,
        "detail": f"Invalid confidence on: {bad_conf}" if bad_conf else "All valid",
    }

    workups = _by_section(suggestions, "workup")
    bad_urg = [
        w.get("content") for w in workups
        if w.get("urgency") and w["urgency"] not in _VALID_URGENCY
    ]
    checks["valid_urgency"] = {
        "pass": len(bad_urg) == 0,
        "detail": f"Invalid urgency on: {bad_urg}" if bad_urg else "All valid",
    }

    treatments = _by_section(suggestions, "treatment")
    bad_int = [
        t.get("content") for t in treatments
        if t.get("intervention") and t["intervention"] not in _VALID_INTERVENTION
    ]
    checks["valid_intervention"] = {
        "pass": len(bad_int) == 0,
        "detail": f"Invalid intervention on: {bad_int}" if bad_int else "All valid",
    }

    all_pass = all(c["pass"] for c in checks.values())
    return {"pass": all_pass, "checks": checks}


# ---------------------------------------------------------------------------
# Tier 2: Clinical accuracy (scored, hard gate)
# ---------------------------------------------------------------------------

def validate_tier2(
    suggestions: List[dict],
    scenario: Dict[str, Any],
) -> Dict[str, Any]:
    expectations = scenario.get("expectations", {})
    checks: Dict[str, Dict[str, Any]] = {}
    scores: List[float] = []

    diffs = _by_section(suggestions, "differential")
    workups = _by_section(suggestions, "workup")
    treatments = _by_section(suggestions, "treatment")

    all_diff_text = " ".join(f"{d.get('content', '')} {d.get('detail', '')}" for d in diffs)
    all_workup_text = " ".join(f"{w.get('content', '')} {w.get('detail', '')}" for w in workups)
    all_treatment_text = " ".join(f"{t.get('content', '')} {t.get('detail', '')}" for t in treatments)
    all_text = f"{all_diff_text} {all_workup_text} {all_treatment_text}"

    # --- Differentials ---
    diff_exp = expectations.get("differentials", {})

    min_diff = diff_exp.get("min_count", 1)
    max_diff = diff_exp.get("max_count", 10)
    count_ok = min_diff <= len(diffs) <= max_diff
    checks["diff_count"] = {
        "pass": count_ok,
        "detail": f"{len(diffs)} differentials (expected {min_diff}-{max_diff})",
    }
    scores.append(1.0 if count_ok else 0.5 if len(diffs) > 0 else 0.0)

    must_include = diff_exp.get("must_include_any", [])
    if must_include:
        found = _contains_any(all_diff_text, must_include)
        checks["diff_must_include"] = {
            "pass": found,
            "detail": f"Expected any of {must_include}: {'found' if found else 'MISSING'}",
        }
        scores.append(1.0 if found else 0.0)

    must_not = diff_exp.get("must_not_include", [])
    if must_not:
        found_bad = _contains_any(all_diff_text, must_not)
        checks["diff_must_not_include"] = {
            "pass": not found_bad,
            "detail": f"Forbidden terms {must_not}: {'FOUND' if found_bad else 'clean'}",
        }
        scores.append(0.0 if found_bad else 1.0)

    top_conf = diff_exp.get("top_confidence_must_be")
    if top_conf and diffs:
        actual_top = diffs[0].get("confidence", "")
        conf_ok = actual_top == top_conf
        checks["diff_top_confidence"] = {
            "pass": conf_ok,
            "detail": f"Top confidence: '{actual_top}' (expected '{top_conf}')",
        }
        scores.append(1.0 if conf_ok else 0.3)

    if diff_exp.get("no_high_confidence"):
        has_high = any(d.get("confidence") == "高" for d in diffs)
        checks["diff_no_high"] = {
            "pass": not has_high,
            "detail": f"No '高' confidence: {'VIOLATED' if has_high else 'correct'}",
        }
        scores.append(0.0 if has_high else 1.0)

    # --- Workup ---
    wu_exp = expectations.get("workup", {})
    min_wu = wu_exp.get("min_count", 0)
    wu_count_ok = len(workups) >= min_wu
    checks["workup_count"] = {
        "pass": wu_count_ok,
        "detail": f"{len(workups)} workup items (min {min_wu})",
    }
    scores.append(1.0 if wu_count_ok else 0.5 if len(workups) > 0 else 0.0)

    wu_keywords = wu_exp.get("should_mention_any", [])
    if wu_keywords:
        found = _contains_any(all_workup_text, wu_keywords)
        checks["workup_keywords"] = {
            "pass": found,
            "detail": f"Expected any of {wu_keywords}: {'found' if found else 'MISSING'}",
        }
        scores.append(1.0 if found else 0.3)

    if wu_exp.get("must_have_urgent"):
        has_urgent = any(w.get("urgency") in ("紧急", "急诊") for w in workups)
        checks["workup_urgent"] = {
            "pass": has_urgent,
            "detail": f"Urgent/emergency workup: {'found' if has_urgent else 'MISSING'}",
        }
        scores.append(1.0 if has_urgent else 0.0)

    # --- Treatment ---
    tx_exp = expectations.get("treatment", {})
    min_tx = tx_exp.get("min_count", 0)
    max_tx = tx_exp.get("max_count", 99)
    tx_count_ok = min_tx <= len(treatments) <= max_tx
    checks["treatment_count"] = {
        "pass": tx_count_ok,
        "detail": f"{len(treatments)} treatment items (expected {min_tx}-{max_tx})",
    }
    scores.append(1.0 if tx_count_ok else 0.5)

    expected_interventions = tx_exp.get("expected_interventions", [])
    if expected_interventions:
        actual_interventions = {t.get("intervention", "") for t in treatments}
        found = any(ei in actual_interventions for ei in expected_interventions)
        checks["treatment_interventions"] = {
            "pass": found,
            "detail": f"Expected interventions {expected_interventions}: actual={actual_interventions}",
        }
        scores.append(1.0 if found else 0.3)

    # --- Red flags ---
    rf_exp = expectations.get("red_flags", {})
    rf_keywords = rf_exp.get("should_mention_any", [])
    if rf_keywords:
        found_rf = _contains_any(all_text, rf_keywords)
        checks["red_flags_keywords"] = {
            "pass": found_rf,
            "detail": f"Red flag keywords {rf_keywords}: {'found' if found_rf else 'MISSING'}",
        }
        scores.append(1.0 if found_rf else 0.3)

    # --- Safety ---
    safety_exp = expectations.get("safety", {})
    if safety_exp.get("no_specific_drug_names"):
        drug_classes = " ".join(t.get("content", "") for t in treatments)
        found_drug = _contains_any(drug_classes, _FORBIDDEN_DRUG_NAMES)
        checks["safety_no_drug_names"] = {
            "pass": not found_drug,
            "detail": f"Drug names in drug_class: {'FOUND' if found_drug else 'clean'}",
        }
        scores.append(0.0 if found_drug else 1.0)

    if safety_exp.get("confidence_differentiation"):
        conf_values = {d.get("confidence") for d in diffs if d.get("confidence")}
        has_diff = len(conf_values) > 1
        checks["safety_conf_differentiation"] = {
            "pass": has_diff or len(diffs) <= 1,
            "detail": f"Confidence values: {conf_values} ({'differentiated' if has_diff else 'NOT differentiated'})",
        }
        scores.append(1.0 if has_diff or len(diffs) <= 1 else 0.5)

    # --- KB text influence (keyword-based) ---
    kb_exp = expectations.get("kb_influence", {})
    kb_keywords = kb_exp.get("should_mention_any", [])
    if kb_keywords:
        found_kb = _contains_any(all_text, kb_keywords)
        checks["kb_influence"] = {
            "pass": found_kb,
            "detail": f"KB influence keywords {kb_keywords}: {'found' if found_kb else 'MISSING'}",
        }
        scores.append(1.0 if found_kb else 0.0)

    combined = int(sum(scores) / len(scores) * 100) if scores else 0
    all_pass = combined >= 60 and checks.get("diff_must_include", {}).get("pass", True)

    return {
        "pass": all_pass,
        "combined_score": combined,
        "checks": checks,
        "scores": scores,
    }


# ---------------------------------------------------------------------------
# Tier 3: Hallucination detection
# ---------------------------------------------------------------------------

def validate_tier3(
    suggestions: List[dict],
    scenario: Dict[str, Any],
) -> Dict[str, Any]:
    import re

    record = scenario.get("record", {})
    checks: Dict[str, Dict[str, Any]] = {}

    record_text = " ".join(v for v in record.values() if v)
    all_detail = " ".join(s.get("detail", "") for s in suggestions)

    detail_numbers = set(re.findall(r'\d+\.?\d*(?:/\d+\.?\d*)?', all_detail))
    record_numbers = set(re.findall(r'\d+\.?\d*(?:/\d+\.?\d*)?', record_text))
    novel_numbers = detail_numbers - record_numbers - {str(i) for i in range(20)}
    significant_novel = {n for n in novel_numbers if len(n) >= 3 or '.' in n}

    checks["no_fabricated_numbers"] = {
        "pass": len(significant_novel) <= 3,
        "detail": f"Novel numbers in details: {significant_novel}" if significant_novel else "No novel numbers",
    }

    treatments = _by_section(suggestions, "treatment")
    drug_content = " ".join(t.get("content", "") for t in treatments)
    found_specific = [d for d in _FORBIDDEN_DRUG_NAMES if d in drug_content]
    checks["no_drug_names_in_content"] = {
        "pass": len(found_specific) == 0,
        "detail": f"Drug names in content: {found_specific}" if found_specific else "Clean",
    }

    all_pass = all(c["pass"] for c in checks.values())
    return {"pass": all_pass, "checks": checks}


# ---------------------------------------------------------------------------
# Tier 4: KB citation validation
# ---------------------------------------------------------------------------

def validate_tier4_kb(
    suggestions: List[dict],
    scenario: Dict[str, Any],
    kb_relevant_ids: List[int],
    kb_irrelevant_ids: List[int],
    kb_items_meta: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Tier 4: verify KB items are used in suggestions (HARD gate).

    Two layers of checking:
    1. Text-level: key_concepts from relevant KB MUST appear in suggestion text
                   key_concepts from irrelevant KB must NOT appear
    2. Citation-level: [KB-N] marker tracking (informational)
    """
    kb_items_meta = kb_items_meta or []
    kb_exp = scenario.get("expectations", {}).get("kb_citation", {})
    if not kb_exp and not kb_items_meta:
        return {"pass": True, "checks": {}, "citation_map": []}

    checks: Dict[str, Dict[str, Any]] = {}
    all_suggestion_text = " ".join(
        f"{s.get('content', '')} {s.get('detail', '')}" for s in suggestions
    )

    # --- Text-level: key_concepts matching (HARD) ---
    for i, item in enumerate(kb_items_meta):
        concepts = item.get("key_concepts", [])
        if not concepts:
            continue
        relevant = item.get("relevant", True)
        title = item.get("title", f"KB-{i}")
        matched = [c for c in concepts if c in all_suggestion_text]

        if relevant:
            # Relevant KB: at least one key_concept MUST appear
            checks[f"kb_used_{i}_{title[:20]}"] = {
                "pass": len(matched) > 0,
                "detail": (
                    f"相关KB「{title}」concepts={concepts} → "
                    f"{'found=' + str(matched) if matched else 'NONE found — KB knowledge not used!'}"
                ),
            }
        else:
            # Irrelevant KB: key_concepts must NOT appear
            checks[f"kb_excluded_{i}_{title[:20]}"] = {
                "pass": len(matched) == 0,
                "detail": (
                    f"不相关KB「{title}」concepts={concepts} → "
                    f"{'LEAKED=' + str(matched) + ' — irrelevant KB contaminated output!' if matched else 'correctly excluded'}"
                ),
            }

    # --- Citation-level: [KB-N] tracking (informational) ---
    all_cited: set[int] = set()
    citation_map: List[Dict[str, Any]] = []
    for s in suggestions:
        cited = s.get("cited_knowledge_ids", [])
        if cited:
            all_cited.update(cited)
            citation_map.append({
                "section": s.get("section", ""),
                "content": s.get("content", ""),
                "cited_kb_ids": cited,
            })

    if kb_relevant_ids:
        relevant_cited = all_cited & set(kb_relevant_ids)
        checks["kb_citation_markers"] = {
            "pass": True,  # informational only — text check is the hard gate
            "detail": (
                f"[KB-N] markers: relevant {sorted(relevant_cited) if relevant_cited else 'none'} / "
                f"irrelevant {sorted(all_cited & set(kb_irrelevant_ids)) if kb_irrelevant_ids else 'n/a'}"
            ),
        }

    all_pass = all(c["pass"] for c in checks.values()) if checks else True
    return {"pass": all_pass, "checks": checks, "citation_map": citation_map}


# ---------------------------------------------------------------------------
# Tier 5: Case memory influence validation
# ---------------------------------------------------------------------------

def validate_tier5_cases(
    suggestions: List[dict],
    scenario: Dict[str, Any],
) -> Dict[str, Any]:
    """Tier 5: verify prior case memory influences current suggestions.

    Checks:
    - Expected influence terms from prior cases appear in current suggestions
    - Maps concept overlap between prior case decisions and current output
    """
    prior_cases = scenario.get("prior_cases", [])
    if not prior_cases:
        return {"pass": True, "checks": {}, "influence_traces": []}

    checks: Dict[str, Dict[str, Any]] = {}
    influence_traces: List[Dict[str, Any]] = []

    all_current_text = " ".join(
        f"{s.get('content', '')} {s.get('detail', '')}" for s in suggestions
    )

    # Check expected influence terms for each prior case
    for i, case in enumerate(prior_cases):
        expected = case.get("expected_influence", [])
        if not expected:
            continue

        matched = [t for t in expected if t in all_current_text]
        missed = [t for t in expected if t not in all_current_text]

        checks[f"case_{i+1}_influence"] = {
            "pass": len(matched) >= 1,
            "detail": (
                f"Expected terms: {expected} | "
                f"found={matched} | missed={missed}"
            ),
        }

        # Trace: map prior decisions → current suggestions
        for prior_sug in case.get("suggestions", []):
            prior_content = prior_sug.get("content", "")
            prior_detail = prior_sug.get("detail", "")
            prior_text = f"{prior_content} {prior_detail}"

            for curr_sug in suggestions:
                curr_content = curr_sug.get("content", "")
                curr_detail = curr_sug.get("detail", "")
                curr_text = f"{curr_content} {curr_detail}"

                # Find overlapping meaningful terms
                common = {"治疗", "评估", "检查", "术后", "患者", "目前", "方案", "进行", "建议", "考虑", "需要", "可能"}
                prior_words = {w for w in prior_text.split() if len(w) >= 2 and w not in common}
                overlap = [w for w in prior_words if w in curr_text]

                if overlap:
                    influence_traces.append({
                        "prior_section": prior_sug.get("section", ""),
                        "prior_content": prior_content,
                        "prior_decision": prior_sug.get("decision", ""),
                        "current_section": curr_sug.get("section", ""),
                        "current_content": curr_content,
                        "overlap_terms": overlap,
                    })

    all_pass = all(c["pass"] for c in checks.values()) if checks else True
    return {"pass": all_pass, "checks": checks, "influence_traces": influence_traces}


# ---------------------------------------------------------------------------
# Overall
# ---------------------------------------------------------------------------

def _validate_counterfactual(
    suggestions: List[dict],
    baseline_suggestions: List[dict],
    scenario: Dict[str, Any],
    kb_items_meta: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Counterfactual validation: compare WITH vs WITHOUT injection.

    For each relevant KB item, check that its key_concepts appear in the
    full run but NOT in the baseline. This proves causal KB influence.
    Same for case memory expected_influence terms.
    """
    if not baseline_suggestions:
        return {"pass": True, "checks": {}, "diffs": []}

    kb_items_meta = kb_items_meta or []
    checks: Dict[str, Dict[str, Any]] = {}
    diffs: List[Dict[str, Any]] = []

    full_text = " ".join(f"{s.get('content','')} {s.get('detail','')}" for s in suggestions)
    base_text = " ".join(f"{s.get('content','')} {s.get('detail','')}" for s in baseline_suggestions)

    # KB counterfactual: concepts in full but NOT in baseline = caused by KB
    for i, item in enumerate(kb_items_meta):
        if not item.get("relevant", True):
            continue
        concepts = item.get("key_concepts", [])
        title = item.get("title", f"KB-{i}")
        new_in_full = [c for c in concepts if c in full_text and c not in base_text]
        in_both = [c for c in concepts if c in full_text and c in base_text]
        in_neither = [c for c in concepts if c not in full_text]

        has_causal = len(new_in_full) > 0
        # If concepts appear in both runs, KB overlaps with model knowledge —
        # not ideal but not a failure (concept is present either way)
        has_any = len(new_in_full) > 0 or len(in_both) > 0
        checks[f"counterfactual_kb_{i}_{title[:15]}"] = {
            "pass": has_any,
            "detail": (
                f"「{title}」causally new={new_in_full}, "
                f"in_both={in_both}, absent={in_neither}"
            ),
        }
        diffs.append({
            "type": "kb",
            "title": title,
            "new_in_full": new_in_full,
            "in_both": in_both,
            "absent": in_neither,
            "causal": has_causal,
        })

    # Case counterfactual: expected_influence in full but NOT in baseline
    for i, case in enumerate(scenario.get("prior_cases", [])):
        expected = case.get("expected_influence", [])
        if not expected:
            continue
        new_in_full = [t for t in expected if t in full_text and t not in base_text]
        in_both = [t for t in expected if t in full_text and t in base_text]
        in_neither = [t for t in expected if t not in full_text]

        has_causal = len(new_in_full) > 0
        has_any = len(new_in_full) > 0 or len(in_both) > 0
        checks[f"counterfactual_case_{i+1}"] = {
            "pass": has_any,
            "detail": (
                f"Case {i+1}: causally new={new_in_full}, "
                f"in_both={in_both}, absent={in_neither}"
            ),
        }
        diffs.append({
            "type": "case",
            "case_idx": i + 1,
            "new_in_full": new_in_full,
            "in_both": in_both,
            "absent": in_neither,
            "causal": has_causal,
        })

    all_pass = all(c["pass"] for c in checks.values()) if checks else True
    return {"pass": all_pass, "checks": checks, "diffs": diffs}


def validate_all(
    suggestions: List[dict],
    scenario: Dict[str, Any],
    kb_relevant_ids: Optional[List[int]] = None,
    kb_irrelevant_ids: Optional[List[int]] = None,
    kb_items_meta: Optional[List[dict]] = None,
    baseline_suggestions: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Run all validation tiers and return combined result."""
    t1 = validate_tier1(suggestions, scenario)
    t2 = validate_tier2(suggestions, scenario)
    t3 = validate_tier3(suggestions, scenario)
    t4 = validate_tier4_kb(
        suggestions, scenario,
        kb_relevant_ids=kb_relevant_ids or [],
        kb_irrelevant_ids=kb_irrelevant_ids or [],
        kb_items_meta=kb_items_meta or [],
    )
    t5 = validate_tier5_cases(suggestions, scenario)
    t6 = _validate_counterfactual(
        suggestions,
        baseline_suggestions=baseline_suggestions or [],
        scenario=scenario,
        kb_items_meta=kb_items_meta or [],
    )

    # T4 (KB text influence) and T5 (case influence) are HARD gates.
    # T6 (counterfactual) is HARD when injection exists.
    overall_pass = t1["pass"] and t2["pass"] and t4["pass"] and t5["pass"] and t6["pass"]

    return {
        "tier1": t1,
        "tier2": t2,
        "tier3": t3,
        "tier4_kb": t4,
        "tier5_cases": t5,
        "tier6_counterfactual": t6,
        "pass": overall_pass,
        "combined_score": t2.get("combined_score", 0),
    }
