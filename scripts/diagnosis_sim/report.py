"""Report generation for diagnosis simulation runs.

Produces HTML and JSON reports from simulation results.
Uses only stdlib + json — no application imports.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = str(_REPO_ROOT / "reports" / "diagnosis_sim")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _date_subdir() -> str:
    """Date string for subdirectory (yyyymmdd), local time."""
    return datetime.now().strftime("%Y%m%d")


def _time_slug() -> str:
    """Time string for filename (hh-mm-ss), local time."""
    return datetime.now().strftime("%H-%M-%S")


def _human_date() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _esc(text: str) -> str:
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# Badge helpers
# ---------------------------------------------------------------------------

def _badge(text: str) -> str:
    if text == "PASS":
        return '<span class="badge pass">通过</span>'
    elif text == "FAIL":
        return '<span class="badge fail">未通过</span>'
    return f'<span class="badge na">{_esc(text)}</span>'


def _score_badge(score: int) -> str:
    if score < 0:
        return '<span class="badge na">N/A</span>'
    if score >= 70:
        cls = "score-green"
    elif score >= 50:
        cls = "score-yellow"
    else:
        cls = "score-red"
    return f'<span class="badge {cls}">{score}</span>'


def _conf_badge(conf: str) -> str:
    colors = {"高": "pass", "中": "score-yellow", "低": "score-red"}
    cls = colors.get(conf, "na")
    return f'<span class="badge {cls}">{_esc(conf)}</span>'


def _urgency_badge(urg: str) -> str:
    colors = {"急诊": "fail", "紧急": "score-yellow", "常规": "pass"}
    cls = colors.get(urg, "na")
    return f'<span class="badge {cls}">{_esc(urg)}</span>'


def _intervention_badge(interv: str) -> str:
    colors = {"手术": "fail", "药物": "score-yellow", "转诊": "score-yellow", "观察": "pass"}
    cls = colors.get(interv, "na")
    return f'<span class="badge {cls}">{_esc(interv)}</span>'


def _tag_badge(tag: str) -> str:
    tag_colors = {
        "kb_injection": ("#e8f0fe", "#1a73e8"),
        "case_memory": ("#fef7e0", "#e37400"),
        "emergency": ("#fce8e6", "#c5221f"),
        "red_flags": ("#fce8e6", "#c5221f"),
        "baseline": ("#e6f4ea", "#137333"),
        "edge_case": ("#f3e8fd", "#7627bb"),
        "minimal_data": ("#f3e8fd", "#7627bb"),
        "insufficient": ("#fff3cd", "#856404"),
        "followup": ("#e8f0fe", "#1a73e8"),
        "allergy": ("#fce8e6", "#c5221f"),
        "rare": ("#f3e8fd", "#7627bb"),
        "multi_differential": ("#e6f4ea", "#137333"),
    }
    bg, fg = tag_colors.get(tag, ("#e2e3e5", "#383d41"))
    return f'<span class="tag" style="background:{bg};color:{fg}">{_esc(tag)}</span>'


# ---------------------------------------------------------------------------
# CSS — left sidebar + tab content layout
# ---------------------------------------------------------------------------

_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       line-height: 1.6; color: #1a1a1a; background: #f5f5f5; }

/* Layout: sidebar + main */
.layout { display: flex; height: 100vh; }
.sidebar { width: 280px; min-width: 280px; background: #fff; border-right: 1px solid #e0e0e0;
           display: flex; flex-direction: column; overflow: hidden; }
.sidebar-header { padding: 16px 16px 12px; border-bottom: 1px solid #e0e0e0; }
.sidebar-header h1 { font-size: 1.1rem; margin-bottom: 2px; }
.sidebar-header .meta { color: #666; font-size: 0.78rem; }
.sidebar-header .meta code { background: #e8e8e8; padding: 1px 4px; border-radius: 3px; font-size: 0.75rem; }
.sidebar-stats { display: flex; gap: 8px; margin-top: 8px; }
.stat { font-size: 0.78rem; font-weight: 600; }
.stat.pass-stat { color: #155724; }
.stat.fail-stat { color: #721c24; }

.sidebar-list { flex: 1; overflow-y: auto; }
.sidebar-item { display: flex; align-items: center; gap: 8px; padding: 10px 16px;
                cursor: pointer; border-bottom: 1px solid #f0f0f0; transition: background 0.15s; }
.sidebar-item:hover { background: #f5f8ff; }
.sidebar-item.active { background: #e8f0fe; border-right: 3px solid #1a73e8; }
.sidebar-item.passed .status-dot { background: #28a745; }
.sidebar-item.failed .status-dot { background: #dc3545; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sidebar-item .sid { font-weight: 600; font-size: 0.82rem; min-width: 36px; }
.sidebar-item .title { font-size: 0.8rem; color: #555; flex: 1; white-space: nowrap;
                       overflow: hidden; text-overflow: ellipsis; }
.sidebar-item .score { font-size: 0.75rem; font-weight: 600; color: #666; }

/* Main content area */
.main { flex: 1; overflow-y: auto; padding: 24px 32px; }
.scenario-panel { display: none; }
.scenario-panel.active { display: block; }

/* Section cards */
.section-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
                margin-bottom: 16px; overflow: hidden; }
.section-card-header { padding: 10px 16px; font-weight: 600; font-size: 0.9rem;
                       background: #fafafa; border-bottom: 1px solid #e0e0e0;
                       display: flex; justify-content: space-between; align-items: center; }
.section-card-body { padding: 14px 16px; }

/* Scenario header */
.scenario-header { margin-bottom: 20px; }
.scenario-header h2 { font-size: 1.3rem; margin-bottom: 4px; }
.scenario-header .tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
.scenario-meta { display: flex; gap: 16px; margin-top: 8px; font-size: 0.84rem; color: #666; }

/* Record fields */
.record-fields { font-size: 0.84rem; }
.record-field { margin-bottom: 6px; display: flex; }
.record-field-name { font-weight: 600; color: #555; min-width: 80px; flex-shrink: 0; }
.record-field-value { color: #333; }
.record-field-empty { color: #bbb; font-style: italic; }

/* Prior cases */
.prior-case { background: #fef7e0; border: 1px solid #f0d68a; border-radius: 8px;
              padding: 14px 16px; margin-bottom: 12px; }
.prior-case-header { font-weight: 600; font-size: 0.88rem; color: #e37400; margin-bottom: 8px;
                     display: flex; align-items: center; gap: 6px; }
.prior-case-header::before { content: "📋"; }
.prior-case .case-field { font-size: 0.82rem; margin-bottom: 4px; }
.prior-case .case-field b { color: #555; }
.prior-case-decisions { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #e0c870; }
.prior-case-decisions h5 { font-size: 0.82rem; color: #856404; margin-bottom: 6px; }
.prior-decision { font-size: 0.8rem; padding: 4px 8px; background: #fff8e1; border-radius: 4px;
                  margin-bottom: 4px; }
.prior-decision .decision-tag { font-weight: 600; color: #137333; }

/* Impact analysis */
.impact-box { background: #e8f0fe; border: 1px solid #aecbfa; border-radius: 8px;
              padding: 14px 16px; margin-top: 12px; }
.impact-box-header { font-weight: 600; font-size: 0.88rem; color: #1a73e8; margin-bottom: 8px;
                     display: flex; align-items: center; gap: 6px; }
.impact-box-header::before { content: "🔗"; }
.impact-row { font-size: 0.82rem; margin-bottom: 4px; display: flex; gap: 8px; }
.impact-label { font-weight: 600; color: #1a73e8; min-width: 80px; }
.impact-value { color: #333; }

/* KB items */
.kb-item { background: #f0f7ff; border-left: 3px solid #1a73e8; padding: 8px 12px;
           margin-bottom: 6px; border-radius: 0 6px 6px 0; font-size: 0.84rem; }
.kb-item b { color: #1a73e8; }

/* Suggestions */
.suggestion-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
                   padding: 12px; margin-bottom: 8px; }
.suggestion-card h4 { font-size: 0.9rem; margin-bottom: 2px; }
.suggestion-detail { font-size: 0.82rem; color: #444; margin-top: 4px; line-height: 1.5; }
.suggestion-section-title { font-weight: 600; font-size: 0.92rem; margin: 12px 0 8px; color: #333; }

/* Validation checks */
.check-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
@media (max-width: 900px) { .check-grid { grid-template-columns: 1fr; } }
.check-item { font-size: 0.8rem; padding: 5px 8px; border-radius: 4px; }
.check-item.pass { background: #d4edda; color: #155724; }
.check-item.fail { background: #f8d7da; color: #721c24; }
.tier-header { font-weight: 600; font-size: 0.88rem; margin: 10px 0 6px;
               display: flex; align-items: center; gap: 8px; }

/* Badges */
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge.pass { background: #d4edda; color: #155724; }
.badge.fail { background: #f8d7da; color: #721c24; }
.badge.na   { background: #e2e3e5; color: #383d41; }
.badge.score-green  { background: #d4edda; color: #155724; }
.badge.score-yellow { background: #fff3cd; color: #856404; }
.badge.score-red    { background: #f8d7da; color: #721c24; }

.fail-detail { background: #fff3cd; border-left: 3px solid #ffc107; padding: 8px 12px;
               margin: 8px 0; font-size: 0.85rem; border-radius: 0 4px 4px 0; }
.badge.kb-ref { background: #e8f0fe; color: #1a73e8; border: 1px solid #aecbfa; font-family: monospace; }
.badge.kb-ref-bad { background: #fce8e6; color: #c5221f; border: 1px solid #f5c6cb; font-family: monospace; }

/* Two-column layout for input + context */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }

/* Trace boxes (KB + case influence) */
.trace-box { border-radius: 8px; margin-bottom: 16px; overflow: hidden; }
.trace-box.kb-trace { border: 2px solid #1a73e8; }
.trace-box.case-trace { border: 2px solid #e37400; }
.trace-box.counterfactual-trace { border: 2px solid #7627bb; }
.counterfactual-trace .trace-header { background: #f3e8fd; color: #7627bb; }
.trace-header { padding: 10px 16px; font-weight: 700; font-size: 0.95rem; }
.kb-trace .trace-header { background: #e8f0fe; color: #1a73e8; }
.case-trace .trace-header { background: #fef7e0; color: #e37400; }
.trace-body { padding: 12px 16px; background: #fff; }
.trace-subtitle { font-weight: 600; font-size: 0.84rem; color: #555; margin-bottom: 8px; }
.trace-item { font-size: 0.84rem; padding: 4px 0; display: flex; align-items: center; gap: 6px; }
.trace-id { font-family: monospace; font-weight: 700; color: #1a73e8; font-size: 0.82rem; }
.trace-link { font-size: 0.84rem; padding: 6px 10px; margin-bottom: 6px;
              background: #fafafa; border-radius: 6px; border: 1px solid #e0e0e0; }
.trace-arrow-icon { font-weight: 700; color: #1a73e8; font-size: 1.1rem; }
.trace-overlap { font-size: 0.78rem; color: #666; margin-top: 2px; padding-left: 4px; }
.trace-summary { font-size: 0.82rem; font-weight: 600; margin-top: 10px; padding-top: 8px;
                 border-top: 1px solid #e0e0e0; color: #333; }
.trace-kb-item { padding: 10px 12px; margin-bottom: 8px; border-radius: 6px; border: 1px solid #e0e0e0; }
.trace-kb-item.pass { background: #f6fff6; border-color: #b7e4c7; }
.trace-kb-item.fail { background: #fff6f6; border-color: #f5c6cb; }
.trace-kb-header { font-size: 0.88rem; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.trace-concepts { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.concept-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }
.concept-tag.found { background: #d4edda; color: #155724; }
.concept-tag.missed { background: #f8d7da; color: #721c24; }
.concept-tag.excluded { background: #d4edda; color: #155724; }
.concept-tag.leaked { background: #f8d7da; color: #721c24; }
.trace-match { font-size: 0.82rem; color: #333; padding: 2px 0 2px 16px; }
.trace-concepts-inline { color: #1a73e8; font-weight: 600; }
"""


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

_FIELD_LABELS = {
    "department": "科室",
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
    "family_history": "家族史",
    "physical_exam": "体格检查",
    "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查",
    "diagnosis": "诊断",
    "treatment_plan": "治疗方案",
    "orders_followup": "医嘱随访",
}


def _build_record_html(record: dict, compact: bool = False) -> str:
    """Render medical record as HTML fields."""
    lines = []
    for key, label in _FIELD_LABELS.items():
        value = (record.get(key) or "").strip()
        if compact and not value:
            continue
        if value:
            lines.append(
                f'<div class="record-field">'
                f'<span class="record-field-name">{_esc(label)}：</span>'
                f'<span class="record-field-value">{_esc(value)}</span></div>'
            )
        else:
            lines.append(
                f'<div class="record-field">'
                f'<span class="record-field-name">{_esc(label)}：</span>'
                f'<span class="record-field-empty">（未填写）</span></div>'
            )
    return '<div class="record-fields">' + "".join(lines) + "</div>"


def _build_prior_cases_html(scenario: dict, suggestions: list) -> str:
    """Render prior cases with their confirmed decisions + impact analysis."""
    cases = scenario.get("prior_cases", [])
    if not cases:
        return ""

    parts = []
    for i, case in enumerate(cases, 1):
        rec = case.get("record", {})
        sugs = case.get("suggestions", [])

        parts.append(f'<div class="prior-case">')
        parts.append(f'<div class="prior-case-header">历史病例 #{i}</div>')

        # Show case record fields
        for key in ("chief_complaint", "present_illness", "past_history", "auxiliary_exam"):
            val = (rec.get(key) or "").strip()
            if val:
                label = _FIELD_LABELS.get(key, key)
                parts.append(f'<div class="case-field"><b>{_esc(label)}：</b>{_esc(val)}</div>')

        # Show confirmed decisions
        if sugs:
            parts.append('<div class="prior-case-decisions">')
            parts.append('<h5>医生确认的诊断决策：</h5>')
            for s in sugs:
                section_labels = {"differential": "鉴别", "workup": "检查", "treatment": "治疗"}
                sec_label = section_labels.get(s.get("section", ""), "")
                content = s.get("content", "")
                detail = s.get("detail", "")
                decision = s.get("decision", "")
                parts.append(
                    f'<div class="prior-decision">'
                    f'<span class="decision-tag">[{_esc(sec_label)}]</span> '
                    f'{_esc(content)} — {_esc(detail)} '
                    f'<span class="badge pass">{_esc(decision)}</span>'
                    f'</div>'
                )
            parts.append('</div>')
        parts.append('</div>')

    # Impact analysis — check if current suggestions reference similar concepts
    if cases and suggestions:
        parts.append('<div class="impact-box">')
        parts.append('<div class="impact-box-header">病例记忆对诊断的影响</div>')

        # Collect terms from prior confirmed decisions
        prior_terms = set()
        for case in cases:
            for s in case.get("suggestions", []):
                for word in (s.get("content", "") + " " + s.get("detail", "")).split():
                    if len(word) >= 2:
                        prior_terms.add(word)

        # Check which current suggestions reference similar concepts
        all_current_text = " ".join(
            f"{s.get('content', '')} {s.get('detail', '')}" for s in suggestions
        )

        matched_terms = [t for t in prior_terms if t in all_current_text and len(t) >= 2]
        # Filter to meaningful medical terms (not common words)
        common = {"治疗", "评估", "检查", "术后", "患者", "目前", "方案", "进行", "建议", "考虑"}
        medical_matches = [t for t in matched_terms if t not in common][:8]

        if medical_matches:
            parts.append(
                f'<div class="impact-row">'
                f'<span class="impact-label">共通概念：</span>'
                f'<span class="impact-value">{", ".join(_esc(t) for t in medical_matches)}</span>'
                f'</div>'
            )

        # Show specific influence traces
        for case in cases:
            for s in case.get("suggestions", []):
                prior_content = s.get("content", "")
                # Check if any current suggestion echoes this
                for curr in suggestions:
                    curr_text = f"{curr.get('content', '')} {curr.get('detail', '')}"
                    # Simple overlap check
                    overlap_words = [
                        w for w in prior_content.split()
                        if len(w) >= 2 and w in curr_text and w not in common
                    ]
                    if overlap_words:
                        parts.append(
                            f'<div class="impact-row">'
                            f'<span class="impact-label">历史→当前：</span>'
                            f'<span class="impact-value">'
                            f'「{_esc(prior_content)}」→ 「{_esc(curr.get("content", ""))}」'
                            f'</span></div>'
                        )
                        break  # one match per prior suggestion is enough

        if not medical_matches:
            parts.append(
                '<div class="impact-row">'
                '<span class="impact-value">（无明显共通概念检测到 — 病例记忆可能以隐式方式影响诊断推理）</span>'
                '</div>'
            )

        parts.append('</div>')

    return "".join(parts)


def _build_kb_html(scenario: dict) -> str:
    """Render injected KB items."""
    kb_items = scenario.get("knowledge_items", [])
    if not kb_items:
        return ""
    parts = []
    for item in kb_items:
        title = item.get("title", "")
        content = item.get("content", "")
        try:
            parsed = json.loads(content)
            text = parsed.get("text", content)
        except (json.JSONDecodeError, TypeError):
            text = content
        parts.append(f'<div class="kb-item"><b>{_esc(title)}</b>: {_esc(text)}</div>')
    return "".join(parts)


def _build_suggestions_html(suggestions: list, kb_items_meta: list = None) -> str:
    """Render AI suggestions grouped by section, with KB concept match badges."""
    kb_items_meta = kb_items_meta or []

    sections = {"differential": "鉴别诊断", "workup": "检查建议", "treatment": "治疗方向"}
    parts = []
    for section, label in sections.items():
        items = [s for s in suggestions if s.get("section") == section]
        if not items:
            continue
        parts.append(f'<div class="suggestion-section-title">{_esc(label)} ({len(items)})</div>')
        for i, s in enumerate(items, 1):
            content = s.get("content") or s.get("edited_text") or ""
            detail = s.get("detail", "")
            sug_text = f"{content} {detail}"
            badges = ""
            if section == "differential" and s.get("confidence"):
                badges += f" {_conf_badge(s['confidence'])}"
            elif section == "workup" and s.get("urgency"):
                badges += f" {_urgency_badge(s['urgency'])}"
            elif section == "treatment" and s.get("intervention"):
                badges += f" {_intervention_badge(s['intervention'])}"

            # KB concept match badges — check which KB items' concepts appear in this suggestion
            for kb_item in kb_items_meta:
                concepts = kb_item.get("key_concepts", [])
                relevant = kb_item.get("relevant", True)
                title = kb_item.get("title", "")
                matched = [c for c in concepts if c in sug_text]
                if matched and relevant:
                    short_title = title[:15]
                    badges += f' <span class="badge kb-ref" title="{_esc(title)}: {_esc(", ".join(matched))}">{_esc(short_title)}</span>'
                elif matched and not relevant:
                    short_title = title[:15]
                    badges += f' <span class="badge kb-ref-bad" title="{_esc(title)}: leaked {_esc(", ".join(matched))}">⚠ {_esc(short_title)}</span>'

            parts.append(
                f'<div class="suggestion-card">'
                f'<h4>{i}. {_esc(content)}{badges}</h4>'
                f'<div class="suggestion-detail">{_esc(detail)}</div>'
                f'</div>'
            )
    return "".join(parts)


def _build_checks_html(validation: dict) -> str:
    """Render validation checks for all tiers."""
    tier_defs = [
        ("tier1", "T1 结构验证"),
        ("tier2", "T2 临床准确性"),
        ("tier3", "T3 安全检查"),
        ("tier4_kb", "T4 知识库引用验证"),
        ("tier5_cases", "T5 病例记忆影响验证"),
        ("tier6_counterfactual", "T6 反事实因果验证（±注入对比）"),
    ]
    parts = []
    for tier_key, tier_label in tier_defs:
        tier = validation.get(tier_key, {})
        checks = tier.get("checks", {})
        if not checks:
            continue
        tier_pass = tier.get("pass", False)
        tier_score = tier.get("combined_score")

        header = f'<div class="tier-header">{tier_label} '
        header += _badge("PASS" if tier_pass else "FAIL")
        if tier_score is not None:
            header += f' {_score_badge(tier_score)}'
        header += '</div>'
        parts.append(header)

        items = []
        for name, info in checks.items():
            cls = "pass" if info.get("pass") else "fail"
            icon = "✓" if info.get("pass") else "✗"
            items.append(
                f'<div class="check-item {cls}">{icon} <b>{_esc(name)}</b>: {_esc(info.get("detail", ""))}</div>'
            )
        parts.append(f'<div class="check-grid">{"".join(items)}</div>')
    return "".join(parts)


def _build_kb_citation_trace_html(validation: dict, kb_items_meta: list, suggestions: list) -> str:
    """Render KB concept trace — which KB concepts appear in which suggestions."""
    if not kb_items_meta:
        return ""

    all_sug_text = " ".join(f"{s.get('content', '')} {s.get('detail', '')}" for s in suggestions)

    parts = ['<div class="trace-box kb-trace">']
    parts.append('<div class="trace-header">知识库使用验证</div>')
    parts.append('<div class="trace-body">')

    for item in kb_items_meta:
        title = item.get("title", "")
        relevant = item.get("relevant", True)
        concepts = item.get("key_concepts", [])
        matched = [c for c in concepts if c in all_sug_text]
        missed = [c for c in concepts if c not in all_sug_text]

        rel_badge = '<span class="badge pass">相关</span>' if relevant else '<span class="badge fail">不相关</span>'

        if relevant:
            # Relevant KB: show which concepts were found
            status = "pass" if matched else "fail"
            icon = "✓" if matched else "✗"
            parts.append(f'<div class="trace-kb-item {status}">')
            parts.append(f'<div class="trace-kb-header">{rel_badge} <b>{_esc(title)}</b> {icon}</div>')
            parts.append('<div class="trace-concepts">')
            for c in concepts:
                if c in matched:
                    parts.append(f'<span class="concept-tag found">{_esc(c)} ✓</span>')
                else:
                    parts.append(f'<span class="concept-tag missed">{_esc(c)} ✗</span>')
            parts.append('</div>')
            # Show which suggestions contain these concepts
            if matched:
                for s in suggestions:
                    s_text = f"{s.get('content', '')} {s.get('detail', '')}"
                    s_matched = [c for c in matched if c in s_text]
                    if s_matched:
                        sec_labels = {"differential": "鉴别", "workup": "检查", "treatment": "治疗"}
                        sec = sec_labels.get(s.get("section", ""), "")
                        parts.append(
                            f'<div class="trace-match">→ [{_esc(sec)}] {_esc(s.get("content", "")[:50])} '
                            f'<span class="trace-concepts-inline">({", ".join(_esc(c) for c in s_matched)})</span></div>'
                        )
            parts.append('</div>')
        else:
            # Irrelevant KB: verify none leaked
            status = "pass" if not matched else "fail"
            icon = "✓" if not matched else "⚠"
            parts.append(f'<div class="trace-kb-item {status}">')
            parts.append(f'<div class="trace-kb-header">{rel_badge} <b>{_esc(title)}</b> {icon}</div>')
            parts.append('<div class="trace-concepts">')
            for c in concepts:
                if c in matched:
                    parts.append(f'<span class="concept-tag leaked">{_esc(c)} ⚠ leaked</span>')
                else:
                    parts.append(f'<span class="concept-tag excluded">{_esc(c)} ✓</span>')
            parts.append('</div>')
            parts.append('</div>')

    parts.append('</div></div>')
    return "".join(parts)


def _build_case_influence_trace_html(validation: dict, scenario: dict) -> str:
    """Render case memory influence trace — how prior cases shaped current output."""
    t5 = validation.get("tier5_cases", {})
    traces = t5.get("influence_traces", [])
    prior_cases = scenario.get("prior_cases", [])
    if not prior_cases:
        return ""

    parts = ['<div class="trace-box case-trace">']
    parts.append('<div class="trace-header">病例记忆影响追踪</div>')
    parts.append('<div class="trace-body">')

    # Show expected influence terms and whether found
    checks = t5.get("checks", {})
    for key, info in checks.items():
        icon = "✓" if info.get("pass") else "✗"
        cls = "pass" if info.get("pass") else "fail"
        parts.append(
            f'<div class="check-item {cls}">{icon} {_esc(info.get("detail", ""))}</div>'
        )

    # Show traced influence links
    if traces:
        parts.append('<div class="trace-subtitle" style="margin-top:12px">历史决策 → 当前建议 映射：</div>')
        seen = set()
        for t in traces:
            key = f"{t['prior_content']}→{t['current_content']}"
            if key in seen:
                continue
            seen.add(key)
            section_labels = {"differential": "鉴别", "workup": "检查", "treatment": "治疗"}
            prior_sec = section_labels.get(t["prior_section"], t["prior_section"])
            curr_sec = section_labels.get(t["current_section"], t["current_section"])
            overlap = ", ".join(t["overlap_terms"][:5])
            parts.append(
                f'<div class="trace-link">'
                f'<span class="badge score-yellow">{_esc(prior_sec)}</span> '
                f'「{_esc(t["prior_content"][:40])}」'
                f' <span class="trace-arrow-icon">→</span> '
                f'<span class="badge pass">{_esc(curr_sec)}</span> '
                f'「{_esc(t["current_content"][:40])}」'
                f'<div class="trace-overlap">共通词: {_esc(overlap)}</div>'
                f'</div>'
            )
    else:
        parts.append('<div class="trace-item" style="color:#856404">⚠ 未检测到历史病例与当前建议的直接概念关联</div>')

    parts.append('</div></div>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_reports(
    results: List[Dict],
    scenarios: List[Dict],
    server_url: str,
    db_path: str,
    output_dir: str = _DEFAULT_OUTPUT_DIR,
) -> Tuple[str, str]:
    """Generate HTML + JSON reports. Returns (html_path, json_path)."""
    date_dir = os.path.join(output_dir, _date_subdir())
    os.makedirs(date_dir, exist_ok=True)
    slug = _time_slug()
    html_path = os.path.join(date_dir, f"dxsim-{slug}-review.html")
    json_path = os.path.join(date_dir, f"dxsim-{slug}.json")

    scenario_map = {s["id"]: s for s in scenarios}
    passed_count = sum(1 for r in results if r.get("pass"))
    total = len(results)

    # --- Build sidebar items ---
    sidebar_items = []
    for idx, r in enumerate(results):
        sid = r.get("scenario_id", "?")
        sc = scenario_map.get(sid, {})
        title = sc.get("title", sid)
        passed = r.get("pass", False)
        score = r.get("combined_score", -1)
        sidebar_items.append({
            "idx": idx,
            "sid": sid,
            "title": title,
            "passed": passed,
            "score": score,
        })

    # --- Build per-scenario panels ---
    panels_html = []
    for idx, r in enumerate(results):
        sid = r.get("scenario_id", "?")
        sc = scenario_map.get(sid, {})
        title = sc.get("title", sid)
        passed = r.get("pass", False)
        error = r.get("error")
        suggestions = r.get("suggestions", [])
        tags = sc.get("tags", [])
        complexity = sc.get("complexity", "?")
        time_s = r.get("diagnosis_time_s", 0)
        score = r.get("combined_score", -1)

        active = ' active' if idx == 0 else ''
        p = [f'<div class="scenario-panel{active}" id="panel-{idx}">']

        # Header
        p.append('<div class="scenario-header">')
        p.append(f'<h2>{_esc(sid)} — {_esc(title)} {_badge("PASS" if passed else "FAIL")}</h2>')
        p.append(f'<div class="tags">{" ".join(_tag_badge(t) for t in tags)}</div>')
        p.append(
            f'<div class="scenario-meta">'
            f'<span>复杂度: <b>{_esc(complexity)}</b></span>'
            f'<span>用时: <b>{time_s}s</b></span>'
            f'<span>评分: {_score_badge(score)}</span>'
            f'<span>建议数: <b>{len(suggestions)}</b></span>'
            f'</div>'
        )
        p.append('</div>')

        if error:
            p.append(f'<div class="fail-detail">Error: {_esc(error)}</div>')

        # Context section: record + KB/cases side by side
        has_kb = bool(sc.get("knowledge_items"))
        has_cases = bool(sc.get("prior_cases"))
        has_context = has_kb or has_cases

        if has_context:
            p.append('<div class="two-col">')

        # Left: input record
        col_class = '' if not has_context else ''
        p.append('<div class="section-card">')
        p.append('<div class="section-card-header">输入病历</div>')
        p.append(f'<div class="section-card-body">{_build_record_html(r.get("record_fields", sc.get("record", {})))}</div>')
        p.append('</div>')

        # Right: KB + prior cases (if any)
        if has_context:
            p.append('<div>')
            if has_kb:
                p.append('<div class="section-card">')
                p.append(f'<div class="section-card-header">注入知识库 ({len(sc.get("knowledge_items", []))}条)</div>')
                p.append(f'<div class="section-card-body">{_build_kb_html(sc)}</div>')
                p.append('</div>')
            if has_cases:
                p.append('<div class="section-card">')
                p.append(f'<div class="section-card-header">历史病例记忆 ({len(sc.get("prior_cases", []))}例)</div>')
                p.append(f'<div class="section-card-body">{_build_prior_cases_html(sc, suggestions)}</div>')
                p.append('</div>')
            p.append('</div>')

        if has_context:
            p.append('</div>')  # close two-col

        # Prior cases impact (shown below two-col for full width when cases exist)
        # Already included inside _build_prior_cases_html

        # Suggestions output
        p.append('<div class="section-card">')
        p.append(f'<div class="section-card-header"><span>AI诊断建议</span><span>{len(suggestions)}条</span></div>')
        if suggestions:
            p.append(f'<div class="section-card-body">{_build_suggestions_html(suggestions, sc.get("knowledge_items", []))}</div>')
        else:
            p.append('<div class="section-card-body"><div class="fail-detail">无建议生成</div></div>')
        p.append('</div>')

        # Counterfactual baseline comparison (if exists)
        baseline_sug = r.get("baseline_suggestions", [])
        if baseline_sug:
            p.append('<div class="trace-box counterfactual-trace">')
            p.append('<div class="trace-header">反事实对比：无注入 vs 有注入</div>')
            p.append('<div class="trace-body">')
            p.append('<div class="two-col">')
            # Baseline column
            p.append('<div>')
            p.append('<div class="trace-subtitle">基线（无 KB / 无病例记忆）</div>')
            for bs in baseline_sug:
                sec_labels = {"differential": "鉴别", "workup": "检查", "treatment": "治疗"}
                sec = sec_labels.get(bs.get("section", ""), "")
                content = bs.get("content", "")[:50]
                p.append(f'<div class="trace-item">[{_esc(sec)}] {_esc(content)}</div>')
            p.append('</div>')
            # Full column
            p.append('<div>')
            p.append('<div class="trace-subtitle">完整（含 KB + 病例记忆）</div>')
            for fs in suggestions:
                sec_labels = {"differential": "鉴别", "workup": "检查", "treatment": "治疗"}
                sec = sec_labels.get(fs.get("section", ""), "")
                content = fs.get("content", "")[:50]
                p.append(f'<div class="trace-item">[{_esc(sec)}] {_esc(content)}</div>')
            p.append('</div>')
            p.append('</div>')  # close two-col
            # Show diffs
            t6 = r.get("validation", {}).get("tier6_counterfactual", {})
            diffs = t6.get("diffs", [])
            if diffs:
                p.append('<div class="trace-subtitle" style="margin-top:12px">因果差异：</div>')
                for d in diffs:
                    dtype = "KB" if d["type"] == "kb" else "病例"
                    title = d.get("title", f'Case {d.get("case_idx", "?")}')
                    causal = d.get("causal", False)
                    new = d.get("new_in_full", [])
                    both = d.get("in_both", [])
                    absent = d.get("absent", [])
                    icon = "✓" if causal else "✗"
                    cls = "pass" if causal else "fail"
                    p.append(f'<div class="check-item {cls}">')
                    p.append(f'{icon} [{dtype}] {_esc(title)}: ')
                    if new:
                        p.append(f'<b>因果新增</b>={", ".join(_esc(n) for n in new)} ')
                    if both:
                        p.append(f'<span style="color:#666">两者都有={", ".join(_esc(b) for b in both)}</span> ')
                    if absent:
                        p.append(f'<span style="color:#dc3545">缺失={", ".join(_esc(a) for a in absent)}</span>')
                    p.append('</div>')
            p.append('</div></div>')

        # KB citation trace (prominent, between suggestions and validation)
        validation = r.get("validation", {})
        kb_trace = _build_kb_citation_trace_html(
            validation,
            sc.get("knowledge_items", []),
            suggestions,
        )
        if kb_trace:
            p.append(kb_trace)

        # Case influence trace
        case_trace = _build_case_influence_trace_html(validation, sc)
        if case_trace:
            p.append(case_trace)

        # Validation
        if validation:
            p.append('<div class="section-card">')
            p.append('<div class="section-card-header">验证结果</div>')
            p.append(f'<div class="section-card-body">{_build_checks_html(validation)}</div>')
            p.append('</div>')

        p.append('</div>')  # close panel
        panels_html.append("\n".join(p))

    # --- JavaScript for tab switching ---
    js = """\
function switchTab(idx) {
  document.querySelectorAll('.sidebar-item').forEach(function(el) { el.classList.remove('active'); });
  document.querySelectorAll('.scenario-panel').forEach(function(el) { el.classList.remove('active'); });
  document.getElementById('tab-' + idx).classList.add('active');
  document.getElementById('panel-' + idx).classList.add('active');
}
"""

    # --- Assemble HTML ---
    html_parts = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>诊断模拟报告 — {_human_date()}</title>',
        f'<style>{_CSS}</style></head><body>',
        '<div class="layout">',
    ]

    # Sidebar
    html_parts.append('<div class="sidebar">')
    html_parts.append('<div class="sidebar-header">')
    html_parts.append('<h1>诊断模拟报告</h1>')
    html_parts.append(f'<div class="meta">{_human_date()} · <code>{_esc(server_url)}</code></div>')
    html_parts.append(f'<div class="sidebar-stats">')
    html_parts.append(f'<span class="stat pass-stat">✓ {passed_count} 通过</span>')
    fail_count = total - passed_count
    if fail_count:
        html_parts.append(f'<span class="stat fail-stat">✗ {fail_count} 失败</span>')
    html_parts.append(f'<span class="stat">共 {total} 场景</span>')
    html_parts.append('</div></div>')

    html_parts.append('<div class="sidebar-list">')
    for item in sidebar_items:
        active = ' active' if item["idx"] == 0 else ''
        status_cls = 'passed' if item["passed"] else 'failed'
        html_parts.append(
            f'<div class="sidebar-item {status_cls}{active}" id="tab-{item["idx"]}" '
            f'onclick="switchTab({item["idx"]})">'
            f'<div class="status-dot"></div>'
            f'<span class="sid">{_esc(item["sid"])}</span>'
            f'<span class="title">{_esc(item["title"])}</span>'
            f'<span class="score">{item["score"]}</span>'
            f'</div>'
        )
    html_parts.append('</div></div>')

    # Main content
    html_parts.append('<div class="main">')
    html_parts.append("\n".join(panels_html))
    html_parts.append('</div>')

    html_parts.append('</div>')  # close layout
    html_parts.append(f'<script>{js}</script>')
    html_parts.append('</body></html>')

    html_content = "\n".join(html_parts)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # --- JSON ---
    json_data = {
        "timestamp": _human_date(),
        "server_url": server_url,
        "passed": passed_count,
        "total": total,
        "results": results,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    return html_path, json_path
