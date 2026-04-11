"""One-shot migration: move persona data from doctor_knowledge_items to doctor_personas.

Usage: python -m scripts.migrate_persona [--dry-run]

1. Creates the doctor_personas table if it doesn't exist.
2. For each doctor_knowledge_items row with category='persona':
   - Parses the 5-field text format into structured JSON rules
   - Creates a DoctorPersona row with those rules
3. Migrates 'preference' and 'communication' KB items to 'custom'.
4. Does NOT delete the old rows (safe migration — old code can still read them).
"""
import asyncio
import json
import re
import sys

from db.engine import engine, AsyncSessionLocal
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS
from db.crud.persona import generate_rule_id
from sqlalchemy import text, select


FIELD_LABELS = {
    "回复风格": "reply_style",
    "常用结尾语": "closing",
    "回复结构": "structure",
    "回避内容": "avoid",
    "常见修改": "edits",
}


def parse_persona_text(content: str) -> dict:
    """Parse old-format persona text into structured rules."""
    fields = EMPTY_PERSONA_FIELDS()
    if not content:
        return fields

    for label, field_key in FIELD_LABELS.items():
        pattern = re.compile(rf"{label}[：:]\s*(.*)", re.MULTILINE)
        match = pattern.search(content)
        if match:
            value = match.group(1).strip()
            if value and value != "（待学习）":
                fields[field_key].append({
                    "id": generate_rule_id(),
                    "text": value,
                    "source": "migrated",
                    "usage_count": 0,
                })

    return fields


async def migrate(dry_run: bool = False):
    """Run the migration."""
    # Create table if needed
    async with engine.begin() as conn:
        await conn.run_sync(DoctorPersona.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # 1. Migrate persona items
        rows = (await session.execute(
            text("SELECT doctor_id, content, persona_status FROM doctor_knowledge_items WHERE category = 'persona'")
        )).fetchall()

        print(f"Found {len(rows)} persona items to migrate")
        for row in rows:
            doctor_id, content, status = row
            fields = parse_persona_text(content)
            has_rules = any(len(v) > 0 for v in fields.values())

            if dry_run:
                print(f"  [DRY RUN] {doctor_id}: status={status}, rules={sum(len(v) for v in fields.values())}")
                continue

            # Check if persona already exists
            existing = (await session.execute(
                select(DoctorPersona).where(DoctorPersona.doctor_id == doctor_id)
            )).scalar_one_or_none()

            if existing:
                print(f"  SKIP {doctor_id}: persona already exists")
                continue

            persona = DoctorPersona(
                doctor_id=doctor_id,
                status="active" if status == "active" and has_rules else "draft",
                onboarded=has_rules,
                edit_count=0,
            )
            persona.fields = fields
            session.add(persona)
            print(f"  MIGRATED {doctor_id}: status={persona.status}, rules={sum(len(v) for v in fields.values())}")

        # 2. Migrate preference/communication items to custom
        if not dry_run:
            result = await session.execute(
                text("UPDATE doctor_knowledge_items SET category = 'custom' WHERE category IN ('preference', 'communication')")
            )
            print(f"Migrated {result.rowcount} preference/communication items to custom")

        if not dry_run:
            await session.commit()
            print("Migration complete.")
        else:
            print("[DRY RUN] No changes made.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(migrate(dry_run=dry_run))
