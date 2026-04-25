"""ChatSessionState — sticky state machine on the patient chat thread.

States: idle | intake | qa_window
Transitions match design spec §1a / §1b / §1c. Exit from intake requires explicit
cancellation or 24h decay; classifier confidence alone never exits intake.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

log = logging.getLogger("chat_state.entry")

from domain.patient_lifecycle.triage import TriageResult, TriageCategory

PRIMARY_THRESHOLD = 0.65
LOWER_THRESHOLD = 0.50
CANCEL_THRESHOLD = 0.85
INTAKE_IDLE_HOURS = 24
QA_WINDOW_IDLE_MINUTES = 30

LEXICON_BODY_SITES = ("头", "胸", "肚", "胃", "腹", "腰", "背", "腿", "膝", "嗓", "喉", "心", "肝", "肾", "脾")
LEXICON_SYMPTOM_TERMS = ("痛", "晕", "喘", "酸", "麻", "肿", "热", "凉", "吐", "拉", "咳", "鸣")
LEXICON_DURATION = ("几天", "几周", "几月", "最近", "好几", "一直", "总是", "好长时间", "持续")


class IntakeEntryReason(str, Enum):
    PRIMARY_THRESHOLD = "primary_threshold"
    LEXICON_BOOST = "lexicon_boost"


@dataclass
class IntakeEntryDecision:
    entered: bool
    reason: Optional[IntakeEntryReason] = None


def _lexicon_match(message: str) -> bool:
    return (
        any(t in message for t in LEXICON_BODY_SITES)
        or any(t in message for t in LEXICON_SYMPTOM_TERMS)
        or any(t in message for t in LEXICON_DURATION)
    )


def evaluate_entry(triage: TriageResult, message: str) -> IntakeEntryDecision:
    if triage.category != TriageCategory.symptom_report:
        return IntakeEntryDecision(entered=False)
    if triage.confidence >= PRIMARY_THRESHOLD:
        log.info("chat_state.entry.entered branch=primary_threshold confidence=%.2f", triage.confidence)
        return IntakeEntryDecision(entered=True, reason=IntakeEntryReason.PRIMARY_THRESHOLD)
    if triage.confidence >= LOWER_THRESHOLD and _lexicon_match(message):
        log.info("chat_state.entry.entered branch=lexicon_boost confidence=%.2f", triage.confidence)
        return IntakeEntryDecision(entered=True, reason=IntakeEntryReason.LEXICON_BOOST)
    return IntakeEntryDecision(entered=False)


@dataclass
class ChatSessionState:
    state: str = "idle"  # idle | intake | qa_window
    record_id: Optional[int] = None
    intake_segment_id: Optional[str] = None
    last_intake_turn_at_iso: Optional[str] = None
    qa_window_entered_at_iso: Optional[str] = None
    cancellation_reason: Optional[str] = None

    def handle_classifier_only(self, triage: TriageResult) -> "ChatSessionState":
        # Classifier confidence alone cannot exit intake (sticky exit rule).
        return self

    def handle_cancel_signal(self, confidence: float) -> "ChatSessionState":
        if confidence < CANCEL_THRESHOLD:
            return self
        return ChatSessionState(state="idle", record_id=self.record_id, cancellation_reason="patient_cancel")

    def enter_qa_window(self, intent: str) -> "ChatSessionState":
        return ChatSessionState(
            state="qa_window",
            record_id=self.record_id,
            intake_segment_id=self.intake_segment_id,
            last_intake_turn_at_iso=self.last_intake_turn_at_iso,
            qa_window_entered_at_iso=datetime.now(timezone.utc).isoformat(),
        )

    def handle_message(self, triage: TriageResult, message: str) -> "ChatSessionState":
        if self.state == "qa_window":
            decision = evaluate_entry(triage, message)
            if decision.entered:
                return ChatSessionState(
                    state="intake",
                    record_id=self.record_id,
                    intake_segment_id=self.intake_segment_id,
                    last_intake_turn_at_iso=datetime.now(timezone.utc).isoformat(),
                )
        return self

    def apply_idle_decay(self, now_iso: str) -> "ChatSessionState":
        now = datetime.fromisoformat(now_iso)
        if self.state == "intake" and self.last_intake_turn_at_iso:
            last = datetime.fromisoformat(self.last_intake_turn_at_iso)
            if (now - last).total_seconds() / 3600 >= INTAKE_IDLE_HOURS:
                return ChatSessionState(state="idle", record_id=self.record_id, cancellation_reason="idle_decay")
        if self.state == "qa_window" and self.qa_window_entered_at_iso:
            entered = datetime.fromisoformat(self.qa_window_entered_at_iso)
            if (now - entered).total_seconds() / 60 >= QA_WINDOW_IDLE_MINUTES:
                return ChatSessionState(
                    state="intake",
                    record_id=self.record_id,
                    intake_segment_id=self.intake_segment_id,
                    last_intake_turn_at_iso=self.last_intake_turn_at_iso,
                )
        return self
