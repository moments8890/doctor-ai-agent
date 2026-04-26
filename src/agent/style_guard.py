"""Style guard — detect hard-block AI-smell phrases in LLM output and
optionally regenerate.

Loads the corpus-validated banned-phrase artifact from
``data/style/anti_smell.json`` (built by ``scripts/build_anti_smell.py``).

Surface latency budgets (per locked plan project_ai_smell_plan_2026-04-25):
- followup_reply:  1 regen on style violation, then ship-with-warning
- patient-interview: 0 regens (latency > polish), detect and log only
- diagnosis: 1-2 regens (async surface)

Safety violations are out of scope here — the prompt-level safety rules
in each intent prompt handle clinical red-flags. This module enforces
*style* only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.log import log

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ARTIFACT_PATH = _REPO_ROOT / "data" / "style" / "anti_smell.json"

_cache: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        if _ARTIFACT_PATH.is_file():
            _cache = json.loads(_ARTIFACT_PATH.read_text(encoding="utf-8"))
        else:
            log(f"[style_guard] anti_smell.json not found at {_ARTIFACT_PATH} — guard disabled", level="warning")
            _cache = {"hard_block": [], "soft_block": []}
    return _cache


def reload() -> None:
    """Force re-read of the artifact (test/dev use)."""
    global _cache
    _cache = None


def detect_hard_violations(text: str) -> List[str]:
    """Return list of hard-block phrases found in *text*."""
    if not text:
        return []
    artifact = _load()
    return [p for p in artifact.get("hard_block", []) if p in text]


_DEFER_PATTERNS = (
    "转给医生",
    "已转给医生",
    "让医生看",
    "让医生先看",
    "医生很快回复",
    "医生会尽快回复",
    "医生马上联系",
    "医生会尽快联系",
    "请先等医生",
    "等医生回复",
)


def detect_defer_to_doctor(text: str) -> bool:
    """True if AI reply uses the defer-to-doctor pattern (locked plan rule 19).

    When this fires, the draft should be marked priority="urgent" (or
    "critical" if after-hours) so the doctor sees it before normal drafts.
    Otherwise the defer pattern is theatre — patient waits silently while
    the draft sits in a generic queue.
    """
    if not text:
        return False
    return any(p in text for p in _DEFER_PATTERNS)


def detect_soft_chain(text: str, threshold: int = 3) -> List[str]:
    """Return soft-block phrases found if ≥ *threshold* co-occur (platitude chain).

    Returns empty list when fewer than *threshold* soft phrases co-occur.
    """
    if not text:
        return []
    artifact = _load()
    found = [p for p in artifact.get("soft_block", []) if p in text]
    return found if len(found) >= threshold else []


def build_correction_message(violations: List[str]) -> Dict[str, str]:
    """Build a corrective system message to nudge regeneration."""
    phrases = "、".join(f'"{p}"' for p in violations[:5])
    return {
        "role": "system",
        "content": (
            f"上一次回复包含禁用短语 {phrases}。这些短语在真实医生回复中"
            f"出现率<0.05%，是 AI 味的标志。请重新输出：直接、口语化、"
            f"像医生发微信。绝不使用这些短语，也不要换成同类客套话。"
        ),
    }


async def llm_call_with_guard(
    *,
    messages: List[Dict[str, str]],
    op_name: str = "llm_call_guarded",
    env_var: str = "ROUTING_LLM",
    temperature: float = 0.3,
    max_tokens: int = 800,
    json_mode: bool = False,
    max_regens: int = 1,
) -> Tuple[str, Dict[str, Any]]:
    """Wrap llm_call with style detection + optional regeneration.

    Returns (final_text, metadata). Metadata keys:
      - initial_violations: list[str] from first call
      - final_violations:   list[str] in returned text (may be non-empty if regens exhausted)
      - regens_used:        int
      - shipped_with_violations: bool — True if final text still violates

    max_regens=0 means detect and log only (no regen). Used for low-latency
    surfaces like patient-interview.
    """
    from agent.llm import llm_call

    text = await llm_call(
        messages=messages,
        op_name=op_name,
        env_var=env_var,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )

    initial = detect_hard_violations(text)
    final = initial
    regens = 0

    while final and regens < max_regens:
        regens += 1
        log(f"[style_guard] {op_name} regen {regens}/{max_regens} due to: {final}")
        corrected = list(messages) + [
            {"role": "assistant", "content": text},
            build_correction_message(final),
        ]
        text = await llm_call(
            messages=corrected,
            op_name=f"{op_name}_regen{regens}",
            env_var=env_var,
            temperature=max(0.1, temperature * 0.7),
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        final = detect_hard_violations(text)

    if final and max_regens > 0:
        log(f"[style_guard] {op_name} shipped with {len(final)} violations after {regens} regens: {final}", level="warning")
    elif initial and max_regens == 0:
        log(f"[style_guard] {op_name} detected (no regen) {len(initial)} violations: {initial}")

    return text, {
        "initial_violations": initial,
        "final_violations": final,
        "regens_used": regens,
        "shipped_with_violations": bool(final),
    }
