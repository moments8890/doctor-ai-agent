"""Doctor persona model — structured AI behavior preferences."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


def EMPTY_PERSONA_FIELDS() -> dict:
    """Return the default empty persona fields structure."""
    return {
        "reply_style": [],
        "closing": [],
        "structure": [],
        "avoid": [],
        "edits": [],
    }


class DoctorPersona(Base):
    """Per-doctor AI persona — structured behavior preferences.

    Each rule in a field has: {"id": "ps_N", "text": "...", "source": "...", "usage_count": 0}
    """
    __tablename__ = "doctor_personas"

    doctor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
        primary_key=True,
    )
    fields_json: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: json.dumps(EMPTY_PERSONA_FIELDS()),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    onboarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    @property
    def fields(self) -> dict:
        """Parse fields_json into a dict."""
        try:
            return json.loads(self.fields_json)
        except (json.JSONDecodeError, TypeError):
            return EMPTY_PERSONA_FIELDS()

    @fields.setter
    def fields(self, value: dict):
        """Serialize dict to fields_json."""
        self.fields_json = json.dumps(value, ensure_ascii=False)

    def all_rules(self) -> list[dict]:
        """Return a flat list of all rules across all fields."""
        rules = []
        for field_rules in self.fields.values():
            rules.extend(field_rules)
        return rules

    def render_for_prompt(self, max_rules_per_field: int = 3, max_chars: int = 600) -> str:
        """Render persona as structured sections for LLM prompt injection.

        Always renders from structured fields (deterministic, no LLM).
        summary_text is display-only and never used here.

        Within each field, selects top rules by usage_count descending.
        """
        SECTION_MAP = [
            ("reply_style", "沟通风格"),
            ("structure", "回复结构"),
            ("avoid", "回避内容"),
            ("closing", "结尾方式"),
            ("edits", "修改习惯"),
        ]
        fields = self.fields
        sections = []
        for key, label in SECTION_MAP:
            rules = fields.get(key, [])
            ranked = sorted(rules, key=lambda r: r.get("usage_count", 0), reverse=True)
            bullets = [r.get("text", "").strip() for r in ranked[:max_rules_per_field] if r.get("text", "").strip()]
            if bullets:
                lines = "\n".join(f"- {b}" for b in bullets)
                sections.append(f"## {label}\n{lines}")

        if not sections:
            return ""

        result = "\n\n".join(sections)
        return result[:max_chars] if len(result) > max_chars else result
