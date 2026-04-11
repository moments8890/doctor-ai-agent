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


# ── Teach by Example ──────────────────────────────────────────────────────────

class TeachRequest(BaseModel):
    example_text: str


@router.post("/api/manage/persona/teach")
async def teach_by_example(
    body: TeachRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Extract style rules from a pasted example response and create pending items."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    text = body.example_text.strip()
    if not text:
        raise HTTPException(400, "example_text must not be empty")
    if len(text) > 2000:
        raise HTTPException(400, "example_text must be under 2000 characters")

    TEACH_PROMPT = """分析以下医生的回复示例，提取其中体现的沟通风格偏好。

回复示例：
{text}

请用JSON格式回答（不要输出其他内容），提取最多3条最明显的风格特征：
{{
  "rules": [
    {{
      "field": "reply_style" 或 "closing" 或 "structure" 或 "avoid" 或 "edits",
      "text": "一句话描述这个风格特征",
      "confidence": "low" 或 "medium" 或 "high"
    }}
  ]
}}

判断规则：
- reply_style: 语气、称呼方式、正式程度
- closing: 结尾用语、随访叮嘱
- structure: 内容组织方式、是否先给结论
- avoid: 明显回避的内容类型
- edits: 语言修辞习惯
只提取有明确证据的特征，不要猜测。最多输出3条。"""

    try:
        from agent.llm import llm_call
        import json

        response = await llm_call(
            messages=[
                {"role": "system", "content": "你是一个分析医生写作风格的助手。只输出JSON，不要输出其他内容。"},
                {"role": "user", "content": TEACH_PROMPT.format(text=text[:1500])},
            ],
            op_name="persona_teach",
        )

        if not response:
            raise HTTPException(500, "Analysis failed, please try again")

        raw = response.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        parsed = json.loads(raw)
        rules = parsed.get("rules", [])

    except (json.JSONDecodeError, Exception) as exc:
        from utils.log import log
        log(f"[persona_teach] extraction failed: {exc}", level="warning")
        raise HTTPException(500, "Analysis failed, please try again")

    VALID_FIELDS = {"reply_style", "closing", "structure", "avoid", "edits"}
    VALID_CONFIDENCES = {"low", "medium", "high"}

    # Create pending items for medium+ confidence rules
    from db.models.persona_pending import PersonaPendingItem
    from domain.knowledge.persona_classifier import compute_pattern_hash

    created = []
    for rule in rules[:3]:
        field = rule.get("field")
        rule_text = (rule.get("text") or "").strip()
        confidence = rule.get("confidence", "medium")

        if field not in VALID_FIELDS or not rule_text:
            continue
        if confidence not in VALID_CONFIDENCES or confidence == "low":
            continue

        pattern = compute_pattern_hash(field, rule_text)

        # Skip if exact pattern already pending or accepted
        from sqlalchemy import select
        existing = (await session.execute(
            select(PersonaPendingItem).where(
                PersonaPendingItem.doctor_id == resolved,
                PersonaPendingItem.pattern_hash == pattern,
                PersonaPendingItem.status.in_(["pending", "accepted"]),
            )
        )).scalar_one_or_none()

        if existing:
            continue

        item = PersonaPendingItem(
            doctor_id=resolved,
            field=field,
            proposed_rule=rule_text,
            summary=rule_text,
            evidence_summary="从示例回复中提取",
            confidence=confidence,
            pattern_hash=pattern,
            status="pending",
        )
        session.add(item)
        created.append({"field": field, "text": rule_text, "confidence": confidence})

    await session.commit()
    return {"status": "ok", "extracted": created, "count": len(created)}
