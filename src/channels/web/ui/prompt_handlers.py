"""
Prompt management routes: CRUD, versioning, rollback, and preview.

SystemPrompt table has been removed. Prompts are now file-defined in
prompts/*.md (ADR 0011). These endpoints are stubbed to avoid breaking
existing UI integrations.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from channels.web.ui._utils import _fmt_ts, _require_ui_admin_access

router = APIRouter(tags=["ui"], include_in_schema=False)


# -- Models --

class PromptUpdate(BaseModel):
    content: str


class PromptRollback(BaseModel):
    version_id: int


# -- Helpers --

_TEMPLATE_PLACEHOLDERS: dict[str, set[str]] = {
    "memory.compress": {"today"},
    "report.extract": {"records_text"},
}


def _validate_prompt_template(key: str, content: str) -> None:
    """Raise HTTPException if content breaks required format() placeholders."""
    required = _TEMPLATE_PLACEHOLDERS.get(key)
    if not required:
        return
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


# -- Routes (stubbed — SystemPrompt table removed) --

@router.get("/api/manage/prompts", include_in_schema=True)
async def manage_prompts(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    from utils.prompt_loader import get_prompt_sync
    return {
        "structuring": get_prompt_sync("structuring") or "",
        "structuring_extension": get_prompt_sync("structuring.extension") or "",
    }


@router.put("/api/manage/prompts/{key}", include_in_schema=True)
async def update_prompt(
    key: str,
    body: PromptUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    raise HTTPException(status_code=501, detail="SystemPrompt DB table removed. Edit prompts/*.md files directly.")


@router.get("/api/admin/prompts")
async def admin_get_prompts(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    return {"prompts": []}


@router.put("/api/admin/prompts/{key}")
async def admin_update_prompt(
    key: str,
    body: PromptUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    raise HTTPException(status_code=501, detail="SystemPrompt DB table removed. Edit prompts/*.md files directly.")


@router.get("/api/admin/prompts/{key}/versions")
async def admin_get_prompt_versions(
    key: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    limit: int = 20,
):
    _require_ui_admin_access(x_admin_token)
    return {"key": key, "versions": []}


@router.post("/api/admin/prompts/{key}/rollback")
async def admin_rollback_prompt(
    key: str,
    body: PromptRollback,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _require_ui_admin_access(x_admin_token)
    raise HTTPException(status_code=501, detail="SystemPrompt DB table removed. Rollback not available.")
