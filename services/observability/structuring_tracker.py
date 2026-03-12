"""Structuring accuracy tracker — source attribution and edit-distance metrics.

Tracks the quality of LLM-generated structured records by:

1. **Source attribution** — tagging each field with its information source
   (doctor's words, LLM inference, knowledge base, skill rules).
2. **Edit tracking** — when a doctor corrects a structured record, computing
   the diff ratio and logging it for offline analysis.
3. **Per-turn metrics** — recording structuring latency, provider, token usage,
   and specialty skill injection for prompt optimization.

Inspired by MediGenius's 100% source annotation + accuracy tracking.

Usage::

    from services.observability.structuring_tracker import (
        StructuringMeta,
        FieldAttribution,
        log_structuring_event,
        log_correction_event,
    )

    # After structuring
    meta = StructuringMeta(
        provider="ollama",
        model="qwen2.5:14b",
        latency_ms=1200,
        input_length=len(text),
        output_length=len(record.content),
        specialty="cardiology",
        skills_injected=["cardiology-structuring"],
    )
    log_structuring_event(doctor_id, meta, record)

    # When doctor edits a record
    log_correction_event(doctor_id, record_id, old_content, new_content)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.log import log as _log


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_rc_loader = None

def _load_config() -> dict:
    global _rc_loader
    if _rc_loader is None:
        from utils.runtime_config import load_runtime_json
        _rc_loader = load_runtime_json
    return _rc_loader()

_LOG_DIR = Path(os.environ.get("STRUCTURING_LOG_DIR", "logs"))
_LOG_FILE = _LOG_DIR / "structuring_events.jsonl"


def _is_test() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FieldAttribution:
    """Source attribution for a single structured field.

    Attributes:
        field_name: Which field this attribution is for ("content", "tags", etc.).
        source: Where the information came from:
            "verbatim" — directly from doctor's words (minimal LLM transformation)
            "inferred" — LLM synthesized/reorganized from context
            "knowledge" — referenced from doctor_knowledge DB
            "skill"    — informed by specialty skill rules
            "unknown"  — source could not be determined
        confidence: 0.0–1.0 estimated confidence.
        detail: Optional explanation (e.g. which skill file contributed).
    """

    field_name: str
    source: str = "unknown"
    confidence: float = 1.0
    detail: Optional[str] = None


@dataclass
class StructuringMeta:
    """Metadata captured during a structuring event.

    Attached to a MedicalRecord as supplementary quality data (not persisted
    to DB — written to JSONL log for offline analysis).
    """

    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    input_length: int = 0             # input text char count
    output_length: int = 0            # structured content char count
    specialty: Optional[str] = None
    skills_injected: List[str] = field(default_factory=list)
    encounter_type: str = "unknown"
    consultation_mode: bool = False
    attributions: List[FieldAttribution] = field(default_factory=list)

    # Computed quality signals
    compression_ratio: float = 0.0    # output_length / input_length
    tag_count: int = 0
    has_scores: bool = False

    def compute_derived(self) -> None:
        """Fill in derived metrics from primary fields."""
        if self.input_length > 0:
            self.compression_ratio = round(self.output_length / self.input_length, 3)


@dataclass
class CorrectionEvent:
    """Records a doctor's correction to a structured record."""

    record_id: int
    doctor_id: str
    old_content: str
    new_content: str
    edit_distance: float = 0.0        # 0.0 = identical, 1.0 = completely different
    old_tags: List[str] = field(default_factory=list)
    new_tags: List[str] = field(default_factory=list)
    tags_added: int = 0
    tags_removed: int = 0

    def compute_diff(self) -> None:
        """Compute edit distance and tag diff metrics."""
        self.edit_distance = round(
            1.0 - SequenceMatcher(None, self.old_content, self.new_content).ratio(),
            4,
        )
        old_set = set(self.old_tags)
        new_set = set(self.new_tags)
        self.tags_added = len(new_set - old_set)
        self.tags_removed = len(old_set - new_set)


# ---------------------------------------------------------------------------
# Attribution helpers
# ---------------------------------------------------------------------------

def attribute_content(
    original_text: str,
    structured_content: str,
    skill_names: Optional[List[str]] = None,
) -> FieldAttribution:
    """Determine the source attribution for the 'content' field.

    Heuristic: if >60% of the structured content tokens appear verbatim in
    the original text, classify as "verbatim"; otherwise "inferred".
    """
    if not original_text or not structured_content:
        return FieldAttribution(field_name="content", source="unknown")

    ratio = SequenceMatcher(None, original_text, structured_content).ratio()

    if ratio > 0.6:
        source = "verbatim"
        confidence = round(ratio, 3)
    elif skill_names:
        source = "skill"
        confidence = round(max(0.5, ratio), 3)
    else:
        source = "inferred"
        confidence = round(max(0.3, ratio), 3)

    return FieldAttribution(
        field_name="content",
        source=source,
        confidence=confidence,
        detail=f"similarity={ratio:.3f}" + (f" skills={skill_names}" if skill_names else ""),
    )


def attribute_tags(tags: List[str], original_text: str) -> FieldAttribution:
    """Determine attribution for the 'tags' field."""
    if not tags:
        return FieldAttribution(field_name="tags", source="unknown", confidence=0.0)

    # Count how many tags appear verbatim in original text.
    verbatim_count = sum(1 for t in tags if t in original_text)
    ratio = verbatim_count / len(tags) if tags else 0

    source = "verbatim" if ratio > 0.5 else "inferred"
    return FieldAttribution(
        field_name="tags",
        source=source,
        confidence=round(ratio, 3),
        detail=f"verbatim_tags={verbatim_count}/{len(tags)}",
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_structuring_event(
    doctor_id: str,
    meta: StructuringMeta,
    record: Optional[Any] = None,
) -> None:
    """Write a structuring event to the JSONL log.

    Args:
        doctor_id: The doctor who triggered structuring.
        meta: Structuring metadata with attribution.
        record: Optional MedicalRecord (for tag_count, has_scores).
    """
    if _is_test():
        return

    meta.compute_derived()

    if record is not None:
        meta.tag_count = len(getattr(record, "tags", []))
        meta.has_scores = bool(getattr(record, "specialty_scores", []))

    payload: Dict[str, Any] = {
        "event": "structuring",
        "ts": _utc_now_iso(),
        "doctor_id": doctor_id,
        "provider": meta.provider,
        "model": meta.model,
        "latency_ms": round(meta.latency_ms, 1),
        "input_length": meta.input_length,
        "output_length": meta.output_length,
        "compression_ratio": meta.compression_ratio,
        "specialty": meta.specialty,
        "encounter_type": meta.encounter_type,
        "consultation_mode": meta.consultation_mode,
        "skills_injected": meta.skills_injected,
        "tag_count": meta.tag_count,
        "has_scores": meta.has_scores,
    }
    if meta.attributions:
        payload["attributions"] = [asdict(a) for a in meta.attributions]

    _write_event(payload)


def log_correction_event(
    doctor_id: str,
    record_id: int,
    old_content: str,
    new_content: str,
    old_tags: Optional[List[str]] = None,
    new_tags: Optional[List[str]] = None,
) -> None:
    """Log a doctor's correction to a structured record.

    The edit distance and tag diff are computed automatically.
    """
    if _is_test():
        return

    evt = CorrectionEvent(
        record_id=record_id,
        doctor_id=doctor_id,
        old_content=old_content,
        new_content=new_content,
        old_tags=old_tags or [],
        new_tags=new_tags or [],
    )
    evt.compute_diff()

    payload: Dict[str, Any] = {
        "event": "correction",
        "ts": _utc_now_iso(),
        "doctor_id": doctor_id,
        "record_id": record_id,
        "edit_distance": evt.edit_distance,
        "tags_added": evt.tags_added,
        "tags_removed": evt.tags_removed,
    }

    _write_event(payload)

    _log(
        f"[structuring_tracker] correction: record={record_id} "
        f"edit_dist={evt.edit_distance:.3f} "
        f"tags +{evt.tags_added}/-{evt.tags_removed}"
    )


def _write_event(payload: Dict[str, Any]) -> None:
    """Write a JSON event to the structuring log file."""
    try:
        from services.observability.observability import _enqueue_jsonl
        _enqueue_jsonl(_LOG_FILE, payload)
    except Exception:
        try:
            _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
