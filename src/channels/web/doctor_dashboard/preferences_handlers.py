"""
User preferences routes: get and update preferences (font_scale, etc.).
Works for any user_id (doctor or patient).
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import UserPreferences, DEFAULT_PREFERENCES
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id

router = APIRouter(tags=["ui"], include_in_schema=False)


class PreferencesUpdate(BaseModel):
    font_scale: Optional[str] = None
    seen_releases: Optional[list[str]] = None


def _parse_prefs(row: UserPreferences | None) -> dict:
    base = dict(DEFAULT_PREFERENCES)
    if row and row.preferences_json:
        try:
            base.update(json.loads(row.preferences_json))
        except (json.JSONDecodeError, TypeError):
            pass
    return base


@router.get("/api/manage/preferences", include_in_schema=True)
async def get_preferences(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_ui_doctor_id(doctor_id, authorization)
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    return _parse_prefs(row)


@router.patch("/api/manage/preferences", include_in_schema=True)
async def patch_preferences(
    body: PreferencesUpdate,
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    user_id = _resolve_ui_doctor_id(doctor_id, authorization)
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    prefs = _parse_prefs(row)

    # Merge only provided fields
    updates = body.model_dump(exclude_none=True)

    # List-type keys use set-union merge (don't overwrite)
    if "seen_releases" in updates:
        existing = set(prefs.get("seen_releases", []))
        incoming = set(updates.pop("seen_releases"))
        prefs["seen_releases"] = sorted(existing | incoming)

    # Scalar keys overwrite as before
    prefs.update(updates)

    if row is None:
        row = UserPreferences(user_id=user_id)
        db.add(row)
    row.preferences_json = json.dumps(prefs, ensure_ascii=False)
    await db.commit()

    return prefs
