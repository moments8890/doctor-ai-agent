from __future__ import annotations

import json
from typing import Any, Dict

MAX_TOOL_RESULT_CHARS = 4000  # ~1000 tokens


def truncate_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Truncate large tool results to fit LLM context window."""
    serialized = json.dumps(result, ensure_ascii=False)
    if len(serialized) <= MAX_TOOL_RESULT_CHARS:
        return result
    if "data" in result and isinstance(result["data"], list):
        original_count = len(result["data"])
        result["data"] = result["data"][:5]
        result["truncated"] = True
        result["total_count"] = original_count
    return result
