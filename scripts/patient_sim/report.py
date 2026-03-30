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


def _date_subdir() -> str:
    """Date string for subdirectory (yyyymmdd), local time."""
    return datetime.now().strftime("%Y%m%d")


def _time_slug() -> str:
    """Time string for filename (hh-mm-ss), local time."""
    return datetime.now().strftime("%H-%M-%S")


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


def _score_badge(score: int) -> str:
    """Return a coloured badge for a 0-100 combined score."""
    if score < 0:
        return '<span class="badge na">N/A</span>'
    if score >= 70:
        cls = "score-green"
    elif score >= 50:
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
.scorecard { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 12px 16px; }
@media (max-width: 760px) { .scorecard { grid-template-columns: 1fr; } }
.panel { border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden; }
.panel-header { background: #fafafa; font-weight: 600; font-size: 0.88rem; padding: 8px 12px; border-bottom: 1px solid #e0e0e0; display: flex; justify-content: space-between; align-items: center; }
.panel-body { padding: 10px 12px; font-size: 0.84rem; }
.panel-full { grid-column: 1 / -1; }
.topic-grid { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.topic-item { white-space: nowrap; }
.topic-item.covered { color: #155724; }
.topic-item.missed  { color: #dc3545; font-weight: 600; }
.fact-critical-miss { background: #f8d7da; }
.fact-important-miss { background: #fff3cd; }
.fact-wrong-field { background: #ffeeba; }
.nhc-section { margin-bottom: 8px; }
.nhc-section-title { font-weight: 600; margin-bottom: 2px; }
.nhc-checks { display: flex; flex-wrap: wrap; gap: 2px 14px; }
.nhc-check.ok   { color: #155724; }
.nhc-check.fail { color: #dc3545; font-weight: 600; }
.nhc-check.hint { color: #0d6efd; font-style: italic; }
"""


def _build_elicitation_panel(elicitation: dict) -> str:
    """Panel A: Elicitation — did the interview ask about each must-elicit topic?"""
    topics = elicitation.get("topics", {})
    if not topics:
        return ""
    covered = sum(1 for v in topics.values() if v)
    total = len(topics)
    score_str = f"{covered}/{total} 个话题已覆盖"

    items = []
    for topic, ok in topics.items():
        cls = "covered" if ok else "missed"
        icon = "✓" if ok else "✗"
        items.append(f'<span class="topic-item {cls}">{icon} {_esc(topic)}</span>')

    return (
        '<div class="panel">'
        '<div class="panel-header"><span>A. 问诊覆盖度 — AI是否询问了关键话题？</span>'
        f'<span class="badge {"score-green" if covered == total else "score-yellow" if covered >= total * 0.6 else "score-red"}">{_esc(score_str)}</span></div>'
        f'<div class="panel-body"><div class="topic-grid">{"".join(items)}</div></div>'
        '</div>'
    )


def _build_extraction_panel(extraction: dict) -> str:
    """Panel B: Extraction Fidelity — did the system capture each fact?"""
    facts = extraction.get("facts", {})
    if not facts:
        return ""

    # Count critical/important stats
    critical_total = 0
    critical_match = 0
    for _fid, info in facts.items():
        imp = info.get("importance", "normal")
        if imp == "critical":
            critical_total += 1
            if info.get("match"):
                critical_match += 1

    total = len(facts)
    matched = sum(1 for v in facts.values() if v.get("match"))
    score_str = f"{matched}/{total} 条事实已提取"
    if critical_total:
        score_str += f"（{critical_match}/{critical_total} 关键）"

    rows = []
    for fid, info in facts.items():
        importance = info.get("importance", "normal")
        expected_field = info.get("expected_field", "")
        found_in = info.get("found_in", "")
        match = info.get("match", False)

        icon = "✓" if match else "✗"
        if match:
            if found_in and expected_field and found_in != expected_field:
                row_cls = "fact-wrong-field"
            else:
                row_cls = ""
        elif importance == "critical":
            row_cls = "fact-critical-miss"
        elif importance == "important":
            row_cls = "fact-important-miss"
        else:
            row_cls = ""

        imp_badge = ""
        if importance == "critical":
            imp_badge = '<span class="badge fail">关键</span>'
        elif importance == "important":
            imp_badge = '<span class="badge na">重要</span>'
        else:
            imp_badge = '<span class="badge pass">一般</span>'

        rows.append(
            f'<tr class="{row_cls}">'
            f"<td>{_esc(fid)}</td>"
            f"<td>{imp_badge}</td>"
            f"<td>{_esc(expected_field)}</td>"
            f"<td>{_esc(found_in) if found_in else '—'}</td>"
            f'<td><span class="badge {"pass" if match else "fail"}">{icon}</span></td>'
            f"</tr>"
        )

    return (
        '<div class="panel panel-full">'
        '<div class="panel-header"><span>B. 提取准确度 — 系统是否正确提取？</span>'
        f'<span class="badge {"score-green" if matched == total else "score-yellow" if matched >= total * 0.6 else "score-red"}">{_esc(score_str)}</span></div>'
        '<div class="panel-body">'
        '<table><tr><th>事实</th><th>重要性</th><th>预期字段</th><th>实际字段</th><th>匹配</th></tr>'
        + "".join(rows) + '</table>'
        '</div></div>'
    )


def _build_nhc_panel(nhc: dict) -> str:
    """Panel C: NHC Record Quality — compliance with formatting standards."""
    score = nhc.get("score", -1)
    if score < 0:
        return ""

    sections: list[str] = []

    # chief_complaint
    cc = nhc.get("chief_complaint", {})
    if cc:
        checks = []
        length = cc.get("actual_length", cc.get("length", 0))
        max_chars = cc.get("max_chars", 20)
        has_dur = cc.get("has_duration", False)
        cc_pass = cc.get("length_ok", False) and cc.get("duration_ok", True)
        checks.append(f'<span class="nhc-check {"ok" if length <= max_chars else "fail"}">字数 {length}/{max_chars}</span>')
        checks.append(f'<span class="nhc-check {"ok" if has_dur else "fail"}">{"✓" if has_dur else "✗"} 包含病程</span>')
        checks.append(f'<span class="nhc-check {"ok" if cc_pass else "fail"}">{"✓ 通过" if cc_pass else "✗ 未通过"}</span>')
        sections.append(
            '<div class="nhc-section">'
            '<div class="nhc-section-title">主诉</div>'
            f'<div class="nhc-checks">{"".join(checks)}</div>'
            '</div>'
        )

    # present_illness — info hints, not compliance failures
    pi = nhc.get("present_illness", {})
    pi_subs = pi.get("subsections", {})
    if pi_subs:
        checks = []
        for sub, ok in pi_subs.items():
            if ok:
                checks.append(f'<span class="nhc-check ok">✓ {_esc(sub)}</span>')
            else:
                checks.append(f'<span class="nhc-check hint">ⓘ {_esc(sub)} — 待医生补充</span>')
        sections.append(
            '<div class="nhc-section">'
            '<div class="nhc-section-title">现病史 — 已收集信息覆盖度</div>'
            f'<div class="nhc-checks">{"".join(checks)}</div>'
            '</div>'
        )

    # past_history — info hints, not compliance failures
    ph = nhc.get("past_history", {})
    ph_subs = ph.get("subsections", {})
    if ph_subs:
        checks = []
        for sub, ok in ph_subs.items():
            if ok:
                checks.append(f'<span class="nhc-check ok">✓ {_esc(sub)}</span>')
            else:
                checks.append(f'<span class="nhc-check hint">ⓘ {_esc(sub)} — 待医生补充</span>')
        sections.append(
            '<div class="nhc-section">'
            '<div class="nhc-section-title">既往史 — 已收集信息覆盖度</div>'
            f'<div class="nhc-checks">{"".join(checks)}</div>'
            '</div>'
        )

    # Render any other top-level NHC sections generically
    _known_keys = {"score", "chief_complaint", "present_illness", "past_history"}
    for key, val in nhc.items():
        if key in _known_keys:
            continue
        if isinstance(val, dict) and "subsections" in val:
            subs = val["subsections"]
            checks = []
            for sub, ok in subs.items():
                cls = "ok" if ok else "fail"
                icon = "✓" if ok else "✗"
                checks.append(f'<span class="nhc-check {cls}">{icon} {_esc(sub)}</span>')
            sections.append(
                '<div class="nhc-section">'
                f'<div class="nhc-section-title">{_esc(key)}</div>'
                f'<div class="nhc-checks">{"".join(checks)}</div>'
                '</div>'
            )

    score_cls = "score-green" if score >= 70 else ("score-yellow" if score >= 50 else "score-red")
    return (
        '<div class="panel">'
        f'<div class="panel-header"><span>C. 病历规范性（门诊，卫医政发〔2010〕11号 第13条）</span>'
        f'<span class="badge {score_cls}">规范符合度: {score}/100</span></div>'
        f'<div class="panel-body">{"".join(sections)}</div>'
        '</div>'
    )


def _build_scorecard(result: dict) -> str:
    """Build the 3-panel scorecard for a persona's tier2 results."""
    t2 = result.get("tier2", {})
    if not t2:
        return "<p><em>无评估数据</em></p>"

    combined = t2.get("combined_score", -1)
    elicitation = t2.get("elicitation", {})
    extraction = t2.get("extraction", {})
    nhc = t2.get("nhc_compliance", {})

    # If no new-format data at all, show a fallback message
    if not elicitation and not extraction.get("facts") and not nhc:
        return "<p><em>无评估数据</em></p>"

    parts: list[str] = ['<div class="scorecard">']

    panel_a = _build_elicitation_panel(elicitation)
    if panel_a:
        parts.append(panel_a)

    panel_c = _build_nhc_panel(nhc)
    if panel_c:
        parts.append(panel_c)

    panel_b = _build_extraction_panel(extraction)
    if panel_b:
        parts.append(panel_b)

    parts.append('</div>')  # .scorecard

    if combined >= 0:
        score_cls = "score-green" if combined >= 70 else ("score-yellow" if combined >= 50 else "score-red")
        parts.append(
            f'<div style="text-align:right;padding:4px 16px 12px;font-size:0.9rem;">'
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


_FIELD_LABELS = {
    "chief_complaint": "主诉", "present_illness": "现病史", "past_history": "既往史",
    "allergy_history": "过敏史", "family_history": "家族史", "personal_history": "个人史",
    "marital_reproductive": "婚育史", "physical_exam": "体格检查", "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查", "diagnosis": "诊断", "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
}

_FIELD_KEYS = list(_FIELD_LABELS.keys())


def _load_medical_record(record_id: int, db_path: str) -> Dict[str, str]:
    """Load clinical record fields from DB for display in report."""
    if not record_id or not db_path:
        return {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cols = ", ".join(_FIELD_KEYS)
        row = conn.execute(f"SELECT {cols} FROM medical_records WHERE id = ?", (record_id,)).fetchone()
        conn.close()
        if row is None:
            return {}
        return {f: (row[f] or "") for f in _FIELD_KEYS}
    except Exception:
        return {}


def _build_medical_record_block(record: Dict[str, str]) -> str:
    """Render clinical record fields from DB as HTML."""
    if not record:
        return "<p><em>未找到病历记录</em></p>"
    parts = ['<div class="record-fields">']
    for field in _FIELD_KEYS:
        value = record.get(field, "")
        label = _FIELD_LABELS.get(field, field)
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


def _build_html(results: List[dict], patient_llm: str, server_url: str, db_path: str = "") -> str:
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

    # Summary table
    p.append("<table><tr><th>角色</th><th>轮次</th><th>数据库</th>"
             "<th>评分</th><th>质量</th><th>异常</th><th>结果</th></tr>")
    for r in results:
        persona = r.get("persona", {})
        pid = _esc(persona.get("id", "?"))
        name = _esc(persona.get("name", "?"))
        condition = _esc(persona.get("condition", ""))
        anchor = f"persona-{persona.get('id', '?')}"
        turns = r.get("turns", "?")
        db = _badge(_tier1_summary(r))
        score = _tier2_summary(r)
        score_html = _score_badge(score)
        qual = _tier3_summary(r)
        t4 = r.get("tier4", {})
        anomaly_count = len(t4.get("anomalies", []))
        anomaly_high = t4.get("high", 0)
        anomaly_str = "0"
        if anomaly_high:
            anomaly_str = f'<span class="badge fail">{anomaly_count}（{anomaly_high} 高）</span>'
        elif anomaly_count:
            anomaly_str = f'<span class="badge na">{anomaly_count}</span>'
        overall = _badge(_overall_result(r))
        p.append(
            f'<tr><td><a href="#{anchor}" style="text-decoration:none;color:inherit">'
            f'<strong>{pid} {name}</strong><br><small>{condition}</small></a></td>'
            f"<td>{turns}</td><td>{db}</td><td>{score_html}</td>"
            f"<td>{_esc(qual)}</td><td>{anomaly_str}</td><td>{overall}</td></tr>"
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

        # Medical Record from DB
        record_id = r.get("record_id")
        if record_id and db_path:
            record = _load_medical_record(record_id, db_path)
            p.append(f"<details><summary>病历记录（数据库 #{record_id}）</summary>")
            p.append(_build_medical_record_block(record))
            p.append("</details>")

        # Scorecard (3-axis evaluation)
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

_FIELD_CN = {
    "chief_complaint": "主诉", "present_illness": "现病史", "past_history": "既往史",
    "allergy_history": "过敏史", "family_history": "家族史", "personal_history": "个人史",
    "marital_reproductive": "婚育史", "department": "科室", "physical_exam": "体格检查",
    "specialist_exam": "专科检查", "auxiliary_exam": "辅助检查", "diagnosis": "诊断",
    "treatment_plan": "治疗方案", "orders_followup": "医嘱随访",
}

_REVIEW_CSS = """\
body{font-family:-apple-system,"Segoe UI",Roboto,Helvetica,sans-serif;max-width:1000px;margin:20px auto;padding:0 20px 0 180px;background:#fafafa;color:#1a1a1a;line-height:1.6}
h1{border-bottom:2px solid #333;padding-bottom:8px;font-size:1.5rem}
.summary-bar{display:flex;gap:16px;margin:12px 0;font-size:16px;font-weight:700}
.persona{border:1px solid #ddd;border-radius:8px;margin:20px 0;padding:16px;background:#fff}
.pass{border-left:4px solid #22c55e}.fail{border-left:4px solid #ef4444}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.badge{padding:2px 10px;border-radius:12px;font-size:13px;font-weight:600}
.badge-pass{background:#dcfce7;color:#166534}.badge-fail{background:#fee2e2;color:#991b1b}
.msg{margin:8px 0;padding:10px 14px;border-radius:12px;max-width:85%;line-height:1.6;font-size:14px;white-space:pre-wrap}
.ai{background:#f0f0f0;margin-right:auto}.patient{background:#dbeafe;margin-left:auto;text-align:right}
.record{background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;margin-top:8px;font-size:13px}
.record dt{font-weight:600;color:#475569;margin-top:8px}.record dd{margin:2px 0 0 0;color:#1e293b}
.persona-bg{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:12px;margin-bottom:12px;font-size:13px}
.persona-bg h3{margin:0 0 8px 0;font-size:14px;color:#166534}.persona-bg .label{font-weight:600;color:#15803d}
.fact-table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}
.fact-table th{background:#f1f5f9;text-align:left;padding:6px 8px;border:1px solid #e2e8f0}
.fact-table td{padding:6px 8px;border:1px solid #e2e8f0;vertical-align:top}
.fact-exact{background:#dcfce7}.fact-partial{background:#fef9c3}.fact-missed{background:#fee2e2}.fact-undisclosed{background:#e0e7ff}
.stats{font-size:13px;color:#64748b}
details{margin-top:8px}summary{cursor:pointer;font-weight:600;font-size:13px;color:#475569}
nav.side{position:fixed;left:0;top:0;width:160px;height:100vh;background:#fff;border-right:1px solid #e2e8f0;padding:16px 12px;overflow-y:auto;font-size:13px;z-index:100}
nav.side h3{font-size:12px;color:#64748b;margin:0 0 8px 0;text-transform:uppercase;letter-spacing:0.5px}
nav.side a{display:block;padding:4px 8px;border-radius:4px;text-decoration:none;color:#334155;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav.side a:hover{background:#f1f5f9}
nav.side a.nav-pass{color:#166534}
nav.side a.nav-fail{color:#991b1b;font-weight:600}
nav.side .nav-icon{margin-right:4px}
@media(max-width:768px){nav.side{display:none}body{padding-left:20px}}
"""


def _build_review_html(results: List[dict], patient_llm: str, server_url: str) -> str:
    """Build the dialog review HTML — persona + chat + record + fact assessment table."""
    date = _human_date()
    passed = sum(1 for r in results if r.get("pass"))
    total = len(results)
    p: list[str] = []

    p.append(f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>")
    p.append(f"<title>Sim Review — {passed}/{total}</title>")
    p.append(f"<style>{_REVIEW_CSS}</style></head><body>")
    # Floating nav bar
    p.append('<nav class="side"><h3>Personas</h3>')
    for r in results:
        _persona = r.get("persona", {})
        _pid = _persona.get("id", "?")
        _name = _persona.get("name", "?")
        _p = r.get("pass", False)
        _icon = "✅" if _p else "❌"
        _cls = "nav-pass" if _p else "nav-fail"
        p.append(f'<a href="#persona-{_esc(_pid)}" class="{_cls}">'
                 f'<span class="nav-icon">{_icon}</span>{_esc(_pid)} {_esc(_name)}</a>')
    p.append("</nav>")

    p.append(f"<h1>Patient Sim Review</h1>")
    p.append(f'<p style="color:#64748b">{_esc(date)} · LLM: {_esc(patient_llm)} · Server: {_esc(server_url)}</p>')
    p.append(f'<div class="summary-bar"><span style="color:#22c55e">PASS: {passed}</span>'
             f'<span style="color:#ef4444">FAIL: {total - passed}</span></div>')

    for r in results:
        persona = r.get("persona", {})
        pid = persona.get("id", "?")
        name = persona.get("name", "?")
        gender = persona.get("gender", "")
        age = persona.get("age", "")
        p_pass = r.get("pass", False)
        turns = r.get("turns", 0)
        t2 = r.get("tier2", {})
        elicit = t2.get("elicitation", {}).get("score", "?")
        extract = t2.get("extraction", {}).get("score", "?")
        undisclosed_ids = t2.get("extraction", {}).get("undisclosed_facts", [])

        cls = "pass" if p_pass else "fail"
        badge = "badge-pass" if p_pass else "badge-fail"
        status = "PASS" if p_pass else "FAIL"
        open_attr = "" if p_pass else " open"

        p.append(f'<div class="persona {cls}" id="persona-{_esc(pid)}">')
        p.append(f'<div class="header"><h2 style="margin:0">{_esc(pid)} — {_esc(name)}, {_esc(gender)}, {_esc(str(age))}岁</h2>')
        p.append(f'<span class="badge {badge}">{status}</span></div>')
        p.append(f'<div class="stats">{turns} turns | elicit={elicit}% | extract={extract}%')
        if undisclosed_ids:
            p.append(f" | {len(undisclosed_ids)} undisclosed")
        p.append("</div>")

        # Persona background
        p.append(f'<details{open_attr}><summary>📋 Persona</summary><div class="persona-bg">')
        p.append(f'<p><span class="label">Condition:</span> {_esc(persona.get("condition", ""))}</p>')
        p.append(f'<p><span class="label">Background:</span> {_esc(persona.get("background", ""))}</p>')
        meds = persona.get("medications", "")
        if meds:
            if isinstance(meds, list):
                meds_str = "; ".join(f"{m.get('name','')} {m.get('dose','')} {m.get('frequency','')}" for m in meds)
            else:
                meds_str = str(meds)
            p.append(f'<p><span class="label">Medications:</span> {_esc(meds_str)}</p>')
        p.append("</div></details>")

        # Dialog
        p.append(f'<details{open_attr}><summary>💬 对话</summary>')
        for m in r.get("conversation", []):
            role = m.get("role")
            text = _esc(m.get("text", m.get("content", "")))
            if role in ("system", "assistant"):
                p.append(f'<div class="msg ai">🤖 {text}</div>')
            else:
                p.append(f'<div class="msg patient">👤 {text}</div>')
        p.append("</details>")

        # Record
        snap = r.get("structured_snapshot", {})
        filled = {k: v for k, v in snap.items() if v}
        if filled:
            p.append(f'<details{open_attr}><summary>📄 病历</summary><div class="record"><dl>')
            for k, v in filled.items():
                p.append(f"<dt>{_esc(_FIELD_CN.get(k, k))}</dt><dd>{_esc(v)}</dd>")
            p.append("</dl></div></details>")

        # Fact assessment table
        facts = t2.get("extraction", {}).get("facts", {})
        all_catalog = persona.get("fact_catalog", [])
        if all_catalog:
            p.append(f'<details{open_attr}><summary>📊 事实评估</summary>')
            p.append('<table class="fact-table">')
            p.append("<tr><th>目标字段</th><th>预期事实</th><th>患者实际表述</th><th>重要性</th><th>结果</th></tr>")
            for f in all_catalog:
                fid = f.get("id", "")
                ftext = _esc(f.get("text", ""))
                imp = f.get("importance", "normal")
                imp_cn = {"critical": "🔴", "important": "🟡", "normal": "⚪"}.get(imp, "")
                target = _FIELD_CN.get(f.get("field", f.get("expected_field", "")), "?")
                v = facts.get(fid, {})
                level = v.get("match_level", "—")
                disclosed = v.get("disclosed", None)
                patient_said = v.get("patient_said", "")

                if level == "exact":
                    row_cls, level_cn = "fact-exact", "✅ 匹配"
                elif level == "partial":
                    row_cls, level_cn = "fact-partial", "⚠️ 部分"
                elif level == "missed" and disclosed is False:
                    row_cls, level_cn = "fact-undisclosed", "— 未评估"
                elif level == "missed":
                    row_cls, level_cn = "fact-missed", "❌ 缺失"
                else:
                    row_cls, level_cn = "", "—"

                said_display = _esc(patient_said) if patient_said else ("（未提及）" if disclosed is False else "—")
                p.append(f'<tr class="{row_cls}"><td>{_esc(target)}</td><td>{ftext}</td>'
                         f"<td>{said_display}</td><td>{imp_cn}</td><td>{level_cn}</td></tr>")
            p.append("</table></details>")

        p.append("</div>")

    p.append("</body></html>")
    return "\n".join(p)


def generate_reports(
    results: List[dict],
    patient_llm: str,
    server_url: str,
    output_dir: Optional[str] = None,
    db_path: str = "",
) -> Tuple[str, str]:
    """Generate HTML, review HTML, and JSON reports for a simulation run.

    Returns:
        Tuple of (html_path, json_path).
    """
    out = Path(output_dir or _DEFAULT_OUTPUT_DIR) / _date_subdir()
    out.mkdir(parents=True, exist_ok=True)

    slug = _time_slug()
    html_name = f"sim-{slug}.html"
    json_name = f"sim-{slug}.json"
    review_name = f"sim-{slug}-review.html"

    html_path = out / html_name
    json_path = out / json_name
    review_path = out / review_name

    html_content = _build_html(results, patient_llm, server_url, db_path=db_path)
    html_path.write_text(html_content, encoding="utf-8")

    review_content = _build_review_html(results, patient_llm, server_url)
    review_path.write_text(review_content, encoding="utf-8")

    json_data = _build_json(results, patient_llm, server_url)
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return str(html_path), str(json_path)
