"""
结构化轮次日志：将每次路由决策写入 JSONL 文件，供离线规则挖掘使用。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_ENABLED = os.environ.get("TURN_LOG_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
_LOG_FILE = Path(os.environ.get("TURN_LOG_FILE", "logs/turn_log.jsonl"))
_TTL_DAYS = int(os.environ.get("TURN_LOG_TTL_DAYS", "30"))


def _is_test() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def prune_turn_log() -> int:
    """Remove entries older than TURN_LOG_TTL_DAYS from the turn log.

    Returns the number of lines kept.
    """
    if not _LOG_FILE.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=_TTL_DAYS)
    kept: list[str] = []
    try:
        for line in _LOG_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                ts_str = row.get("ts", "")
                # Parse ISO 8601 with Z suffix
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts >= cutoff:
                    kept.append(json.dumps(row, ensure_ascii=False))
            except Exception:
                # Drop malformed lines — they cannot be dated and would
                # accumulate indefinitely.
                pass
        _LOG_FILE.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    except Exception:
        pass

    return len(kept)
