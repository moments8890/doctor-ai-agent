"""Teaching loop: detect significant doctor edits and optionally save as knowledge rules."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Optional

from db.models.doctor import DoctorKnowledgeItem, KnowledgeCategory
from db.models.doctor_edit import DoctorEdit
from domain.knowledge.knowledge_crud import save_knowledge_item
from utils.log import log


# ── Significance detection ────────────────────────────────────────


def should_prompt_teaching(original: str, edited: str) -> bool:
    """Return True if the edit is significant enough to warrant saving as a knowledge rule.

    Returns False for:
    - Whitespace-only changes
    - Minor edits: diff < 10 chars AND content similarity > 80%
    """
    orig_stripped = (original or "").strip()
    edit_stripped = (edited or "").strip()

    # Whitespace-only change
    import re
    if re.sub(r"\s+", "", orig_stripped) == re.sub(r"\s+", "", edit_stripped):
        return False

    # Measure similarity and diff size
    similarity = SequenceMatcher(None, orig_stripped, edit_stripped).ratio()
    diff_chars = abs(len(edit_stripped) - len(orig_stripped))

    # Also count actual character-level changes (not just length diff)
    # Use the opcodes to measure total changed characters
    matcher = SequenceMatcher(None, orig_stripped, edit_stripped)
    changed_chars = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            changed_chars += max(i2 - i1, j2 - j1)

    if changed_chars < 10 and similarity > 0.8:
        return False

    return True


# ── Edit logging ──────────────────────────────────────────────────


async def log_doctor_edit(
    session,
    doctor_id: str,
    entity_type: str,
    entity_id: int,
    original_text: str,
    edited_text: str,
    field_name: str | None = None,
) -> int:
    """Create a DoctorEdit record and return its ID."""
    edit = DoctorEdit(
        doctor_id=doctor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        original_text=original_text,
        edited_text=edited_text,
    )
    session.add(edit)
    await session.flush()  # get the ID
    edit_id = edit.id
    log(f"[teaching] logged edit {edit_id} for doctor={doctor_id} entity={entity_type}:{entity_id}")
    return edit_id


# ── Rule creation from edit ───────────────────────────────────────


async def create_rule_from_edit(
    session,
    doctor_id: str,
    edit_id: int,
) -> Optional[DoctorKnowledgeItem]:
    """Load a DoctorEdit, save edited_text as a knowledge rule with category=preference.

    Returns the created DoctorKnowledgeItem, or None if edit not found or
    doctor_id mismatch.
    """
    from sqlalchemy import select

    row = (
        await session.execute(
            select(DoctorEdit).where(DoctorEdit.id == edit_id).limit(1)
        )
    ).scalar_one_or_none()

    if row is None or row.doctor_id != doctor_id:
        return None

    rule = await save_knowledge_item(
        session,
        doctor_id=doctor_id,
        text=row.edited_text,
        source="teaching",
        confidence=1.0,
        category=KnowledgeCategory.preference,
    )

    if rule is not None:
        row.rule_created = True
        row.rule_id = rule.id
        await session.flush()
        log(f"[teaching] created rule {rule.id} from edit {edit_id} for doctor={doctor_id}")

    return rule
