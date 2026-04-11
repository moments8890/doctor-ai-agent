"""CRUD operations for doctor_personas table."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS


def generate_rule_id() -> str:
    """Generate a unique rule ID like ps_abc123."""
    return f"ps_{uuid.uuid4().hex[:8]}"


async def get_or_create_persona(session: AsyncSession, doctor_id: str) -> DoctorPersona:
    """Get or lazily create a doctor's persona row."""
    result = await session.execute(
        select(DoctorPersona).where(DoctorPersona.doctor_id == doctor_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    persona = DoctorPersona(doctor_id=doctor_id)
    session.add(persona)
    await session.flush()
    return persona


def add_rule_to_persona(
    persona: DoctorPersona,
    field: str,
    rule: dict,
) -> DoctorPersona:
    """Add a rule to a specific field. Mutates persona in place."""
    fields = persona.fields
    if field not in fields:
        raise ValueError(f"Unknown persona field: {field}")
    fields[field].append(rule)
    persona.fields = fields
    persona.version += 1
    return persona


def remove_rule_from_persona(
    persona: DoctorPersona,
    field: str,
    rule_id: str,
) -> DoctorPersona:
    """Remove a rule by ID from a field. Mutates persona in place."""
    fields = persona.fields
    if field not in fields:
        raise ValueError(f"Unknown persona field: {field}")
    fields[field] = [r for r in fields[field] if r.get("id") != rule_id]
    persona.fields = fields
    persona.version += 1
    return persona


def update_rule_in_persona(
    persona: DoctorPersona,
    field: str,
    rule_id: str,
    new_text: str,
) -> DoctorPersona:
    """Update a rule's text by ID. Mutates persona in place."""
    fields = persona.fields
    if field not in fields:
        raise ValueError(f"Unknown persona field: {field}")
    for rule in fields[field]:
        if rule.get("id") == rule_id:
            rule["text"] = new_text
            break
    persona.fields = fields
    persona.version += 1
    return persona


async def load_active_persona_text(session: AsyncSession, doctor_id: str) -> str:
    """Load the rendered persona text for prompt injection.

    Returns empty string if no persona exists or is not active.
    """
    result = await session.execute(
        select(DoctorPersona).where(DoctorPersona.doctor_id == doctor_id)
    )
    persona = result.scalar_one_or_none()
    if not persona or persona.status != "active":
        return ""
    return persona.render_for_prompt()
