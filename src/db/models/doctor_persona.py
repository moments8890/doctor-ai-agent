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

    def render_for_prompt(self, max_rules: int = 15, max_chars: int = 500) -> str:
        """Render persona rules into the prompt format with [P-id] markers.

        Prioritizes by field order: avoid > structure > reply_style > closing > edits.
        Within each field, prioritizes by usage_count descending.
        """
        FIELD_ORDER = ["avoid", "structure", "reply_style", "closing", "edits"]
        FIELD_LABELS = {
            "reply_style": "回复风格",
            "closing": "常用结尾语",
            "structure": "回复结构",
            "avoid": "回避内容",
            "edits": "常见修改",
        }
        fields = self.fields
        selected: list[tuple[str, dict]] = []

        for field_key in FIELD_ORDER:
            field_rules = fields.get(field_key, [])
            sorted_rules = sorted(field_rules, key=lambda r: r.get("usage_count", 0), reverse=True)
            for rule in sorted_rules:
                if len(selected) >= max_rules:
                    break
                selected.append((field_key, rule))
            if len(selected) >= max_rules:
                break

        if not selected:
            return ""

        grouped: dict[str, list[dict]] = {}
        for field_key, rule in selected:
            grouped.setdefault(field_key, []).append(rule)

        lines = []
        for field_key in FIELD_ORDER:
            if field_key not in grouped:
                continue
            label = FIELD_LABELS[field_key]
            parts = []
            for rule in grouped[field_key]:
                rid = rule.get("id", "?")
                text = rule.get("text", "")
                parts.append(f"{text} [P-{rid}]")
            lines.append(f"{label}：{'；'.join(parts)}")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars]
        return result
