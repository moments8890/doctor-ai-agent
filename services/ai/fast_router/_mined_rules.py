"""
挖掘路由规则加载器：从 JSON 文件加载数据挖掘得出的意图路由规则。

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


def _compile_single_rule(
    i: int, rule: Dict[str, Any], log_fn
) -> Optional[Dict[str, Any]]:
    """编译单条路由规则；格式错误时记录日志并返回 None。"""
    if not isinstance(rule, dict):
        log_fn(f"[mined_rules] rule[{i}] is not a dict, skipping")
        return None
    intent_name = rule.get("intent", "")
    if intent_name not in Intent.__members__:
        log_fn(f"[mined_rules] rule[{i}] unknown intent {intent_name!r}, skipping")
        return None
    try:
        patterns = [re.compile(pat) for pat in rule.get("patterns", [])]
    except re.error as e:
        log_fn(f"[mined_rules] rule[{i}] invalid pattern: {e}, skipping")
        return None
    return {
        "intent": intent_name,
        "patterns": patterns,
        "keywords_any": list(rule.get("keywords_any") or []),
        "min_length": int(rule.get("min_length", 0)),
        "patient_name_group": rule.get("patient_name_group"),
        "extra_data": dict(rule.get("extra_data") or {}),
        "confidence": float(rule.get("confidence", 1.0)),
        "priority": int(rule.get("priority", 700)),
        "enabled": bool(rule.get("enabled", True)),
    }


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

    Silently skips if the file does not exist. Logs errors on malformed content.
    """
    from utils.log import log
    global _MINED_RULES
    p = Path(path)
    if not p.exists():
        return
    try:
        raw: List[Dict[str, Any]] = json.loads(p.read_text(encoding="utf-8"))
        compiled = [
            r for i, rule in enumerate(raw)
            if (r := _compile_single_rule(i, rule, log)) is not None
        ]
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
