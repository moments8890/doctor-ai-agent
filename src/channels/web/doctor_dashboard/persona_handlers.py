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


class UpdateSummaryRequest(BaseModel):
    summary_text: str


class ActivateRequest(BaseModel):
    active: bool


class ApplyTemplateRequest(BaseModel):
    template_id: str


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
        "summary_text": persona.summary_text or "",
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


@router.put("/api/manage/persona/summary")
async def update_summary(
    body: UpdateSummaryRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Save the doctor's free-text persona summary."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    text = body.summary_text.strip()
    if len(text) > 2000:
        raise HTTPException(400, "summary_text must be under 2000 characters")

    persona = await get_or_create_persona(session, resolved)
    persona.summary_text = text if text else None
    if text and persona.status == "draft":
        persona.status = "active"
    await session.commit()
    return {"status": "ok"}


@router.post("/api/manage/persona/generate")
async def generate_profile(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Generate a natural-language AI profile from structured rules + doctor info."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    persona = await get_or_create_persona(session, resolved)

    # Gather rules text
    fields = persona.fields
    FIELD_LABELS = {
        "reply_style": "回复风格", "closing": "常用结尾语",
        "structure": "回复结构", "avoid": "回避内容", "edits": "常见修改",
    }
    rules_parts = []
    for key, label in FIELD_LABELS.items():
        rules = fields.get(key, [])
        if rules:
            texts = "、".join(r.get("text", "") for r in rules if r.get("text"))
            if texts:
                rules_parts.append(f"- {label}：{texts}")

    if not rules_parts and not persona.summary_text:
        raise HTTPException(400, "没有可用的风格规则来生成描述")

    rules_text = "\n".join(rules_parts) if rules_parts else f"（当前描述：{persona.summary_text[:200]}）"

    # Load doctor info
    from sqlalchemy import select
    from db.models.doctor import Doctor
    doctor = (await session.execute(
        select(Doctor).where(Doctor.doctor_id == resolved)
    )).scalar_one_or_none()

    doctor_name = doctor.name if doctor else "医生"
    specialty = doctor.specialty if doctor and doctor.specialty else "全科"

    from utils.prompt_loader import get_prompt_sync
    from agent.llm import llm_call

    template = get_prompt_sync("persona-generate")
    prompt = template.format(
        doctor_name=doctor_name,
        specialty=specialty,
        rules_text=rules_text,
    )

    try:
        response = await llm_call(
            messages=[
                {"role": "system", "content": "你是一个生成AI助手风格档案的工具。严格按指定格式输出，简洁专业。"},
                {"role": "user", "content": prompt},
            ],
            op_name="persona_generate",
            max_tokens=400,
        )
        if not response or len(response.strip()) < 20:
            raise HTTPException(500, "生成失败，请重试")

        generated = response.strip()
        persona.summary_text = generated
        if persona.status == "draft":
            persona.status = "active"
        await session.commit()
        return {"status": "ok", "summary_text": generated}

    except HTTPException:
        raise
    except Exception as exc:
        from utils.log import log
        log(f"[persona_generate] failed: {exc}", level="warning")
        raise HTTPException(500, "生成失败，请重试")


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


# ── Templates ────────────────────────────────────────────────────────────────

@router.get("/api/manage/persona/templates")
async def list_templates(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return available persona templates (lightweight list)."""
    _resolve_ui_doctor_id(doctor_id, authorization)  # auth check only
    from domain.knowledge.persona_templates import PERSONA_TEMPLATES
    return {
        "templates": [
            {"id": t["id"], "name": t["name"], "subtitle": t["subtitle"], "summary_text": t["summary_text"], "sample_reply": t.get("sample_reply", "")}
            for t in PERSONA_TEMPLATES
        ]
    }


@router.post("/api/manage/persona/apply-template")
async def apply_template(
    body: ApplyTemplateRequest,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Apply a pre-built persona template to the doctor's persona."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    from domain.knowledge.persona_templates import PERSONA_TEMPLATES
    template = next((t for t in PERSONA_TEMPLATES if t["id"] == body.template_id), None)
    if not template:
        raise HTTPException(404, "模板不存在")

    persona = await get_or_create_persona(session, resolved)
    persona.summary_text = template["summary_text"]
    persona.fields = template["build_fields"]()
    persona.status = "active"
    persona.onboarded = True

    await session.commit()
    return {
        "status": "ok",
        "summary_text": persona.summary_text,
        "fields": persona.fields,
        "persona_status": "active",
    }


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

    from utils.prompt_loader import get_prompt_sync
    teach_template = get_prompt_sync("persona-teach")

    try:
        from agent.llm import llm_call
        import json

        response = await llm_call(
            messages=[
                {"role": "system", "content": "你是一个分析医生写作风格的助手。只输出JSON，不要输出其他内容。"},
                {"role": "user", "content": teach_template.format(text=text[:1500])},
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
