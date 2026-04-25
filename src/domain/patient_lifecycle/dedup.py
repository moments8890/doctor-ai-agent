"""Dedup detection — chief_complaint similarity AND episode-boundary signals.

Spec §5a. The hard rule: same complaint text after a doctor decision or
status advance is by definition a NEW clinical episode, never a
duplicate. Episode signals override similarity even at very high scores.

Three bands by similarity (when episode signals are clear):
  similarity >= 0.7    → auto_merge   (append-only merge into existing record)
  0.5 <= similarity < 0.7 → patient_prompt (ask the patient before merging)
  similarity < 0.5     → none          (treat as new record)

Why episode signals trump similarity: a patient saying "头痛" the day
after their doctor prescribed treatment for "头痛" might actually be
reporting a side effect, a worsening, or an unrelated new headache.
Auto-merging would silently destroy clinical context. Forcing a new
record preserves the timeline and lets the doctor decide whether to
link them later.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# Band thresholds — see spec §5a.
LOWER_BOUND = 0.5
UPPER_BOUND = 0.7

# Within this many hours, similarity-driven dedup is considered. Past
# this gap, every complaint is a new episode regardless of text match.
WITHIN_HOURS = 24


@dataclass
class EpisodeSignals:
    """Boundary indicators that override similarity.

    `treatment_event_since_last`: the doctor has prescribed / scheduled /
        intervened on this complaint since the target record landed.
    `status_change_since_last`: the target record advanced through any
        status transition (e.g. interview_active → pending_review →
        completed) since it last received a field update.
    """
    hours_since_last: float
    treatment_event_since_last: bool
    status_change_since_last: bool


@dataclass
class DedupDecision:
    same_episode: bool
    band: Literal["auto_merge", "patient_prompt", "none"]
    similarity: float


async def detect_same_episode(
    draft_complaint: str,
    target_complaint: str,
    signals: EpisodeSignals,
) -> DedupDecision:
    """Return a dedup decision for a draft complaint vs a target record.

    Episode signals are checked first — they short-circuit the
    similarity check. Only when signals are clear do we compare text.
    """
    similarity = await _llm_chief_complaint_similarity(draft_complaint, target_complaint)

    # Episode-boundary signals override similarity. Same text after
    # treatment / status change / >24h gap = new episode.
    if signals.hours_since_last > WITHIN_HOURS:
        return DedupDecision(same_episode=False, band="none", similarity=similarity)
    if signals.treatment_event_since_last or signals.status_change_since_last:
        return DedupDecision(same_episode=False, band="none", similarity=similarity)

    if similarity >= UPPER_BOUND:
        return DedupDecision(same_episode=True, band="auto_merge", similarity=similarity)
    if similarity >= LOWER_BOUND:
        return DedupDecision(same_episode=True, band="patient_prompt", similarity=similarity)
    return DedupDecision(same_episode=False, band="none", similarity=similarity)


async def _llm_chief_complaint_similarity(a: str, b: str) -> float:
    """One-shot LLM similarity score in [0.0, 1.0].

    Tight prompt — no clinical reasoning, just text equivalence ("are
    these two complaints describing the same thing?"). Returns 0.0 on
    any LLM error so callers don't wedge on transient failures; that
    falls through to the "none" band, which means "treat as new
    record" — the safe default.
    """
    from pydantic import BaseModel, Field

    from agent.llm import structured_call

    class _SimResp(BaseModel):
        similarity: float = Field(ge=0.0, le=1.0)

    messages = [
        {
            "role": "system",
            "content": (
                "你判断两段中文主诉文本是否在描述同一个临床问题。"
                "只输出 JSON，结构: {\"similarity\": 0.0-1.0}。"
                "不做诊断，不做推理，只比较文本含义。"
            ),
        },
        {"role": "user", "content": f"A: {a}\nB: {b}"},
    ]

    try:
        result = await structured_call(
            response_model=_SimResp,
            messages=messages,
            op_name="dedup.similarity",
            env_var="DEDUP_LLM",
            temperature=0.0,
            max_tokens=40,
            max_retries=1,
        )
        return float(result.similarity)
    except Exception:
        return 0.0
