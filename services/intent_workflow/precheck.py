"""Minimal stateful precheck — deterministic layer before normal routing.

Checks authoritative session state for blocked write continuations.
This is NOT a semantic rule engine — it handles exact workflow-state
transitions only (ADR 0007).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from services.domain.name_utils import (
    is_blocked_write_cancel,
    name_only_text,
    name_with_supplement,
)
from services.session import (
    clear_blocked_write_context,
    get_blocked_write_context,
)
from utils.log import log


@dataclass
class BlockedWriteContinuation:
    """Result of a successful blocked-write precheck resolution."""

    patient_name: str
    clinical_text: str         # original clinical content from the blocked turn
    original_text: str         # raw input from the blocked turn
    supplement: Optional[str]  # additional text appended in the continuation turn
    history_snapshot: list     # history at block time


def precheck_blocked_write(
    doctor_id: str,
    text: str,
) -> Optional[BlockedWriteContinuation]:
    """Check if the current message continues a blocked write.

    Returns:
        BlockedWriteContinuation if the message is a name reply to a
        previously blocked add_record.  Returns None otherwise (fall
        through to normal routing).

    Side effects:
        - Clears blocked write context on cancel.
        - Clears blocked write context on successful resolution.
        - Clears stale/unrelated messages (non-name, non-cancel).
    """
    ctx = get_blocked_write_context(doctor_id)
    if ctx is None:
        return None

    stripped = text.strip()

    # Cancel command
    if is_blocked_write_cancel(stripped):
        clear_blocked_write_context(doctor_id)
        log(f"[precheck] blocked write cancelled doctor={doctor_id}")
        return None  # caller checks for cancel separately

    # Bare name: "张三"
    bare_name = name_only_text(stripped)
    if bare_name:
        clear_blocked_write_context(doctor_id)
        log(
            f"[precheck] blocked write resumed with bare name={bare_name} "
            f"doctor={doctor_id}"
        )
        return BlockedWriteContinuation(
            patient_name=bare_name,
            clinical_text=ctx.clinical_text,
            original_text=ctx.original_text,
            supplement=None,
            history_snapshot=ctx.history_snapshot,
        )

    # Name + supplement: "张三，还有头痛三天"
    ns = name_with_supplement(stripped)
    if ns:
        name, supplement = ns
        # Merge supplement into clinical text
        merged_text = f"{ctx.clinical_text}，{supplement}" if ctx.clinical_text else supplement
        clear_blocked_write_context(doctor_id)
        log(
            f"[precheck] blocked write resumed with name={name} "
            f"supplement={supplement[:30]!r} doctor={doctor_id}"
        )
        return BlockedWriteContinuation(
            patient_name=name,
            clinical_text=merged_text,
            original_text=ctx.original_text,
            supplement=supplement,
            history_snapshot=ctx.history_snapshot,
        )

    # Not a name reply — the doctor sent something else.
    # Clear stale blocked context and fall through to normal routing.
    clear_blocked_write_context(doctor_id)
    log(
        f"[precheck] blocked write cleared (unrelated message) "
        f"doctor={doctor_id} text={stripped[:40]!r}"
    )
    return None


def is_blocked_write_cancel_reply(doctor_id: str, text: str) -> bool:
    """Return True if text cancels an active blocked write.

    Separate from precheck_blocked_write so callers can generate
    a cancel reply without needing the full continuation dataclass.
    """
    ctx = get_blocked_write_context(doctor_id)
    if ctx is None:
        return False
    return is_blocked_write_cancel(text.strip())
