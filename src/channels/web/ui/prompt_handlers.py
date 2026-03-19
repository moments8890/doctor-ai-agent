"""
Prompt management routes: CRUD, versioning, rollback, and preview.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.crud import get_system_prompt, upsert_system_prompt
from db.engine import AsyncSessionLocal
from db.models import SystemPrompt
from channels.web.ui._utils import _fmt_ts, _require_ui_admin_access

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Models ────────────────────────────────────────────────────────────────────

class PromptUpdate(BaseModel):
    content: str


class PromptRollback(BaseModel):
    version_id: int


# ── Helpers ───────────────────────────────────────────────────────────────────

# Prompt keys that are used as .format() templates at runtime.
# Map key → set of required placeholder names.
_TEMPLATE_PLACEHOLDERS: dict[str, set[str]] = {
    "memory.compress": {"today"},
    "report.extract": {"records_text"},
}


def _validate_prompt_template(key: str, content: str) -> None:
    """Raise HTTPException if content breaks required format() placeholders."""
    required = _TEMPLATE_PLACEHOLDERS.get(key)
    if not required:
        return
    # Check that .format() with dummy values succeeds and all placeholders exist.
    test_kwargs = {p: "__TEST__" for p in required}
    try:
        formatted = content.format(**test_kwargs)
    except (KeyError, ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Prompt template error: {exc}. "
            f"Required placeholders for '{key}': {sorted(required)}",
        )
    for p in required:
        if f"__TEST__" not in formatted:
            raise HTTPException(
                status_code=422,
                detail=f"Missing required placeholder {{{p}}} in prompt '{key}'.",
            )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/manage/prompts", include_in_schema=True)
async def manage_prompts(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as db:
        base = await get_system_prompt(db, "structuring")
        ext = await get_system_prompt(db, "structuring.extension")
    return {
        "structuring": base.content if base else "",
        "structuring_extension": ext.content if ext else "",
    }


@router.put("/api/manage/prompts/{key}", include_in_schema=True)
async def update_prompt(
    key: str,
    body: PromptUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    if key not in {"structuring", "structuring.extension"}:
        raise HTTPException(status_code=400, detail="Only structuring and structuring.extension are editable.")
    _validate_prompt_template(key, body.content)
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, body.content, changed_by="admin")
    return {"ok": True, "key": key}


@router.get("/api/admin/prompts")
async def admin_get_prompts(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(SystemPrompt).order_by(SystemPrompt.key))).scalars().all()
    return {
        "prompts": [
            {"key": p.key, "content": p.content or "", "updated_at": _fmt_ts(p.updated_at)}
            for p in rows
        ]
    }


@router.put("/api/admin/prompts/{key}")
async def admin_update_prompt(
    key: str,
    body: PromptUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    _validate_prompt_template(key, body.content)
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, body.content, changed_by="admin")
    return {"ok": True, "key": key}


@router.get("/api/admin/prompts/{key}/versions")
async def admin_get_prompt_versions(
    key: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    limit: int = 20,
):
    """Return version history for a prompt key, newest first."""
    _require_ui_admin_access(x_admin_token)
    from db.crud.system import list_system_prompt_versions
    async with AsyncSessionLocal() as db:
        versions = await list_system_prompt_versions(db, key, limit=limit)
    return {
        "key": key,
        "versions": [
            {
                "id": v.id,
                "content": v.content or "",
                "changed_by": v.changed_by,
                "changed_at": _fmt_ts(v.changed_at),
            }
            for v in versions
        ],
    }


@router.post("/api/admin/prompts/{key}/rollback")
async def admin_rollback_prompt(
    key: str,
    body: PromptRollback,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Restore a prompt to the content of a specific version entry."""
    _require_ui_admin_access(x_admin_token)
    from db.crud.system import rollback_system_prompt
    async with AsyncSessionLocal() as db:
        result = await rollback_system_prompt(db, key, body.version_id, changed_by="admin:rollback")
    if result is None:
        raise HTTPException(status_code=404, detail="Version not found or key mismatch")
    from utils.prompt_loader import invalidate
    invalidate(key)
    return {"ok": True, "key": key, "restored_from_version": body.version_id}
