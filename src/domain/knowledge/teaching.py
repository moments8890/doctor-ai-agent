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


# ── Persona lifecycle ─────────────────────────────────────────────


PERSONA_TEMPLATE = """\
## 回复风格
（AI会根据你的回复逐渐学习，你也可以直接编辑）

## 常用结尾语

## 回复结构

## 回避内容

## 常见修改"""


async def get_or_create_persona(session, doctor_id: str):
    """Get or lazily create the doctor's persona KB item."""
    from sqlalchemy import select
    from db.models.doctor import DoctorKnowledgeItem, KnowledgeCategory

    result = await session.execute(
        select(DoctorKnowledgeItem).where(
            DoctorKnowledgeItem.doctor_id == doctor_id,
            DoctorKnowledgeItem.category == KnowledgeCategory.persona.value,
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    persona = DoctorKnowledgeItem(
        doctor_id=doctor_id,
        content=PERSONA_TEMPLATE,
        category=KnowledgeCategory.persona.value,
        title="我的AI人设",
        summary="AI会根据你的回复逐渐学习你的风格",
        persona_status="draft",
        seed_source="system",
    )
    session.add(persona)
    await session.flush()
    log(f"[persona] created persona item for doctor={doctor_id}")
    return persona


_EXTRACTION_THRESHOLD = 15


async def _check_persona_extraction(doctor_id: str) -> None:
    """Check if persona extraction should run. Called as fire-and-forget."""
    from db.engine import AsyncSessionLocal
    from db.models.doctor_edit import DoctorEdit
    from sqlalchemy import select, func

    try:
        async with AsyncSessionLocal() as session:
            persona = await get_or_create_persona(session, doctor_id)
            since = persona.updated_at if persona.persona_status == "active" else None
            query = select(func.count()).select_from(DoctorEdit).where(
                DoctorEdit.doctor_id == doctor_id,
                DoctorEdit.entity_type == "draft_reply",
            )
            if since:
                query = query.where(DoctorEdit.created_at > since)
            count = (await session.execute(query)).scalar() or 0
            if count < _EXTRACTION_THRESHOLD:
                return
            await extract_persona(session, doctor_id, persona)
            await session.commit()
    except Exception as exc:
        log(f"[persona] extraction check failed (non-fatal): {exc}", level="warning")


async def extract_persona(session, doctor_id: str, persona) -> None:
    """Run LLM extraction on recent edit pairs, save as draft persona."""
    from agent.llm import llm_call
    from db.models.doctor_edit import DoctorEdit
    from sqlalchemy import select

    result = await session.execute(
        select(DoctorEdit).where(
            DoctorEdit.doctor_id == doctor_id,
            DoctorEdit.entity_type == "draft_reply",
        ).order_by(DoctorEdit.created_at.desc()).limit(30)
    )
    edits = result.scalars().all()
    if not edits:
        return

    edit_examples = []
    for e in reversed(edits):
        if e.original_text == e.edited_text:
            edit_examples.append(f"- 医生直接发送（未修改）：{e.edited_text[:100]}")
        else:
            edit_examples.append(
                f"- AI草稿：{e.original_text[:80]}\n"
                f"  医生改为：{e.edited_text[:80]}"
            )

    current_persona = persona.content if persona.persona_status == "active" else ""
    current_section = f"\n\n当前人设：\n{current_persona}" if current_persona else ""

    prompt = f"""分析以下医生的回复记录，提取其沟通风格和偏好。

{chr(10).join(edit_examples)}
{current_section}

请用以下格式输出（保留标题，填充内容）：

## 回复风格
（描述医生的整体沟通风格）

## 常用结尾语
（医生常用的结尾方式）

## 回复结构
（医生回复的典型结构）

## 回避内容
（医生从不在回复中包含的内容）

## 常见修改
（医生最常修改AI草稿的模式）"""

    messages = [
        {"role": "system", "content": "你是一个分析医生沟通风格的助手。根据医生的实际回复记录，提取可复用的风格规则。简洁、具体、可操作。"},
        {"role": "user", "content": prompt},
    ]

    try:
        response = await llm_call(messages=messages, op_name="persona_extract")
        if response and len(response.strip()) > 50:
            persona.content = response.strip()
            if persona.persona_status != "active":
                persona.persona_status = "draft"
            log(f"[persona] extracted persona for doctor={doctor_id} ({len(edits)} edits)")
        else:
            log("[persona] LLM returned insufficient content, skipping", level="warning")
    except Exception as exc:
        log(f"[persona] LLM extraction failed: {exc}", level="warning")
