"""Guided medical intake interview state machine."""
from __future__ import annotations
from dataclasses import dataclass, field

STEPS: list[tuple[str, str]] = [
    ("patient_name",        "患者叫什么名字？"),
    ("chief_complaint",     "哪里不舒服？主要症状是什么？"),
    ("duration",            "这个症状持续多久了？"),
    ("severity",            "严重程度如何？轻微、中等还是比较严重？"),
    ("associated_symptoms", "还有其他伴随症状吗？没有请说「没有」"),
    ("past_history",        "既往病史或药物过敏史？没有请说「没有」"),
    ("physical_exam",       "体格检查结果？没有请说「跳过」"),
]

_SKIP = {"没有", "无", "跳过", "没", "none", "no"}


@dataclass
class InterviewState:
    step: int = 0
    answers: dict = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.step < len(STEPS)

    @property
    def current_field(self) -> str:
        return STEPS[self.step][0] if self.active else ""

    @property
    def current_question(self) -> str:
        return STEPS[self.step][1] if self.active else ""

    @property
    def progress(self) -> str:
        return f"[{self.step}/{len(STEPS)}]"

    def record_answer(self, text: str) -> None:
        field_name = STEPS[self.step][0]
        self.answers[field_name] = text.strip()
        self.step += 1

    def compile_text(self) -> str:
        """Build a natural-language summary for structure_medical_record."""
        parts = []
        a = self.answers

        if name := a.get("patient_name"):
            parts.append(f"患者{name}")
        if cc := a.get("chief_complaint"):
            parts.append(f"主诉：{cc}")
        if dur := a.get("duration"):
            parts.append(f"持续{dur}")
        if sev := a.get("severity"):
            parts.append(f"程度{sev}")
        if assoc := a.get("associated_symptoms"):
            if assoc.strip() not in _SKIP:
                parts.append(f"伴随症状：{assoc}")
        if hist := a.get("past_history"):
            if hist.strip() not in _SKIP:
                parts.append(f"既往病史：{hist}")
        if pe := a.get("physical_exam"):
            if pe.strip() not in _SKIP:
                parts.append(f"体格检查：{pe}")

        return "，".join(parts)

    @property
    def patient_name(self) -> str | None:
        return self.answers.get("patient_name")
