"""GeneralMedicalTemplate — Phase 2.5 implementation.

Phase 2.5: GeneralMedicalExtractor now owns the full medical prompt context
building (prompt_partial), metadata extraction (extract_metadata), and reply
softening (post_process_reply). The legacy _call_intake_llm in
intake_turn.py is the behavior reference — byte-identical context output is
the preservation bar.
"""
from __future__ import annotations

import re
from typing import Any

from domain.intake.protocols import (
    BatchExtractor, CompletenessState, EngineConfig, FieldExtractor, FieldSpec,
    Mode, Phase, PersistRef, PostConfirmHook, SessionState, Template, Writer,
)
from domain.patients.intake_context import (
    _load_patient_info,
    _load_previous_history,
)

# ---- field specs — canonical source of medical-intake schema ------------

# Declarative: add/remove/reorder fields here. Legacy callers import via the
# completeness.py and intake_models.py shims (both now thin re-exports).

MEDICAL_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="chief_complaint", type="string", tier="required", appendable=False,
        label="主诉",
        description="促使就诊的主要症状+持续时间",
        example="腹痛3天",
    ),
    FieldSpec(
        name="present_illness", type="text", tier="required", appendable=True,
        label="现病史",
        description="症状详情、演变、已做检查",
        example="脐周阵发性钝痛，无放射，进食后加重",
    ),
    FieldSpec(
        name="past_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="既往史",
        description="既往疾病、手术、长期用药",
        example="高血压10年，口服氨氯地平",
    ),
    FieldSpec(
        name="allergy_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="过敏史",
        description="药物/食物过敏",
        example="青霉素过敏",
    ),
    FieldSpec(
        name="family_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="家族史",
        description="家族遗传病史",
        example="父亲糖尿病",
    ),
    FieldSpec(
        name="personal_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="个人史",
        description="吸烟、饮酒、职业暴露",
        example="吸烟20年，1包/天",
    ),
    FieldSpec(
        name="marital_reproductive", type="text", tier="optional", appendable=True,
        label="婚育史",
        description="婚育情况",
        example="已婚，育1子",
    ),
    FieldSpec(
        name="physical_exam", type="text", tier="recommended", appendable=True,
        label="体格检查",
        description="生命体征、阳性/阴性体征",
        example="腹软，脐周压痛，无反跳痛",
    ),
    FieldSpec(
        name="specialist_exam", type="text", tier="optional", appendable=True,
        label="专科检查",
        description="专科特殊检查",
        example="肛门指检未触及肿物",
    ),
    FieldSpec(
        name="auxiliary_exam", type="text", tier="optional", appendable=True,
        label="辅助检查",
        description="化验、影像结果",
        example="血常规WBC 12.5×10⁹/L",
    ),
    FieldSpec(
        name="diagnosis", type="string", tier="recommended", appendable=False,
        label="诊断",
        description="初步诊断或印象",
        example="急性胃肠炎",
    ),
    FieldSpec(
        name="treatment_plan", type="text", tier="recommended", appendable=True,
        label="治疗方案",
        description="处方、处置、建议",
        example="口服蒙脱石散，清淡饮食",
    ),
    FieldSpec(
        name="orders_followup", type="text", tier="optional", appendable=True,
        label="医嘱及随访",
        description="医嘱及复诊安排",
        example="3天后复诊，如加重急诊",
    ),
    FieldSpec(
        name="department", type="string", tier="optional", appendable=False,
        label="科别",
        description="科别：门诊/急诊/住院 + 科室",
    ),
]


# ---- engine-driven focus policy (2026-04-27) -------------------------------
#
# These tables move the patient-intake state machine out of the prompt and
# into the engine. The prompt previously carried 32 rules including 17a
# (danger-screen tables) and 17b (chronic-disease drill-down) that referenced
# fictional "phase 1 / phase 2" state with no engine support. The engine now
# computes the exact next question + chip seeds and surfaces them via
# CompletenessState.next_focus_question.

# 17a danger-screen trigger map (≤3 questions per CC). Each entry is
# (question_text, suggestion_seeds). Asked-tracker (`_asked_safety_net`)
# in collected[] dedupes across turns.
_DANGER_SCREEN_TRIGGERS: dict[str, list[tuple[str, list[str]]]] = {
    "headache": [
        ("是突然剧烈发作的，还是慢慢加重的？", ["突然剧烈", "慢慢加重", "说不清"]),
        ("有没有视物模糊、说话困难、手脚没力气？", ["没有", "有视物模糊", "有手脚无力", "不清楚"]),
        ("有没有发热？", ["没有", "有发热", "不清楚"]),
    ],
    "chest_pain": [
        ("是劳累或情绪激动后出现的吗？", ["是的", "不是", "说不清"]),
        ("有没有出冷汗或憋气？", ["没有", "有出冷汗", "有憋气", "不清楚"]),
        ("有没有放射到肩膀、胳膊或下颌？", ["没有", "有放射", "不清楚"]),
    ],
    "abdominal": [
        ("具体在哪个位置？", ["上腹部", "下腹部", "肚脐周围", "说不清"]),
        ("是阵发性还是持续性？", ["阵发性", "持续性", "说不清"]),
        ("有没有发热、呕吐或腹泻？", ["没有", "有发热", "有呕吐", "有腹泻"]),
    ],
}

_DANGER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "headache": ("头痛", "头疼", "头晕", "头胀"),
    "chest_pain": ("胸痛", "胸闷", "心悸", "心慌", "呼吸困难", "喘不上"),
    "abdominal": ("腹痛", "肚子疼", "肚子痛", "胃痛", "腹泻", "呕吐"),
}

# 17b chronic-disease drill-down map. Triggered when a chronic condition
# has just been mentioned in past_history (short → not yet drilled).
_CHRONIC_DRILLDOWN: dict[str, tuple[str, list[str]]] = {
    "糖尿病": ("您现在血糖控制得怎么样？吃什么药？", ["控制可", "偶尔偏高", "不清楚"]),
    "高血压": ("您平时血压多少？吃什么降压药？", ["控制可", "偶尔偏高", "不清楚"]),
    "抗凝": ("这个药按时吃吗？最近有没有自己停过？", ["按时吃", "停过", "不清楚"]),
    "华法林": ("这个药按时吃吗？最近有没有自己停过？", ["按时吃", "停过", "不清楚"]),
    "阿司匹林": ("这个药按时吃吗？最近有没有自己停过？", ["按时吃", "停过", "不清楚"]),
}


def _postprocess_suggestions(reply: str, suggestions: list[str]) -> list[str]:
    """Engine-side chip post-processing.

    1. Cap at 4 entries, each ≤10 chars (truncate, don't drop).
    2. If the LLM asked a binary-ish question, ensure at least one negative
       chip (没有/无) is present — inject if missing.
    3. If the question is multi-choice or vague, ensure an uncertainty chip
       (不清楚/说不准) is present — inject if missing.
    4. Dedup case-insensitive (Chinese is case-insensitive in practice).
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in suggestions or []:
        if not s or not isinstance(s, str):
            continue
        s = s.strip()
        if not s:
            continue
        if len(s) > 10:
            s = s[:10]
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)

    # Binary detection — LLM asked a yes/no-ish question
    has_binary_marker = any(p in reply for p in ("有没有", "是不是", "吗？", "吗?"))
    has_negative = any(neg in chip for chip in cleaned for neg in ("没有", "无", "不是"))
    if has_binary_marker and not has_negative and len(cleaned) < 4:
        cleaned.append("没有")
        seen.add("没有")

    # Uncertainty detection — multi-choice question (含"还是"/"或"), or
    # vague request ("怎么样"/"什么感觉"/"具体..." style)
    has_multichoice = "还是" in reply or "或者" in reply
    has_vague = any(p in reply for p in ("怎么样", "什么感觉", "具体什么", "什么情况"))
    has_uncertain = any(
        u in chip for chip in cleaned
        for u in ("不清楚", "说不准", "说不清", "不太清楚", "不知道")
    )
    if (has_multichoice or has_vague) and not has_uncertain and len(cleaned) < 4:
        cleaned.append("不清楚")

    # Final cap
    return cleaned[:4]


# ---- extractor -------------------------------------------------------------

from agent.prompt_composer import (
    compose_for_doctor_intake as _compose_for_doctor_intake,
    compose_for_patient_intake as _compose_for_patient_intake,
)


class GeneralMedicalExtractor:
    """Phase 1 thin-stub FieldExtractor. Every method forwards to legacy code."""

    def fields(self) -> list[FieldSpec]:
        return MEDICAL_FIELDS

    async def prompt_partial(
        self,
        session_state: SessionState,
        completeness_state: CompletenessState,
        phase: Phase,
        mode: Mode,
    ) -> list[dict[str, str]]:
        """Build the medical intake LLM message list.

        Phase 2.5: absorbs the patient_context + history-window logic that
        previously lived in _call_intake_llm. The engine passes structured
        state; this method produces the messages list.
        """
        import json

        collected = session_state.collected
        conversation = session_state.conversation
        state = completeness_state

        # Field metadata for hints (from template's own FieldSpec list)
        fields_by_name = {f.name: f for f in self.fields()}

        # Fetch patient info + previous history (medical-specific)
        patient_info = await _load_patient_info(session_state.patient_id)
        previous_history = await _load_previous_history(
            session_state.patient_id, session_state.doctor_id,
        )

        # Split collected into "本次新填" (patient-confirmed this visit) vs.
        # "待确认（上次记录）" (carry-forward seeded but not yet confirmed by
        # the patient). Without this split the LLM sees fields in BOTH
        # `已收集` and `必填缺` simultaneously — contradictory, and it
        # resolves the contradiction by ignoring phase-2 fields entirely.
        cf_meta_raw = collected.get("_carry_forward_meta")
        cf_meta = cf_meta_raw if isinstance(cf_meta_raw, dict) else {}

        confirmed_collected: dict[str, str] = {}
        pending_carry: dict[str, str] = {}
        for k, v in collected.items():
            if k.startswith("_"):
                continue
            entry = cf_meta.get(k)
            if (
                isinstance(entry, dict)
                and entry.get("confirmed_by_patient") is False
            ):
                pending_carry[k] = v
            else:
                confirmed_collected[k] = v

        can_str = "是" if state.can_complete else "否"

        # "待补充" with inline hints (top 3 recommended/optional fields)
        guide_parts = []
        for fk in (list(state.recommended_missing) + list(state.optional_missing))[:3]:
            spec = fields_by_name.get(fk)
            label = (spec.label if spec else fk) or fk
            if spec and (spec.description or spec.example):
                hint = spec.description or ""
                example = spec.example or ""
                if hint and example:
                    guide_parts.append(f'{label}({hint},如"{example}")')
                elif hint:
                    guide_parts.append(f'{label}({hint})')
                else:
                    guide_parts.append(label)
            else:
                guide_parts.append(label)

        # Required missing (only when can_complete is False)
        req_parts = []
        if not state.can_complete:
            for fk in state.required_missing:
                spec = fields_by_name.get(fk)
                label = (spec.label if spec else fk) or fk
                if spec and (spec.description or spec.example):
                    hint = spec.description or ""
                    example = spec.example or ""
                    if hint and example:
                        req_parts.append(f'{label}({hint},如"{example}")')
                    elif hint:
                        req_parts.append(f'{label}({hint})')
                    else:
                        req_parts.append(label)
                else:
                    req_parts.append(label)

        context_lines = [
            f"患者：{patient_info['name']}，{patient_info['gender']}，{patient_info['age']}岁",
            f"已收集（本次新填）：{json.dumps(confirmed_collected, ensure_ascii=False)}",
            f"可完成：{can_str}",
        ]
        if pending_carry:
            # Format with field labels so the LLM knows what to ask about.
            cf_lines = []
            for fk, fv in pending_carry.items():
                spec = fields_by_name.get(fk)
                label = (spec.label if spec else fk) or fk
                cf_lines.append(f'  {label}({fk}): "{fv}"')
            context_lines.append(
                "待确认（上次记录，需患者逐项确认；规则18-19适用）：\n"
                + "\n".join(cf_lines)
            )
        # Engine-driven focus (2026-04-27): when set, the engine has
        # computed the exact next question + chip seeds. Surface as a
        # concrete instruction so the LLM doesn't have to interpret
        # priority rules. Falls through to legacy 必填缺/待补充 when not set.
        if state.next_focus_question:
            context_lines.append(f"下一步焦点：{state.next_focus_question}")
            if state.next_focus_suggestions:
                context_lines.append(
                    "建议 suggestions 选项（请基于本次问题调整）："
                    + json.dumps(state.next_focus_suggestions, ensure_ascii=False)
                )
        elif req_parts:
            context_lines.append(f"必填缺：{'｜'.join(req_parts)}")
        if guide_parts and not state.next_focus_question:
            context_lines.append(f"待补充：{'｜'.join(guide_parts)}")
        if previous_history:
            prev = previous_history.replace("\n", " ").strip()
            if len(prev) > 100:
                prev = prev[:100] + "..."
            context_lines.append(f"上次：{prev}")

        # Conversation history window. Was 6 — too short for typical patient
        # intake (12-15 turns) and the LLM forgot what it had already asked,
        # leading to question loops. Bumped to 20 to cover even longer flows
        # (carry-forward confirmation can extend the turn count).
        _HISTORY_WINDOW = 20
        if len(conversation) > _HISTORY_WINDOW:
            early_turns = conversation[:-_HISTORY_WINDOW]
            early_summary_parts = []
            for t in early_turns:
                role_label = "患者" if t.get("role") == "user" else "助手"
                content = t.get("content", "").strip()
                if content and role_label == "患者":
                    early_summary_parts.append(content[:80])
            if early_summary_parts:
                context_lines.append(f"早期对话摘要：{'；'.join(early_summary_parts)}")

        patient_context = "\n".join(context_lines)

        history = [
            {"role": turn.get("role", "user"), "content": turn.get("content", "")}
            for turn in conversation[-_HISTORY_WINDOW:]
        ]

        # Separate the latest user message from history (goes to doctor_message slot)
        latest_msg = ""
        prior_history = history
        if history and history[-1].get("role") == "user":
            latest_msg = history[-1]["content"]
            prior_history = history[:-1]

        if mode == "doctor":
            return await _compose_for_doctor_intake(
                doctor_id=session_state.doctor_id,
                patient_context=patient_context,
                doctor_message=latest_msg,
                history=prior_history,
                template_id=session_state.template_id,
            )
        return await _compose_for_patient_intake(
            doctor_id=session_state.doctor_id,
            patient_context=patient_context,
            doctor_message=latest_msg,
            history=prior_history,
            template_id=session_state.template_id,
        )

    def extract_metadata(
        self, extracted: dict[str, str],
    ) -> dict[str, str]:
        """Pop patient metadata out of the raw LLM extraction dict.

        Medical templates surface patient_name/gender/age at the turn level;
        engine stores them as underscore-prefixed keys in session.collected.
        """
        out = {}
        for key in ("patient_name", "patient_gender", "patient_age"):
            value = extracted.get(key)
            if isinstance(value, str):
                value = value.strip()
            if value:
                out[key] = value
        return out

    def post_process_reply(
        self, reply: str, collected: dict[str, str], mode: Mode,
    ) -> str:
        """Soften blocking language when all required fields are set.

        If can_complete=True (required fields filled), rewrite phrases like
        "还需要补充X" → "如方便可再补充" and strip "必须..." / "还缺...".
        Preserves the current intake_turn.py:317-325 behavior.
        """
        import re
        state = self.completeness(collected, mode)
        if not state.can_complete:
            return reply

        # Only soften if reply contains blocking language
        if not any(kw in reply for kw in ("还需要", "必须", "还缺")):
            return reply

        out = re.sub(r"还需要补充.+?[。；]?", "如方便可再补充", reply)
        out = re.sub(r"必须.+?[。；]?", "", out)
        out = re.sub(r"还缺.+?[。；]?", "", out)
        if not out.strip():
            out = "已记录。现在可以点击「完成」生成病历。"
        return out

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        """Merge LLM-extracted fields into collected using FieldSpec.appendable.

        Inlined from completeness.merge_extracted (Phase 2). Dedup rule:
        on appendable fields, if the new value is a substring of existing
        text, skip it. Non-appendable fields always overwrite.
        """
        _fields_by_name = {f.name: f for f in self.fields()}
        for name, value in extracted.items():
            spec = _fields_by_name.get(name)
            if spec is None:
                continue
            if not value:
                continue
            value = value.strip()
            if not value:
                continue
            if spec.appendable:
                existing = collected.get(name, "")
                if existing and value in existing:
                    continue
                collected[name] = (
                    f"{existing}；{value}".strip("；") if existing else value
                )
            else:
                collected[name] = value
        return collected

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        """Tier-based completeness. Uses FieldSpec.tier; patient mode filters
        to the subjective-field subset.

        Inlined from completeness.get_completeness_state (Phase 2).
        """
        specs = self.fields()

        _PATIENT_FIELDS = {
            "chief_complaint", "present_illness", "past_history",
            "allergy_history", "family_history", "personal_history",
            "marital_reproductive",
        }

        if mode == "patient":
            specs = [s for s in specs if s.name in _PATIENT_FIELDS]
            # Patient intake drives the full pre-consultation loop: all
            # subjective fields are required before the session is "ready
            # to review". This matches patient-intake.md's stop condition.
            required = [s.name for s in specs]
            recommended = []
            optional = []
        else:
            required = [s.name for s in specs if s.tier == "required"]
            recommended = [s.name for s in specs if s.tier == "recommended"]
            optional = [s.name for s in specs if s.tier == "optional"]

        # Unconfirmed carry-forward fields don't count as filled — patient
        # must explicitly confirm (or the LLM must re-extract from new
        # patient input, which flips confirmed_by_patient → true). Without
        # this, intake ends after turn 2 because phase-2 fields seeded from
        # the previous record satisfy completeness immediately.
        cf_meta_raw = collected.get("_carry_forward_meta")
        cf_meta = cf_meta_raw if isinstance(cf_meta_raw, dict) else {}

        def _filled(f: str) -> bool:
            if not collected.get(f):
                return False
            entry = cf_meta.get(f)
            if isinstance(entry, dict) and entry.get("confirmed_by_patient") is False:
                return False
            return True

        required_missing = [f for f in required if not _filled(f)]
        recommended_missing = [f for f in recommended if not _filled(f)]
        optional_missing = [f for f in optional if not _filled(f)]

        next_focus: str | None = None
        if recommended_missing:
            next_focus = recommended_missing[0]
        elif optional_missing:
            next_focus = optional_missing[0]

        # ---- engine-driven focus policy -----------------------------------
        # Compute phase1_complete + next_focus_question. This used to be
        # interpretive prompt logic (rules 11/12/12.1/17a/17b in
        # patient-intake.md); moving it here gives the LLM a concrete
        # instruction each turn.

        asked_set: set[str] = set(collected.get("_asked_safety_net") or [])
        present = (collected.get("present_illness") or "").lower()
        chief = (collected.get("chief_complaint") or "")

        # Phase 1 structural completeness: time + characteristic + ≥1 associated
        has_time = bool(re.search(
            r"\d|天|周|月|小时|分钟|半天|整天|早上|晚上|刚才|突然",
            present + chief,
        ))
        has_characteristic = bool(re.search(
            r"阵发|持续|搏动|钝痛|刺痛|绞痛|胀痛|放射|加重|减轻|位置|侧|上|下|左|右|前|后",
            present,
        ))
        has_associated = bool(re.search(
            r"恶心|呕吐|发热|发烧|腹泻|出汗|无力|麻木|视物|视力|言语|无",
            present,
        ))
        phase1_complete = has_time and has_characteristic and has_associated

        next_focus_question: str | None = None
        next_focus_suggestions: list[str] = []

        # Engine-driven focus only fires for patient mode. Doctor mode keeps
        # the original "next_focus = first missing field key" semantics so
        # existing doctor-intake prompts/tests are unchanged.
        if mode == "patient":
            # P0: 17a danger screen — match CC keywords, walk the trigger
            # list, take the first not-yet-asked question. Heuristic skip:
            # if the LLM has already gathered the answer in present_illness
            # (e.g. patient volunteered "发烧38°"), we still let it ask —
            # false positives prefer asking over silently dropping safety
            # net coverage.
            cc_lower = chief.lower()
            matched_cc_key: str | None = None
            for cc_key, kws in _DANGER_KEYWORDS.items():
                if any(kw in cc_lower or kw in present for kw in kws):
                    matched_cc_key = cc_key
                    break
            if matched_cc_key:
                for question, seeds in _DANGER_SCREEN_TRIGGERS[matched_cc_key]:
                    if question in asked_set:
                        continue
                    next_focus_question = question
                    next_focus_suggestions = list(seeds)
                    break

            # P0b: 17b chronic-disease drill-down. Only fire when the field
            # is short (= just-mentioned, no drill yet). Once the patient
            # has elaborated past 30 chars we treat the drill as covered.
            if next_focus_question is None:
                past = collected.get("past_history") or ""
                if past and len(past) < 30:
                    for drill_key, (question, seeds) in _CHRONIC_DRILLDOWN.items():
                        if drill_key in past and question not in asked_set:
                            next_focus_question = question
                            next_focus_suggestions = list(seeds)
                            break

            # P1: phase 1 structural gap — ask the missing dimension
            if next_focus_question is None and not phase1_complete:
                if not has_time:
                    next_focus_question = "大概持续多久了？什么时候开始的？"
                    next_focus_suggestions = ["几小时", "几天", "几周", "说不清"]
                elif not has_characteristic:
                    next_focus_question = "具体什么感觉？比如阵发性、持续性、搏动性？"
                    next_focus_suggestions = ["持续性", "阵发性", "说不清"]
                elif not has_associated:
                    next_focus_question = "有没有其他不舒服，比如恶心、发热、无力？"
                    next_focus_suggestions = ["没有", "有恶心", "有发热", "有无力"]

            # P2: required_missing fallback — generic "now let's cover X"
            if next_focus_question is None and required_missing:
                fk = required_missing[0]
                spec = next((s for s in specs if s.name == fk), None)
                label = (spec.label if spec else fk) if spec else fk
                next_focus_question = f"接下来想了解一下您的{label}。"
                next_focus_suggestions = []

        return CompletenessState(
            can_complete=len(required_missing) == 0,
            required_missing=required_missing,
            recommended_missing=recommended_missing,
            optional_missing=optional_missing,
            next_focus=next_focus,
            phase1_complete=phase1_complete,
            next_focus_question=next_focus_question,
            next_focus_suggestions=next_focus_suggestions,
        )

    def next_phase(
        self, session: SessionState, phases: list[Phase],
    ) -> Phase:
        # Phase 1: template declares a single phase. This returns it.
        # Phase 3+ may introduce real branching; keep the protocol ready for that.
        return phases[0]


# ---- batch extractor -------------------------------------------------------


class MedicalBatchExtractor:
    """Phase 1 stub. Forwards to the existing batch_extract_from_transcript."""

    async def extract(
        self,
        conversation: list[dict[str, Any]],
        context: dict[str, Any],
        mode: Mode,
    ) -> dict[str, str] | None:
        # Lazy import to avoid circular dependency:
        # completeness (shim) → medical_general → intake_summary → completeness
        from domain.patients.intake_summary import (
            batch_extract_from_transcript as _batch_extract_from_transcript,
        )
        return await _batch_extract_from_transcript(
            conversation, context, mode=mode,
        )


# ---- writer -----------------------------------------------------------------

from fastapi import HTTPException

from agent.tools.resolve import resolve as _resolve_patient
from db.crud.doctor import _ensure_doctor_exists
from db.engine import AsyncSessionLocal
from db.models.records import MedicalRecordDB, RecordStatus


# Columns that the writer controls explicitly — NOT mapped from `collected`
# even if a key with the same name is present. Keep in sync with the
# explicit kwargs in persist() below.
#
# - id / created_at / updated_at: auto-generated by the ORM.
# - doctor_id / patient_id: sourced from session + _ensure_patient, never
#   from `collected`.
# - record_type / status / content: derived by the writer itself
#   (record_type is fixed, status from completeness heuristics, content
#   from _build_clinical_text).
_WRITER_CONTROLLED_COLUMNS: frozenset[str] = frozenset({
    "id",
    "created_at",
    "updated_at",
    "doctor_id",
    "patient_id",
    "record_type",
    "status",
    "content",
})


class MedicalRecordWriter:
    """Writer. Persists the confirmed intake to medical_records.

    Maps `collected` keys to `MedicalRecordDB` columns generically: any
    `collected` key whose name matches an ORM column (and isn't writer-
    controlled) becomes a kwarg on the INSERT. This lets specialty variants
    (e.g. medical_neuro_v1) introduce new FieldSpec + column pairs without
    the writer caring.

    Absorbs deferred patient creation from confirm.py:72-101. Does NOT fire
    diagnosis / notifications / task generation — those are separate hooks.
    """

    async def persist(
        self, session: SessionState, collected: dict[str, str],
    ) -> PersistRef:
        # Lazy import to avoid circular dependency:
        # completeness (shim) → medical_general → shared → intake_turn → completeness
        from channels.web.doctor_intake.shared import _build_clinical_text

        patient_id = await self._ensure_patient(session, collected)

        clinical_text = _build_clinical_text(collected)
        has_diagnosis = bool(collected.get("diagnosis", "").strip())
        has_treatment = bool(collected.get("treatment_plan", "").strip())
        has_followup = bool(collected.get("orders_followup", "").strip())
        status = (
            RecordStatus.completed.value
            if (has_diagnosis and has_treatment and has_followup)
            else RecordStatus.pending_review.value
        )

        # Dynamic column mapping: any `collected` key that matches an ORM
        # column on MedicalRecordDB and is not writer-controlled flows through
        # as a kwarg. Underscore-prefixed keys (engine-level metadata like
        # _patient_name) are skipped. Unknown keys are silently ignored.
        table_columns = {c.name for c in MedicalRecordDB.__table__.columns}
        column_kwargs = {
            key: value
            for key, value in collected.items()
            if not key.startswith("_")
            and key in table_columns
            and key not in _WRITER_CONTROLLED_COLUMNS
        }

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, session.doctor_id)
            record = MedicalRecordDB(
                doctor_id=session.doctor_id,
                patient_id=patient_id,
                record_type="intake_summary",
                status=status,
                content=clinical_text,
                **column_kwargs,
            )
            db.add(record)
            await db.commit()
            record_id = record.id

        return PersistRef(kind="medical_record", id=record_id)

    async def _ensure_patient(
        self, session: SessionState, collected: dict[str, str],
    ) -> int:
        """If session.patient_id is set, return it. Otherwise resolve from
        collected["_patient_name"] and create the patient row. Mirrors the
        confirm.py:72-101 behavior byte-for-byte."""
        if session.patient_id is not None:
            return session.patient_id

        name = (collected.get("_patient_name") or "").strip()
        if not name:
            raise HTTPException(
                status_code=422,
                detail="无法确认：未检测到患者姓名，请在对话中提供",
            )

        gender = collected.get("_patient_gender")
        age_str = collected.get("_patient_age")
        age: int | None = None
        if age_str:
            try:
                age = int(age_str.rstrip("岁"))
            except (ValueError, AttributeError):
                pass

        resolved = await _resolve_patient(
            name, session.doctor_id, auto_create=True,
            gender=gender, age=age,
        )
        if "status" in resolved:
            raise HTTPException(
                status_code=422,
                detail=resolved.get("message", "Patient creation failed"),
            )
        return resolved["patient_id"]


# ---- template binding -------------------------------------------------------

from dataclasses import dataclass, field

from domain.intake.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)


@dataclass
class GeneralMedicalTemplate:
    """medical_general_v1. Binds all the medical-specific components."""
    id: str = "medical_general_v1"
    kind: str = "medical"
    display_name: str = "通用医学问诊"
    requires_doctor_review: bool = True
    supported_modes: tuple[Mode, ...] = ("patient", "doctor")
    extractor: FieldExtractor = field(default_factory=GeneralMedicalExtractor)
    batch_extractor: BatchExtractor | None = field(default_factory=MedicalBatchExtractor)
    writer: Writer = field(default_factory=MedicalRecordWriter)
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {
            "patient": [
                TriggerDiagnosisPipelineHook(),
                NotifyDoctorHook(),
            ],
            # §8 open question — doctor-mode is deliberately NOT firing
            # diagnosis in Phase 1 because that matches today's confirm.py.
            # Phase 4 revisits.
            "doctor": [
                GenerateFollowupTasksHook(),
            ],
        }
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=30,
        phases={"patient": ["default"], "doctor": ["default"]},
    ))
