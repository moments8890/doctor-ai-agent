"""Reply simulation validator — validates triage, reply content, KB usage."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(kw in text for kw in keywords)


# ---------------------------------------------------------------------------
# T1: Triage classification
# ---------------------------------------------------------------------------

def validate_triage(result: dict, scenario: dict) -> Dict[str, Any]:
    """Check triage category and ai_handled match expectations."""
    exp = scenario.get("expectations", {})
    checks = {}

    expected_cat = exp.get("triage_category", "")
    expected_any = exp.get("triage_category_any", [])
    actual_cat = result.get("triage_category", "")
    if expected_any:
        cat_ok = actual_cat in expected_any
        checks["triage_category"] = {
            "pass": cat_ok,
            "detail": f"Expected any of {expected_any}, got '{actual_cat}'",
        }
    elif expected_cat:
        checks["triage_category"] = {
            "pass": actual_cat == expected_cat,
            "detail": f"Expected '{expected_cat}', got '{actual_cat}'",
        }

    expected_handled = exp.get("ai_handled")
    actual_handled = result.get("ai_handled")
    if expected_handled is not None:
        checks["ai_handled"] = {
            "pass": actual_handled == expected_handled,
            "detail": f"Expected ai_handled={expected_handled}, got {actual_handled}",
        }

    all_pass = all(c["pass"] for c in checks.values())
    return {"pass": all_pass, "checks": checks}


# ---------------------------------------------------------------------------
# T2: Reply content
# ---------------------------------------------------------------------------

def validate_reply(result: dict, scenario: dict) -> Dict[str, Any]:
    """Check reply content: must-mention, must-not-mention, length."""
    exp = scenario.get("expectations", {})
    checks = {}
    reply = result.get("reply", "")

    must_mention = exp.get("reply_must_mention", [])
    if must_mention:
        found = [kw for kw in must_mention if kw in reply]
        missed = [kw for kw in must_mention if kw not in reply]
        checks["reply_must_mention"] = {
            "pass": len(found) > 0,
            "detail": f"Expected any of {must_mention}: found={found}, missed={missed}",
        }

    must_not = exp.get("reply_must_not_mention", [])
    if must_not:
        leaked = [kw for kw in must_not if kw in reply]
        checks["reply_must_not_mention"] = {
            "pass": len(leaked) == 0,
            "detail": f"Forbidden {must_not}: {'LEAKED=' + str(leaked) if leaked else 'clean'}",
        }

    max_len = exp.get("max_reply_length", 200)
    checks["reply_length"] = {
        "pass": len(reply) <= max_len,
        "detail": f"{len(reply)} chars (max {max_len})",
    }

    has_reply = len(reply.strip()) > 0
    checks["has_reply"] = {
        "pass": has_reply,
        "detail": f"Reply: '{reply[:80]}'" if has_reply else "EMPTY reply",
    }

    all_pass = all(c["pass"] for c in checks.values())
    return {"pass": all_pass, "checks": checks}


# ---------------------------------------------------------------------------
# T3: KB citation (for scenarios with KB)
# ---------------------------------------------------------------------------

def validate_kb(result: dict, scenario: dict) -> Dict[str, Any]:
    """Check KB concepts appear in reply, irrelevant KB excluded.

    Only checks relevant KB concepts when ai_handled=true (informational).
    When escalated, KB is not in the reply — only check irrelevant exclusion.
    """
    kb_items = scenario.get("knowledge_items", [])
    kb_exp = scenario.get("expectations", {}).get("kb_citation", {})
    if not kb_items or not kb_exp:
        return {"pass": True, "checks": {}}

    checks = {}
    reply = result.get("reply", "")
    ai_handled = result.get("ai_handled", False)

    for i, item in enumerate(kb_items):
        concepts = item.get("key_concepts", [])
        relevant = item.get("relevant", True)
        title = item.get("title", f"KB-{i}")
        matched = [c for c in concepts if c in reply]

        if relevant:
            if ai_handled:
                # Only assert KB used when AI auto-replied (informational)
                checks[f"kb_used_{title[:20]}"] = {
                    "pass": len(matched) > 0,
                    "detail": f"相关KB「{title}」concepts={concepts} → {'found=' + str(matched) if matched else 'NONE'}",
                }
            else:
                # Escalated — KB not in reply, just note it
                checks[f"kb_skipped_{title[:20]}"] = {
                    "pass": True,
                    "detail": f"相关KB「{title}」— 已升级给医生，KB 将用于草稿生成",
                }
        elif not relevant:
            checks[f"kb_excluded_{title[:20]}"] = {
                "pass": len(matched) == 0,
                "detail": f"不相关KB「{title}」concepts={concepts} → {'LEAKED=' + str(matched) if matched else 'excluded'}",
            }

    all_pass = all(c["pass"] for c in checks.values())
    return {"pass": all_pass, "checks": checks}


# ---------------------------------------------------------------------------
# Overall
# ---------------------------------------------------------------------------

def validate_all(result: dict, scenario: dict) -> Dict[str, Any]:
    t1 = validate_triage(result, scenario)
    t2 = validate_reply(result, scenario)
    t3 = validate_kb(result, scenario)

    # Triage is the hard gate — if classification is wrong, everything is wrong
    overall = t1["pass"] and t2["pass"] and t3["pass"]

    return {
        "tier1_triage": t1,
        "tier2_reply": t2,
        "tier3_kb": t3,
        "pass": overall,
    }
