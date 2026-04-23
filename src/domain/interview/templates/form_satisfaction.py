"""Patient satisfaction survey — first non-medical template (kind="form").

Proves the Phase 1/2 seams hold for templates that don't go through the
medical prompt_composer path and persist to form_responses instead of
medical_records.
"""
from __future__ import annotations

from typing import Any

from domain.interview.protocols import (
    CompletenessState, FieldSpec, Mode, Phase, SessionState,
)

# ---- field specs -----------------------------------------------------------

_RATING_FIVE = ("非常满意", "满意", "一般", "不满意", "非常不满意")
_WAIT_RATING = ("很快", "合理", "偏长", "很长")
_RECOMMEND = ("一定会", "可能会", "不太会", "不会")


FORM_SATISFACTION_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="overall_rating", type="enum", tier="required", appendable=False,
        enum_values=_RATING_FIVE,
        label="总体满意度",
        description="本次就诊整体满意度",
    ),
    FieldSpec(
        name="wait_time_rating", type="enum", tier="recommended", appendable=False,
        enum_values=_WAIT_RATING,
        label="等待时间",
        description="候诊时间是否合理",
    ),
    FieldSpec(
        name="doctor_rating", type="enum", tier="recommended", appendable=False,
        enum_values=_RATING_FIVE,
        label="医生服务",
        description="医生沟通与诊疗满意度",
    ),
    FieldSpec(
        name="recommend", type="enum", tier="recommended", appendable=False,
        enum_values=_RECOMMEND,
        label="推荐意愿",
        description="是否愿意向家人朋友推荐",
    ),
    FieldSpec(
        name="comments", type="text", tier="optional", appendable=False,
        label="补充说明",
        description="其他建议或具体反馈（可选）",
    ),
]


# ---- extractor -------------------------------------------------------------

class FormSatisfactionExtractor:
    """FieldExtractor for the satisfaction survey.

    Form extractors don't use prompt_composer — they produce a minimal
    survey-style message list directly.
    """

    def fields(self) -> list[FieldSpec]:
        return FORM_SATISFACTION_FIELDS

    async def prompt_partial(
        self,
        collected: dict[str, str],
        history: list[dict[str, Any]],
        phase: Phase,
        mode: Mode,
        **_unused: Any,
    ) -> list[dict[str, str]]:
        system_lines = [
            "你是满意度调查助手，帮助医院收集患者就诊反馈。",
            "请用友好、简短的中文提问。每次只问1-2个问题。",
            "已有答案不要重复问。当所有必答题回答完毕，确认提交。",
            "",
            "调查问题：",
        ]
        for spec in FORM_SATISFACTION_FIELDS:
            label = spec.label or spec.name
            options = (
                " / ".join(spec.enum_values)
                if spec.enum_values else "（开放回答）"
            )
            tier_hint = {
                "required": "必答",
                "recommended": "建议回答",
                "optional": "可选",
            }.get(spec.tier, "")
            system_lines.append(f"- {label}（{tier_hint}）：{options}")

        missing = [
            s.label or s.name
            for s in FORM_SATISFACTION_FIELDS
            if not collected.get(s.name)
        ]
        user_lines = [
            f"已收集：{collected}",
            f"还未回答：{', '.join(missing) if missing else '无'}",
        ]

        return [
            {"role": "system", "content": "\n".join(system_lines)},
            {"role": "user", "content": "\n".join(user_lines)},
        ]

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        _fields_by_name = {f.name: f for f in self.fields()}
        for name, value in extracted.items():
            if name not in _fields_by_name:
                continue
            if not value:
                continue
            value = value.strip() if isinstance(value, str) else value
            if value:
                collected[name] = value
        return collected

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        specs = self.fields()
        required = [s.name for s in specs if s.tier == "required"]
        recommended = [s.name for s in specs if s.tier == "recommended"]
        optional = [s.name for s in specs if s.tier == "optional"]

        required_missing = [f for f in required if not collected.get(f)]
        recommended_missing = [f for f in recommended if not collected.get(f)]
        optional_missing = [f for f in optional if not collected.get(f)]

        next_focus: str | None = None
        if recommended_missing:
            next_focus = recommended_missing[0]
        elif optional_missing:
            next_focus = optional_missing[0]

        return CompletenessState(
            can_complete=len(required_missing) == 0,
            required_missing=required_missing,
            recommended_missing=recommended_missing,
            optional_missing=optional_missing,
            next_focus=next_focus,
        )

    def next_phase(
        self, session: SessionState, phases: list[Phase],
    ) -> Phase:
        return phases[0]
