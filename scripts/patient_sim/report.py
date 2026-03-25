"""Report generation for patient simulation runs.

Produces both HTML and JSON reports from simulation results.
Uses only stdlib + json + sqlite3 — no application imports.
"""
from __future__ import annotations

import html
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = str(_REPO_ROOT / "reports" / "patient_sim")


def _timestamp() -> str:
    """ISO 8601 timestamp for filenames (UTC, no colons)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _human_date() -> str:
    """Human-readable date for report title."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _tier1_summary(result: dict) -> str:
    t1 = result.get("tier1", {})
    return "PASS" if t1.get("pass") else "FAIL"


def _tier2_dim_scores(result: dict) -> Dict[str, int]:
    """Return per-dimension scores from tier2, -1 if unavailable."""
    t2 = result.get("tier2", {})
    dims = t2.get("dimensions", {})
    # Support both prefixed (dim1_xxx) and unprefixed (xxx) key formats
    _MAP = {
        "interview_policy": "dim2_interview_policy",
        "disclosure": "dim3_disclosure",
        "extraction": "dim4_extraction_accuracy",
        "record_quality": "dim5_record_quality",
    }
    out: Dict[str, int] = {}
    for short, prefixed in _MAP.items():
        d = dims.get(prefixed, dims.get(short, {}))
        out[short] = d.get("score", -1)
    return out


def _tier2_summary(result: dict) -> int:
    """Return combined_score from tier2 (0-100), or -1 if unavailable."""
    t2 = result.get("tier2", {})
    return t2.get("combined_score", -1)


def _tier3_summary(result: dict) -> str:
    t3 = result.get("tier3", {})
    score = t3.get("score", -1)
    if score < 0:
        return "N/A"
    return f"{score}/10"


def _overall_result(result: dict) -> str:
    t1 = result.get("tier1", {}).get("pass", False)
    t2 = result.get("tier2", {}).get("pass", False)
    return "PASS" if (t1 and t2) else "FAIL"


def _dim_score_badge(score: int) -> str:
    """Return a compact coloured badge for a dimension score (0-100).

    Thresholds: green >= 80, yellow >= 60, red < 60.
    """
    if score < 0:
        return '<span class="badge na">—</span>'
    if score >= 80:
        cls = "score-green"
    elif score >= 60:
        cls = "score-yellow"
    else:
        cls = "score-red"
    return f'<span class="badge {cls}">{score}</span>'


def _score_badge(score: int) -> str:
    """Return a coloured badge for a 0-100 combined score."""
    if score < 0:
        return '<span class="badge na">N/A</span>'
    if score >= 80:
        cls = "score-green"
    elif score >= 60:
        cls = "score-yellow"
    else:
        cls = "score-red"
    return f'<span class="badge {cls}">{score}/100</span>'


def _badge(text: str) -> str:
    """Return a coloured badge span."""
    if text == "PASS":
        return '<span class="badge pass">通过</span>'
    elif text == "FAIL":
        return '<span class="badge fail">未通过</span>'
    return f'<span class="badge na">{_esc(text)}</span>'


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       line-height: 1.6; color: #1a1a1a; background: #f5f5f5; padding: 24px; max-width: 1100px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin-bottom: 4px; }
h2 { font-size: 1.2rem; margin: 32px 0 12px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
h3 { font-size: 1rem; margin: 16px 0 8px; }
.meta { color: #666; font-size: 0.85rem; margin-bottom: 20px; }
.meta code { background: #e8e8e8; padding: 1px 5px; border-radius: 3px; font-size: 0.82rem; }
table { border-collapse: collapse; width: 100%; margin-bottom: 16px; background: #fff; border-radius: 6px; overflow: hidden; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; font-size: 0.88rem; }
th { background: #fafafa; font-weight: 600; }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.78rem; font-weight: 600; }
.badge.pass { background: #d4edda; color: #155724; }
.badge.fail { background: #f8d7da; color: #721c24; }
.badge.na   { background: #e2e3e5; color: #383d41; }
details { margin: 8px 0 20px; background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; }
details summary { cursor: pointer; padding: 10px 14px; font-weight: 600; font-size: 0.9rem; background: #fafafa; border-radius: 6px; }
details[open] summary { border-bottom: 1px solid #e0e0e0; border-radius: 6px 6px 0 0; }
.conversation { padding: 12px 16px; font-size: 0.85rem; }
.turn { margin-bottom: 10px; }
.turn-role { font-weight: 600; margin-bottom: 2px; }
.turn-role.system { color: #07C160; }
.turn-role.patient { color: #1a73e8; }
.turn-text { white-space: pre-wrap; color: #333; padding-left: 8px; border-left: 3px solid #e0e0e0; }
.checklist { font-size: 0.85rem; color: #555; margin-bottom: 12px; }
.fail-detail { background: #fff3cd; border-left: 3px solid #ffc107; padding: 8px 12px; margin: 8px 0; font-size: 0.85rem; border-radius: 0 4px 4px 0; }
nav.toc { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px 16px; margin-bottom: 24px; }
nav.toc a { color: #1a73e8; text-decoration: none; font-size: 0.88rem; }
nav.toc a:hover { text-decoration: underline; }
nav.toc ul { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; }
.persona-section { margin-bottom: 32px; }
.record-fields { padding: 12px 16px; font-size: 0.85rem; }
.record-field { margin-bottom: 8px; }
.record-field-name { font-weight: 600; color: #555; min-width: 100px; display: inline-block; }
.record-field-value { color: #333; }
.record-field-empty { color: #bbb; font-style: italic; }
.badge.score-green  { background: #d4edda; color: #155724; }
.badge.score-yellow { background: #fff3cd; color: #856404; }
.badge.score-red    { background: #f8d7da; color: #721c24; }
.scorecard { padding: 12px 16px; }
.dim-section { margin-bottom: 16px; border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden; }
.dim-header { background: #fafafa; font-weight: 600; font-size: 0.88rem; padding: 8px 12px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.dim-header:hover { background: #f0f0f0; }
.dim-body { padding: 10px 12px; font-size: 0.84rem; }
.topic-grid { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.topic-item { white-space: nowrap; }
.topic-item.covered { color: #155724; }
.topic-item.missed  { color: #dc3545; font-weight: 600; }
.fact-list { list-style: none; padding: 0; margin: 0; font-size: 0.84rem; }
.fact-list li { padding: 2px 0; }
.fact-list li.ok { color: #155724; }
.fact-list li.miss { color: #dc3545; font-weight: 600; }
.fact-critical-miss { background: #f8d7da; }
.fact-important-miss { background: #fff3cd; }
.nhc-section { margin-bottom: 8px; }
.nhc-section-title { font-weight: 600; margin-bottom: 2px; }
.nhc-checks { display: flex; flex-wrap: wrap; gap: 2px 14px; }
.nhc-check.ok   { color: #155724; }
.nhc-check.fail { color: #dc3545; font-weight: 600; }
.nhc-check.hint { color: #0d6efd; font-style: italic; }
.combined-score-bar { text-align: right; padding: 8px 12px; font-size: 0.9rem; border-top: 1px solid #e0e0e0; margin-top: 8px; }
.summary-dim { text-align: center !important; padding: 6px 8px !important; }
.summary-dim-header { text-align: center !important; font-size: 0.78rem !important; padding: 6px 8px !important; }
.importance-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.74rem; font-weight: 600; }
.importance-critical { background: #f8d7da; color: #721c24; }
.importance-important { background: #fff3cd; color: #856404; }
.importance-normal { background: #e2e3e5; color: #383d41; }
.hallucination-list { color: #dc3545; font-weight: 600; }
"""


# ---------------------------------------------------------------------------
# 5-dimension scorecard panels
# ---------------------------------------------------------------------------

def _build_dim_simulator_fidelity(dim: dict) -> str:
    """Dimension 1: 模拟器忠实度 — did patient volunteer the right facts?"""
    facts = dim.get("facts", {})
    score = dim.get("score", -1)
    if not facts and score < 0:
        return ""

    items: list[str] = []
    for fact_id, info in facts.items():
        disclosed = info.get("disclosed", False)
        cls = "ok" if disclosed else "miss"
        icon = "✓" if disclosed else "✗"
        items.append(f'<li class="{cls}">{icon} {_esc(fact_id)}</li>')

    score_html = _dim_score_badge(score)
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>1. 模拟器忠实度</span>{score_html}</summary>'
        f'<div class="dim-body"><ul class="fact-list">{"".join(items)}</ul></div>'
        '</details>'
    )


def _build_dim_interview_policy(dim: dict) -> str:
    """Dimension 2: 问诊策略 — did the AI ask about each must-elicit topic?"""
    topics = dim.get("topics", {})
    score = dim.get("score", -1)
    if not topics and score < 0:
        return ""

    items: list[str] = []
    for topic, ok in topics.items():
        cls = "covered" if ok else "missed"
        icon = "✓" if ok else "✗"
        items.append(f'<span class="topic-item {cls}">{icon} {_esc(topic)}</span>')

    score_html = _dim_score_badge(score)
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>2. 问诊策略</span>{score_html}</summary>'
        f'<div class="dim-body"><div class="topic-grid">{"".join(items)}</div></div>'
        '</details>'
    )


def _build_dim_disclosure(dim: dict) -> str:
    """Dimension 3: 信息披露 — were critical/important facts mentioned in conversation?"""
    facts = dim.get("facts", {})
    score = dim.get("score", -1)
    if not facts and score < 0:
        return ""

    # Filter to critical + important only
    filtered = {
        fid: info for fid, info in facts.items()
        if info.get("importance", "normal") in ("critical", "important")
    }
    if not filtered:
        # Fall back to showing all if no importance info
        filtered = facts

    rows: list[str] = []
    for fid, info in filtered.items():
        importance = info.get("importance", "normal")
        disclosed = info.get("disclosed", False)
        icon = "✓" if disclosed else "✗"

        imp_cls = f"importance-{importance}"
        imp_label = {"critical": "关键", "important": "重要", "normal": "一般"}.get(importance, importance)

        row_cls = ""
        if not disclosed and importance == "critical":
            row_cls = "fact-critical-miss"
        elif not disclosed and importance == "important":
            row_cls = "fact-important-miss"

        rows.append(
            f'<tr class="{row_cls}">'
            f'<td>{_esc(fid)}</td>'
            f'<td><span class="importance-badge {imp_cls}">{_esc(imp_label)}</span></td>'
            f'<td><span class="badge {"pass" if disclosed else "fail"}">{icon}</span></td>'
            f'</tr>'
        )

    score_html = _dim_score_badge(score)
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>3. 信息披露</span>{score_html}</summary>'
        '<div class="dim-body">'
        '<table><tr><th>事实ID</th><th>重要性</th><th>对话中提到</th></tr>'
        + "".join(rows)
        + '</table></div>'
        '</details>'
    )


def _build_dim_extraction(dim: dict) -> str:
    """Dimension 4: 提取准确度 — did the system capture disclosed facts?"""
    facts = dim.get("facts", {})
    score = dim.get("score", -1)
    if not facts and score < 0:
        return ""

    # Only show facts where disclosed=true
    disclosed_facts = {
        fid: info for fid, info in facts.items()
        if info.get("disclosed", False)
    }

    rows: list[str] = []
    for fid, info in disclosed_facts.items():
        importance = info.get("importance", "normal")
        disclosed = info.get("disclosed", False)
        captured = info.get("captured", False)
        found_in = info.get("found_in", "")

        imp_cls = f"importance-{importance}"
        imp_label = {"critical": "关键", "important": "重要", "normal": "一般"}.get(importance, importance)

        disclosed_icon = "✓" if disclosed else "✗"
        captured_icon = "✓" if captured else "✗"

        # Red highlight for disclosed but not captured
        row_cls = ""
        if disclosed and not captured:
            if importance == "critical":
                row_cls = "fact-critical-miss"
            else:
                row_cls = "fact-important-miss"

        rows.append(
            f'<tr class="{row_cls}">'
            f'<td>{_esc(fid)}</td>'
            f'<td><span class="importance-badge {imp_cls}">{_esc(imp_label)}</span></td>'
            f'<td><span class="badge {"pass" if disclosed else "fail"}">{disclosed_icon}</span></td>'
            f'<td><span class="badge {"pass" if captured else "fail"}">{captured_icon}</span></td>'
            f'<td>{_esc(found_in) if found_in else "—"}</td>'
            f'</tr>'
        )

    score_html = _dim_score_badge(score)
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>4. 提取准确度</span>{score_html}</summary>'
        '<div class="dim-body">'
        '<table><tr><th>事实ID</th><th>重要性</th><th>已披露</th><th>已提取</th><th>所在字段</th></tr>'
        + "".join(rows)
        + '</table></div>'
        '</details>'
    )


def _build_dim_record_quality(dim: dict) -> str:
    """Dimension 5: 记录质量 — CC checks and hallucinations."""
    score = dim.get("score", -1)
    cc = dim.get("chief_complaint", {})
    hallucinations = dim.get("hallucinations", [])
    if score < 0 and not cc and not hallucinations:
        return ""

    parts: list[str] = []

    # Chief complaint checks
    if cc:
        length = cc.get("length", 0)
        max_chars = cc.get("max_chars", 20)
        has_dur = cc.get("has_duration", False)
        cc_pass = cc.get("pass", False)
        length_ok = length <= max_chars

        checks: list[str] = []
        checks.append(f'<span class="nhc-check {"ok" if length_ok else "fail"}">字数 {length}/{max_chars} {"✓" if length_ok else "✗"}</span>')
        checks.append(f'<span class="nhc-check {"ok" if has_dur else "fail"}">包含病程 {"✓" if has_dur else "✗"}</span>')
        parts.append(
            '<div class="nhc-section">'
            '<div class="nhc-section-title">主诉检查</div>'
            f'<div class="nhc-checks">{"".join(checks)}</div>'
            '</div>'
        )

    # Hallucinations
    if hallucinations:
        items = "".join(f"<li>{_esc(h)}</li>" for h in hallucinations)
        parts.append(
            '<div class="nhc-section">'
            '<div class="nhc-section-title">幻觉</div>'
            f'<ul class="hallucination-list">{items}</ul>'
            '</div>'
        )
    else:
        parts.append(
            '<div class="nhc-section">'
            '<span class="nhc-check ok">幻觉检查：✓ 未发现</span>'
            '</div>'
        )

    score_html = _dim_score_badge(score)
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>5. 记录质量</span>{score_html}</summary>'
        f'<div class="dim-body">{"".join(parts)}</div>'
        '</details>'
    )


def _build_scorecard(result: dict) -> str:
    """Build the 5-dimension scorecard for a persona's tier2 results."""
    t2 = result.get("tier2", {})
    if not t2:
        return "<p><em>无评估数据</em></p>"

    combined = t2.get("combined_score", -1)
    dims = t2.get("dimensions", {})

    if not dims:
        return "<p><em>无评估数据</em></p>"

    parts: list[str] = ['<div class="scorecard">']

    dim2 = _build_dim_interview_policy(dims.get("dim2_interview_policy", dims.get("interview_policy", {})))
    if dim2:
        parts.append(dim2)

    dim3 = _build_dim_disclosure(dims.get("dim3_disclosure", dims.get("disclosure", {})))
    if dim3:
        parts.append(dim3)

    dim4 = _build_dim_extraction(dims.get("dim4_extraction_accuracy", dims.get("extraction", {})))
    if dim4:
        parts.append(dim4)

    dim5 = _build_dim_record_quality(dims.get("dim5_record_quality", dims.get("record_quality", {})))
    if dim5:
        parts.append(dim5)

    parts.append('</div>')  # .scorecard

    if combined >= 0:
        score_cls = "score-green" if combined >= 80 else ("score-yellow" if combined >= 60 else "score-red")
        parts.append(
            f'<div class="combined-score-bar">'
            f'综合评分: <span class="badge {score_cls}" style="font-size:0.9rem">{combined}/100</span>'
            f'</div>'
        )

    return "\n".join(parts)


def _build_conversation_block(result: dict) -> str:
    conversation = result.get("conversation", [])
    if not conversation:
        return "<p><em>无对话记录</em></p>"

    turns = []
    for turn in conversation:
        role = turn.get("role", "unknown")
        text = turn.get("content", turn.get("text", ""))
        role_label = "AI助手" if role == "system" else "患者"
        cls = "system" if role == "system" else "patient"
        turns.append(
            f'<div class="turn">'
            f'<div class="turn-role {cls}">{_esc(role_label)}</div>'
            f'<div class="turn-text">{_esc(text)}</div>'
            f'</div>'
        )

    return '<div class="conversation">' + "".join(turns) + "</div>"


_SOAP_LABELS = {
    "chief_complaint": "主诉", "present_illness": "现病史", "past_history": "既往史",
    "allergy_history": "过敏史", "family_history": "家族史", "personal_history": "个人史",
    "marital_reproductive": "婚育史", "physical_exam": "体格检查", "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查", "diagnosis": "诊断", "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
}

_SOAP_FIELDS = list(_SOAP_LABELS.keys())


def _load_medical_record(record_id: int, db_path: str) -> Dict[str, str]:
    """Load SOAP fields from DB for display in report."""
    if not record_id or not db_path:
        return {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cols = ", ".join(_SOAP_FIELDS)
        row = conn.execute(f"SELECT {cols} FROM medical_records WHERE id = ?", (record_id,)).fetchone()
        conn.close()
        if row is None:
            return {}
        return {f: (row[f] or "") for f in _SOAP_FIELDS}
    except Exception:
        return {}


def _build_medical_record_block(record: Dict[str, str]) -> str:
    """Render SOAP fields from DB as HTML."""
    if not record:
        return "<p><em>未找到病历记录</em></p>"
    parts = ['<div class="record-fields">']
    for field in _SOAP_FIELDS:
        value = record.get(field, "")
        label = _SOAP_LABELS.get(field, field)
        if value and value.strip():
            parts.append(
                f'<div class="record-field">'
                f'<span class="record-field-name">{_esc(label)}：</span>'
                f'<span class="record-field-value">{_esc(value)}</span></div>'
            )
        else:
            parts.append(
                f'<div class="record-field">'
                f'<span class="record-field-name">{_esc(label)}：</span>'
                f'<span class="record-field-empty">未采集</span></div>'
            )
    parts.append("</div>")
    return "\n".join(parts)


def _build_html(results: List[dict], patient_llm: str, server_url: str, db_path: str = "", ai_analyses: Optional[List[dict]] = None) -> str:
    date = _human_date()
    p: list[str] = []

    p.append(f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>")
    p.append(f"<title>患者模拟测试报告 — {_esc(date)}</title>")
    p.append(f"<style>{_CSS}</style></head><body>")

    p.append(f"<h1>患者模拟测试报告</h1>")
    p.append(f'<div class="meta">{_esc(date)} · 患者模型: <code>{_esc(patient_llm)}</code> · '
             f'服务器: <code>{_esc(server_url)}</code> · 测试角色: {len(results)}</div>')

    # Navigation
    p.append('<nav class="toc"><strong>快速跳转：</strong> <ul>')
    for r in results:
        persona = r.get("persona", {})
        pid = persona.get("id", "?")
        name = persona.get("name", "?")
        anchor = f"persona-{pid}"
        result_icon = "✓" if r.get("pass") else "✗"
        p.append(f'<li><a href="#{anchor}">{result_icon} {_esc(pid)} {_esc(name)}</a></li>')
    p.append('</ul></nav>')

    # Summary table — 5 dimension mini-columns
    p.append(
        "<table><tr>"
        "<th>角色</th><th>轮次</th><th>数据库</th>"
        '<th class="summary-dim-header">问诊</th>'
        '<th class="summary-dim-header">披露</th>'
        '<th class="summary-dim-header">提取</th>'
        '<th class="summary-dim-header">质量</th>'
        "<th>结果</th></tr>"
    )
    for r in results:
        persona = r.get("persona", {})
        pid = _esc(persona.get("id", "?"))
        name = _esc(persona.get("name", "?"))
        condition = _esc(persona.get("condition", ""))
        anchor = f"persona-{persona.get('id', '?')}"
        turns = r.get("turns", "?")
        db = _badge(_tier1_summary(r))
        dim_scores = _tier2_dim_scores(r)
        overall = _badge(_overall_result(r))

        p.append(
            f'<tr><td><a href="#{anchor}" style="text-decoration:none;color:inherit">'
            f'<strong>{pid} {name}</strong><br><small>{condition}</small></a></td>'
            f'<td>{turns}</td><td>{db}</td>'
            f'<td class="summary-dim">{_dim_score_badge(dim_scores["interview_policy"])}</td>'
            f'<td class="summary-dim">{_dim_score_badge(dim_scores["disclosure"])}</td>'
            f'<td class="summary-dim">{_dim_score_badge(dim_scores["extraction"])}</td>'
            f'<td class="summary-dim">{_dim_score_badge(dim_scores["record_quality"])}</td>'
            f'<td>{overall}</td></tr>'
        )
    p.append("</table>")

    # Per-persona details (each in a collapsible section)
    for r in results:
        persona = r.get("persona", {})
        pid = persona.get("id", "?")
        name = persona.get("name", "?")
        condition = persona.get("condition", "")
        label = f"{pid} {name}"
        anchor = f"persona-{pid}"
        result_icon = "✓ 通过" if r.get("pass") else "✗ 未通过"

        p.append(f'<div class="persona-section" id="{anchor}">')
        p.append(f"<h2>{_esc(label)} — {_esc(condition)} [{result_icon}]</h2>")

        # Medical Record — use snapshot from JSON (survives cleanup), fall back to DB
        record_id = r.get("record_id")
        record = r.get("soap_snapshot", {})
        if not record and record_id and db_path:
            record = _load_medical_record(record_id, db_path)
        if record:
            p.append(f"<details><summary>病历记录</summary>")
            p.append(_build_medical_record_block(record))
            p.append("</details>")

        # Scorecard (5-dimension evaluation)
        t2 = r.get("tier2", {})
        combined = t2.get("combined_score", -1)
        score_label = f" — {combined}/100" if combined >= 0 else ""
        p.append(f'<details open><summary>评估记分卡{_esc(score_label)}</summary>')
        p.append(_build_scorecard(r))
        p.append("</details>")

        # DB check failures
        t1 = r.get("tier1", {})
        if not t1.get("pass"):
            p.append("<details open><summary>数据库检查失败</summary><div style='padding:12px 16px'>")
            for check_name, check in t1.get("checks", {}).items():
                if not check.get("pass"):
                    p.append(f'<div class="fail-detail"><strong>{_esc(check_name)}</strong>: '
                             f'{_esc(check.get("detail", "unknown"))}</div>')
            p.append("</div></details>")

        # Quality
        t3 = r.get("tier3", {})
        if t3.get("score", -1) >= 0:
            valid_n = t3.get("valid_count", "?")
            total_n = t3.get("judge_count", "?")
            def _fmt(key: str) -> str:
                vals = t3.get(key, [])
                return ", ".join(str(s) for s in vals) if vals else "—"
            p.append(f"<details><summary>质量评分 — {t3['score']}/10 中位数（{valid_n}/{total_n} 位评审）</summary>")
            p.append('<div style="padding:12px 16px">')
            p.append(
                f"<table><tr><th>维度</th><th>中位数</th><th>全部评分</th></tr>"
                f"<tr><td>综合</td><td><strong>{t3['score']}/10</strong></td><td>{_esc(_fmt('all_scores'))}</td></tr>"
                f"<tr><td>完整性</td><td>{t3.get('completeness', '?')}/10</td><td>{_esc(_fmt('all_completeness'))}</td></tr>"
                f"<tr><td>相关性</td><td>{t3.get('appropriateness', '?')}/10</td><td>{_esc(_fmt('all_appropriateness'))}</td></tr>"
                f"<tr><td>沟通质量</td><td>{t3.get('communication', '?')}/10</td><td>{_esc(_fmt('all_communication'))}</td></tr>"
                f"</table>"
            )
            explanations = t3.get("all_explanations", [])
            if explanations:
                p.append('<div style="font-size:0.82rem;color:#666;margin-top:4px">')
                for i, exp in enumerate(explanations):
                    if exp and exp != "judge error":
                        p.append(f"<div>评审 {i+1}：<em>{_esc(exp[:120])}</em></div>")
                p.append("</div>")
            p.append("</div></details>")

        # Anomalies
        t4 = r.get("tier4", {})
        anomalies = t4.get("anomalies", [])
        if anomalies:
            high = t4.get("high", 0)
            medium = t4.get("medium", 0)
            low = t4.get("low", 0)
            counts = []
            if high: counts.append(f'{high} 高')
            if medium: counts.append(f'{medium} 中')
            if low: counts.append(f'{low} 低')
            p.append(f"<details open><summary>异常审查（{', '.join(counts)}）</summary>")
            p.append('<div style="padding:12px 16px">')
            p.append("<table><tr><th>严重性</th><th>类型</th><th>详情</th></tr>")
            for a in sorted(anomalies, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 3)):
                sev = a.get("severity", "low")
                sev_cls = "fail" if sev == "high" else ("na" if sev == "medium" else "pass")
                sev_label = {"high": "高", "medium": "中", "low": "低"}.get(sev, sev)
                p.append(
                    f"<tr><td><span class='badge {sev_cls}'>{_esc(sev_label)}</span></td>"
                    f"<td>{_esc(a.get('type', ''))}</td>"
                    f"<td>{_esc(a.get('detail', ''))}</td></tr>"
                )
            p.append("</table>")
            summary = t4.get("summary", "")
            if summary:
                p.append(f"<p><em>{_esc(summary)}</em></p>")
            p.append("</div></details>")
        else:
            p.append(f'<div class="checklist">异常审查：✓ 未发现异常</div>')

        # Conversation
        p.append(f"<details><summary>对话记录（{r.get('turns', '?')} 轮）</summary>")
        p.append(_build_conversation_block(r))
        p.append("</details>")

        p.append("</div>")  # .persona-section

    # AI Analysis section
    if ai_analyses:
        p.append('<h2 id="ai-analysis">AI 专家分析与建议</h2>')
        for i, analysis in enumerate(ai_analyses):
            model = _esc(analysis.get("model", f"分析师 {i+1}"))
            text = analysis.get("analysis", "")
            # Convert markdown-ish text to HTML paragraphs
            html_text = ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    html_text += "<br>"
                elif line.startswith("### "):
                    html_text += f"<h4>{_esc(line[4:])}</h4>"
                elif line.startswith("## "):
                    html_text += f"<h3>{_esc(line[3:])}</h3>"
                elif line.startswith("- "):
                    html_text += f"<li>{_esc(line[2:])}</li>"
                else:
                    html_text += f"<p>{_esc(line)}</p>"
            p.append(
                f'<details open>'
                f'<summary>{model}</summary>'
                f'<div style="padding:12px 16px;font-size:0.88rem;line-height:1.7">{html_text}</div>'
                f'</details>'
            )

        # Add analysis link to navigation
        # (nav was already built, so we append via JS)
        p.append('<script>document.querySelector("nav.toc ul")?.insertAdjacentHTML("beforeend", '
                 '"<li><a href=\\"#ai-analysis\\">📋 AI专家分析</a></li>")</script>')

    p.append("</body></html>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def _build_json(results: List[dict], patient_llm: str, server_url: str) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "patient_llm": patient_llm,
        "server_url": server_url,
        "persona_count": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_reports(
    results: List[dict],
    patient_llm: str,
    server_url: str,
    output_dir: Optional[str] = None,
    db_path: str = "",
    ai_analyses: Optional[List[dict]] = None,
) -> Tuple[str, str]:
    """Generate HTML and JSON reports for a simulation run.

    Returns:
        Tuple of (html_path, json_path).
    """
    out = Path(output_dir or _DEFAULT_OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    html_name = f"sim-{ts}.html"
    json_name = f"sim-{ts}.json"

    html_path = out / html_name
    json_path = out / json_name

    html_content = _build_html(results, patient_llm, server_url, db_path=db_path, ai_analyses=ai_analyses)
    html_path.write_text(html_content, encoding="utf-8")

    json_data = _build_json(results, patient_llm, server_url)
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return str(html_path), str(json_path)
