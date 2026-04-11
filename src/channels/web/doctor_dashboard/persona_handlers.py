"""Persona management API for doctor AI behavior preferences."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.crud.persona import (
    get_or_create_persona,
    add_rule_to_persona,
    remove_rule_from_persona,
    update_rule_in_persona,
    generate_rule_id,
)

router = APIRouter(tags=["ui"], include_in_schema=False)

VALID_FIELDS = {"reply_style", "closing", "structure", "avoid", "edits"}


# ── Request models ───────────────────────────────────────────────────────────

class AddRuleRequest(BaseModel):
    field: str
    text: str


class UpdateRuleRequest(BaseModel):
    field: str
    rule_id: str
    text: str


class DeleteRuleRequest(BaseModel):
    field: str
    rule_id: str


class ActivateRequest(BaseModel):
    active: bool


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/api/manage/persona")
async def get_persona(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return the doctor's full persona with all fields and rules."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    persona = await get_or_create_persona(session, resolved)
    await session.commit()

    return {
        "doctor_id": resolved,
        "fields": persona.fields,
        "status": persona.status,
        "onboarded": persona.onboarded,
        "edit_count": persona.edit_count,
        "version": persona.version,
        "updated_at": persona.updated_at.isoformat() if persona.updated_at else None,
    }


@router.post("/api/manage/persona/rules")
async def add_rule(
    body: AddRuleRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Add a new rule to a persona field."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    if body.field not in VALID_FIELDS:
        raise HTTPException(400, "field must be one of: {}".format(", ".join(sorted(VALID_FIELDS))))
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text must not be empty")

    persona = await get_or_create_persona(session, resolved)
    rule = {"id": generate_rule_id(), "text": text, "source": "doctor", "usage_count": 0}
    add_rule_to_persona(persona, body.field, rule)

    # Auto-activate on first rule add
    if persona.status == "draft":
        persona.status = "active"

    await session.commit()
    return {"status": "ok", "rule": rule, "persona_status": persona.status}


@router.put("/api/manage/persona/rules")
async def update_rule(
    body: UpdateRuleRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Update a rule's text."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    if body.field not in VALID_FIELDS:
        raise HTTPException(400, "field must be one of: {}".format(", ".join(sorted(VALID_FIELDS))))
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text must not be empty")

    persona = await get_or_create_persona(session, resolved)
    update_rule_in_persona(persona, body.field, body.rule_id, text)

    await session.commit()
    return {"status": "ok"}


@router.delete("/api/manage/persona/rules")
async def delete_rule(
    body: DeleteRuleRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Delete a rule from a persona field."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    if body.field not in VALID_FIELDS:
        raise HTTPException(400, "field must be one of: {}".format(", ".join(sorted(VALID_FIELDS))))

    persona = await get_or_create_persona(session, resolved)
    remove_rule_from_persona(persona, body.field, body.rule_id)

    await session.commit()
    return {"status": "ok"}


@router.post("/api/manage/persona/activate")
async def activate_persona(
    body: ActivateRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Activate or deactivate the doctor's persona."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    persona = await get_or_create_persona(session, resolved)

    persona.status = "active" if body.active else "draft"

    await session.commit()
    return {"status": "ok", "persona_status": persona.status}


# ── Onboarding ────────────────────────────────────────────────────────────────

class OnboardingPicksRequest(BaseModel):
    picks: list[dict]


@router.get("/api/manage/persona/onboarding/scenarios")
async def get_onboarding_scenarios(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return onboarding scenarios for pick-your-style flow."""
    _resolve_ui_doctor_id(doctor_id, authorization)  # auth check only
    from domain.knowledge.onboarding_scenarios import GENERIC_SCENARIOS
    return {"scenarios": GENERIC_SCENARIOS}


@router.post("/api/manage/persona/onboarding/complete")
async def complete_onboarding(
    body: OnboardingPicksRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Process onboarding picks and populate persona."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    from domain.knowledge.onboarding_scenarios import extract_rules_from_picks
    rules_by_field = extract_rules_from_picks(body.picks)

    persona = await get_or_create_persona(session, resolved)

    # Write extracted rules to persona
    for field_key, rules in rules_by_field.items():
        for rule in rules:
            add_rule_to_persona(persona, field_key, rule)

    persona.onboarded = True
    if persona.status == "draft" and any(rules_by_field.values()):
        persona.status = "active"

    await session.commit()
    return {"status": "ok", "fields": persona.fields, "persona_status": persona.status}
