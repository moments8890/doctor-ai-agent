"""
Mined routing rules for fast_router.

P0: Rules include a ``priority`` field (default 700). After loading, rules are
sorted by priority descending so higher-priority rules are checked first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from . import _keywords
from services.ai.intent import Intent

# ── Mined rules ────────────────────────────────────────────────────────────────
# Rules loaded from an external JSON file produced by scripts/mine_routing_rules.py.
# Each rule is applied BEFORE Tier 3 in fast_route().
# P0: sorted by priority descending after loading.

_MINED_RULES: List[Dict[str, Any]] = []


def load_mined_rules(path: str) -> None:
    """Load mined routing rules from a JSON file.

    The file must be a JSON array of objects with the schema::

        [
          {
            "intent": "add_record",
            "patterns": ["^先记[：:]", "^早班.*记[：:]"],
            "keywords_any": ["先记", "早班记"],
            "min_length": 4,
            "patient_name_group": 1,
            "extra_data": {"source": "mined"},
            "confidence": 0.9,
            "priority": 700,
            "enabled": true
          }
        ]

    Optional fields:
    - ``patient_name_group``: int — regex capture group index to use as patient_name
    - ``extra_data``: dict — static key-value pairs added to IntentResult.extra_data
    - ``confidence``: float — confidence score (default 1.0)
    - ``priority``: int — sort key; higher values are evaluated first (default 700)

    After loading, rules are sorted by ``priority`` descending so that higher-priority
    rules are evaluated before lower-priority ones.

    Silently skips if the file does not exist. Logs errors on malformed content.
    """
    from utils.log import log
    global _MINED_RULES
    p = Path(path)
    if not p.exists():
        return
    try:
        raw: List[Dict[str, Any]] = json.loads(p.read_text(encoding="utf-8"))
        compiled: List[Dict[str, Any]] = []
        for i, rule in enumerate(raw):
            if not isinstance(rule, dict):
                log(f"[mined_rules] rule[{i}] is not a dict, skipping")
                continue
            intent_name = rule.get("intent", "")
            if intent_name not in Intent.__members__:
                log(f"[mined_rules] rule[{i}] unknown intent {intent_name!r}, skipping")
                continue
            try:
                patterns = [re.compile(pat) for pat in rule.get("patterns", [])]
            except re.error as e:
                log(f"[mined_rules] rule[{i}] invalid pattern: {e}, skipping")
                continue
            compiled.append({
                "intent": intent_name,
                "patterns": patterns,
                "keywords_any": list(rule.get("keywords_any") or []),
                "min_length": int(rule.get("min_length", 0)),
                "patient_name_group": rule.get("patient_name_group"),  # int or None
                "extra_data": dict(rule.get("extra_data") or {}),
                "confidence": float(rule.get("confidence", 1.0)),
                "priority": int(rule.get("priority", 700)),
                "enabled": bool(rule.get("enabled", True)),
            })
        _MINED_RULES = sorted(compiled, key=lambda r: r["priority"], reverse=True)
        log(f"[mined_rules] loaded {len(compiled)} rules from {path}")
    except Exception as e:
        log(f"[mined_rules] failed to load {path}: {e}")


def reload_mined_rules(path: str = "data/mined_rules.json") -> int:
    """Hot-reload mined rules from disk.

    Returns the number of rules loaded.
    """
    load_mined_rules(path)
    return len(_MINED_RULES)


# Load rules at module import time (no-op if file absent).
load_mined_rules("data/mined_rules.json")
