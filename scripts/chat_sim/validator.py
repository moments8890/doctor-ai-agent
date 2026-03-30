"""Chat simulation validator — validates intent routing and reply content."""
from __future__ import annotations

from typing import Any, Dict, List


def validate_all(result: dict, scenario: dict) -> Dict[str, Any]:
    exp = scenario.get("expectations", {})
    checks = {}

    # T1: Intent routing
    expected_intent = exp.get("intent", "")
    expected_any = exp.get("intent_any", [])
    actual_intent = result.get("intent", "")

    if expected_any:
        checks["intent"] = {
            "pass": actual_intent in expected_any,
            "detail": f"Expected any of {expected_any}, got '{actual_intent}'",
        }
    elif expected_intent:
        checks["intent"] = {
            "pass": actual_intent == expected_intent,
            "detail": f"Expected '{expected_intent}', got '{actual_intent}'",
        }

    # T2: Reply content
    reply = result.get("reply", "")
    checks["has_reply"] = {
        "pass": len(reply.strip()) > 0,
        "detail": f"Reply: '{reply[:80]}'" if reply else "EMPTY",
    }

    must_mention = exp.get("reply_must_mention", [])
    if must_mention:
        found = [kw for kw in must_mention if kw in reply]
        missed = [kw for kw in must_mention if kw not in reply]
        checks["reply_must_mention"] = {
            "pass": len(found) >= len(must_mention) * 0.5,  # at least half
            "detail": f"Expected {must_mention}: found={found}, missed={missed}",
        }

    must_not = exp.get("reply_must_not_mention", [])
    if must_not:
        leaked = [kw for kw in must_not if kw in reply]
        checks["reply_must_not"] = {
            "pass": len(leaked) == 0,
            "detail": f"Forbidden: {'LEAKED=' + str(leaked) if leaked else 'clean'}",
        }

    all_pass = all(c["pass"] for c in checks.values())
    return {"pass": all_pass, "checks": checks}
