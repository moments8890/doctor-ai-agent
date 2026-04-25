"""Dedup detection AND append-only merge.

Two responsibilities, one module:

  - detect_same_episode()   §5a — decide whether a draft is the same
                                  clinical episode as a target record
  - merge_into_existing()   §5b — append new field entries onto a target
                                  record without ever mutating prior ones

Append-only is the key safety property: clinical work product is never
silently overwritten. The doctor view collapses the per-segment
timestamps + intake_segment_ids into a readable timeline.

Original docstring follows.

----

Dedup detection — chief_complaint similarity AND episode-boundary signals.

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


# ── Append-only merge (§5b common case) ────────────────────────────


# The 7 history fields tracked in FieldEntryDB. Same constant as
# extraction_confidence.REQUIRED_FIELDS — kept local so dedup.py
# doesn't reach across modules for it.
# Public alias used by supplement_handlers for field-name whitelist check.
REQUIRED_FIELDS = _REQUIRED_FIELDS = (
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "personal_history",
    "marital_reproductive",
    "family_history",
)


async def merge_into_existing(
    session,
    target_record_id: int,
    new_fields: dict,
    intake_segment_id: str | None,
) -> None:
    """Append new field entries onto an existing record. Never mutate prior.

    Logic:
      - For each history field, append a FieldEntryDB row if the new
        text is non-empty.
      - For chief_complaint specifically, skip if the same text already
        exists for this record (dedup the dedup signal — there's no
        point in stamping "头痛" 5 times).
      - Provenance via intake_segment_id so the doctor view can group
        entries by segment.
    """
    from datetime import datetime

    from sqlalchemy import select

    from db.models.records import FieldEntryDB

    # Pull existing chief_complaint texts to dedup against.
    existing_chief = (
        await session.execute(
            select(FieldEntryDB.text).where(
                FieldEntryDB.record_id == target_record_id,
                FieldEntryDB.field_name == "chief_complaint",
            )
        )
    ).scalars().all()

    now = datetime.utcnow()
    for field in _REQUIRED_FIELDS:
        text = new_fields.get(field)
        if text is None or not str(text).strip():
            continue
        if field == "chief_complaint" and text in existing_chief:
            continue
        session.add(
            FieldEntryDB(
                record_id=target_record_id,
                field_name=field,
                text=text,
                intake_segment_id=intake_segment_id,
                created_at=now,
            )
        )
    await session.flush()


# ── Supplement for doctor-reviewed records (§5c) ────────────────────


async def create_supplement(
    session,
    target_record_id: int,
    new_fields: dict,
    intake_segment_id: str | None,
):
    """Create a pending supplement for a doctor-reviewed record.

    Never mutates FieldEntryDB on the target record. The supplement row
    carries the new field entries as a JSON blob; the doctor explicitly
    accepts (merges into the record), rejects-create-new, or ignores.
    """
    import json as _json
    from datetime import datetime as _datetime

    from db.models.records import RecordSupplementDB

    now = _datetime.utcnow()
    entries = []
    for field in _REQUIRED_FIELDS:
        text = new_fields.get(field)
        if text is None or not str(text).strip():
            continue
        entries.append({
            "field_name": field,
            "text": text,
            "intake_segment_id": intake_segment_id,
            "created_at": now.isoformat(),
        })
    sup = RecordSupplementDB(
        record_id=target_record_id,
        status="pending_doctor_review",
        field_entries_json=_json.dumps(entries),
        created_at=now,
    )
    session.add(sup)
    await session.flush()
    return sup
