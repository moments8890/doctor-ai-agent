"""Report generation for doctor simulation runs.

Produces both HTML and JSON reports from simulation results.
Uses only stdlib + json + sqlite3 — no application imports.
Reuses CSS from patient_sim.report.
"""
from __future__ import annotations

import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = str(_REPO_ROOT / "reports" / "doctor_sim")


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
# CSS — reused from patient_sim.report with doctor-specific additions
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
nav.toc { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px 16px; margin-bottom: 24px; }
nav.toc a { color: #1a73e8; text-decoration: none; font-size: 0.88rem; }
nav.toc a:hover { text-decoration: underline; }
nav.toc ul { list-style: none; padding: 0; margin: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; }
.persona-section { margin-bottom: 32px; }
.importance-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.74rem; font-weight: 600; }
.importance-critical { background: #f8d7da; color: #721c24; }
.importance-important { background: #fff3cd; color: #856404; }
.importance-normal { background: #e2e3e5; color: #383d41; }
.hallucination-list { color: #dc3545; font-weight: 600; }
.fact-critical-miss { background: #f8d7da; }
.fact-important-miss { background: #fff3cd; }
.combined-score-bar { text-align: right; padding: 8px 12px; font-size: 0.9rem; border-top: 1px solid #e0e0e0; margin-top: 8px; }
.summary-dim { text-align: center !important; padding: 6px 8px !important; }
.summary-dim-header { text-align: center !important; font-size: 0.78rem !important; padding: 6px 8px !important; }
.doctor-input { padding: 12px 16px; font-size: 0.85rem; white-space: pre-wrap; color: #333; background: #fafafa; }
.turn-block { margin-bottom: 12px; border-left: 3px solid #1a73e8; padding-left: 10px; }
.turn-label { font-weight: 600; color: #1a73e8; margin-bottom: 2px; font-size: 0.84rem; }
.turn-text { white-space: pre-wrap; color: #333; }
.quality-section { margin-bottom: 8px; }
.quality-title { font-weight: 600; margin-bottom: 2px; }
.quality-check.ok   { color: #155724; }
.quality-check.fail { color: #dc3545; font-weight: 600; }
"""


# ---------------------------------------------------------------------------
# Badge helpers
# ---------------------------------------------------------------------------

def _dim_score_badge(score: int) -> str:
    """Coloured badge for a dimension score (0-100)."""
    if score < 0:
        return '<span class="badge na">--</span>'
    if score >= 80:
        cls = "score-green"
    elif score >= 60:
        cls = "score-yellow"
    else:
        cls = "score-red"
    return f'<span class="badge {cls}">{score}</span>'


def _score_badge(score: int) -> str:
    """Coloured badge for a 0-100 combined score."""
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
    """Coloured badge span for pass/fail."""
    if text == "PASS":
        return '<span class="badge pass">通过</span>'
    elif text == "FAIL":
        return '<span class="badge fail">未通过</span>'
    return f'<span class="badge na">{_esc(text)}</span>'


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _dim_scores(result: dict) -> Dict[str, int]:
    """Return per-dimension scores from validation, -1 if unavailable."""
    val = result.get("validation", {})
    dims = val.get("dimensions", {})
    return {
        "extraction_recall": dims.get("dim1_extraction_recall", {}).get("score", -1),
        "field_accuracy": dims.get("dim2_field_accuracy", {}).get("score", -1),
        "record_quality": dims.get("dim3_record_quality", {}).get("score", -1),
    }


def _overall_result(result: dict) -> str:
    return "PASS" if result.get("pass") else "FAIL"


# ---------------------------------------------------------------------------
# SOAP display helpers
# ---------------------------------------------------------------------------

_SOAP_LABELS = {
    "chief_complaint": "主诉", "present_illness": "现病史", "past_history": "既往史",
    "allergy_history": "过敏史", "family_history": "家族史", "personal_history": "个人史",
    "marital_reproductive": "婚育史", "physical_exam": "体格检查", "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查", "diagnosis": "诊断", "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
}

_SOAP_FIELDS = list(_SOAP_LABELS.keys())


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


# ---------------------------------------------------------------------------
# Scorecard panels
# ---------------------------------------------------------------------------

def _build_dim1_extraction_recall(dim: dict) -> str:
    """Dimension 1: 事实提取召回率 — fact_catalog matched against DB."""
    facts = dim.get("facts", {})
    score = dim.get("score", -1)
    matched = dim.get("matched", 0)
    total = dim.get("total", 0)
    if not facts and score < 0:
        return ""

    rows: list[str] = []
    for fid, info in facts.items():
        importance = info.get("importance", "normal")
        match = info.get("match", False)
        found_in = info.get("found_in", "")
        expected = info.get("expected_field", "")
        text = info.get("text", "")

        imp_cls = f"importance-{importance}"
        imp_label = {"critical": "关键", "important": "重要", "normal": "一般"}.get(importance, importance)

        match_icon = "+" if match else "-"

        row_cls = ""
        if not match and importance == "critical":
            row_cls = "fact-critical-miss"
        elif not match and importance == "important":
            row_cls = "fact-important-miss"

        rows.append(
            f'<tr class="{row_cls}">'
            f'<td>{_esc(fid)}</td>'
            f'<td><span class="importance-badge {imp_cls}">{_esc(imp_label)}</span></td>'
            f'<td>{_esc(expected)}</td>'
            f'<td>{_esc(found_in) if found_in else "--"}</td>'
            f'<td><span class="badge {"pass" if match else "fail"}">{match_icon}</span></td>'
            f'</tr>'
        )

    score_html = _dim_score_badge(score)
    summary = f"{matched}/{total} 匹配" if total > 0 else ""
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>1. 事实提取召回率 ({_esc(summary)})</span>{score_html}</summary>'
        '<div class="dim-body">'
        '<table><tr><th>事实ID</th><th>重要性</th><th>预期字段</th><th>实际字段</th><th>匹配</th></tr>'
        + "".join(rows)
        + '</table></div>'
        '</details>'
    )


def _build_dim2_field_accuracy(dim: dict) -> str:
    """Dimension 2: 字段归类准确率 — matched facts in correct field."""
    facts = dim.get("facts", {})
    score = dim.get("score", -1)
    correct = dim.get("correct", 0)
    total_matched = dim.get("total_matched", 0)
    if not facts and score < 0:
        return ""

    rows: list[str] = []
    for fid, info in facts.items():
        is_correct = info.get("correct", False)
        expected = info.get("expected_field", "")
        actual = info.get("actual_field", "")

        icon = "+" if is_correct else "-"
        row_cls = "" if is_correct else "fact-important-miss"

        rows.append(
            f'<tr class="{row_cls}">'
            f'<td>{_esc(fid)}</td>'
            f'<td>{_esc(expected)}</td>'
            f'<td>{_esc(actual)}</td>'
            f'<td><span class="badge {"pass" if is_correct else "fail"}">{icon}</span></td>'
            f'</tr>'
        )

    score_html = _dim_score_badge(score)
    summary = f"{correct}/{total_matched} 正确" if total_matched > 0 else ""
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>2. 字段归类准确率 ({_esc(summary)})</span>{score_html}</summary>'
        '<div class="dim-body">'
        '<table><tr><th>事实ID</th><th>预期字段</th><th>实际字段</th><th>正确</th></tr>'
        + "".join(rows)
        + '</table></div>'
        '</details>'
    )


def _build_dim3_record_quality(dim: dict) -> str:
    """Dimension 3: 记录质量 — hallucinations, abbreviations, duplication."""
    score = dim.get("score", -1)
    hallucinations = dim.get("hallucinations", [])
    abbreviation_issues = dim.get("abbreviation_issues", [])
    duplication_issues = dim.get("duplication_issues", [])

    if score < 0 and not hallucinations and not abbreviation_issues and not duplication_issues:
        return ""

    parts: list[str] = []

    # Hallucinations
    if hallucinations:
        items = []
        for h in hallucinations:
            if isinstance(h, dict):
                items.append(f"<li>{_esc(h.get('field', ''))}: {_esc(h.get('detail', ''))}</li>")
            else:
                items.append(f"<li>{_esc(str(h))}</li>")
        parts.append(
            '<div class="quality-section">'
            '<div class="quality-title">幻觉检查</div>'
            f'<ul class="hallucination-list">{"".join(items)}</ul>'
            '</div>'
        )
    else:
        parts.append(
            '<div class="quality-section">'
            '<span class="quality-check ok">幻觉检查：+ 未发现</span>'
            '</div>'
        )

    # Abbreviation issues
    if abbreviation_issues:
        items = []
        for a in abbreviation_issues:
            if isinstance(a, dict):
                items.append(
                    f"<li>{_esc(a.get('field', ''))}: "
                    f"原文「{_esc(a.get('original', ''))}」 -> "
                    f"DB「{_esc(a.get('db_value', ''))}」 "
                    f"({_esc(a.get('detail', ''))})</li>"
                )
            else:
                items.append(f"<li>{_esc(str(a))}</li>")
        parts.append(
            '<div class="quality-section">'
            '<div class="quality-title">缩写保留</div>'
            f'<ul style="color:#856404">{"".join(items)}</ul>'
            '</div>'
        )
    else:
        parts.append(
            '<div class="quality-section">'
            '<span class="quality-check ok">缩写保留：+ 正常</span>'
            '</div>'
        )

    # Duplication issues
    if duplication_issues:
        items = []
        for d in duplication_issues:
            if isinstance(d, dict):
                items.append(f"<li>{_esc(d.get('field', ''))}: {_esc(d.get('detail', ''))}</li>")
            else:
                items.append(f"<li>{_esc(str(d))}</li>")
        parts.append(
            '<div class="quality-section">'
            '<div class="quality-title">信息重复</div>'
            f'<ul style="color:#856404">{"".join(items)}</ul>'
            '</div>'
        )
    else:
        parts.append(
            '<div class="quality-section">'
            '<span class="quality-check ok">信息重复：+ 未发现</span>'
            '</div>'
        )

    score_html = _dim_score_badge(score)
    return (
        '<details class="dim-section" open>'
        f'<summary class="dim-header"><span>3. 记录质量</span>{score_html}</summary>'
        f'<div class="dim-body">{"".join(parts)}</div>'
        '</details>'
    )


def _build_scorecard(result: dict) -> str:
    """Build the 3-dimension scorecard for a persona's validation results."""
    val = result.get("validation", {})
    if not val:
        return "<p><em>无评估数据</em></p>"

    combined = val.get("combined_score", -1)
    dims = val.get("dimensions", {})

    if not dims:
        return "<p><em>无评估数据</em></p>"

    parts: list[str] = ['<div class="scorecard">']

    dim1 = _build_dim1_extraction_recall(dims.get("dim1_extraction_recall", {}))
    if dim1:
        parts.append(dim1)

    dim2 = _build_dim2_field_accuracy(dims.get("dim2_field_accuracy", {}))
    if dim2:
        parts.append(dim2)

    dim3 = _build_dim3_record_quality(dims.get("dim3_record_quality", {}))
    if dim3:
        parts.append(dim3)

    parts.append('</div>')  # .scorecard

    if combined >= 0:
        score_cls = "score-green" if combined >= 80 else ("score-yellow" if combined >= 60 else "score-red")
        parts.append(
            f'<div class="combined-score-bar">'
            f'综合评分: <span class="badge {score_cls}" style="font-size:0.9rem">{combined}/100</span>'
            f'</div>'
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Doctor input block
# ---------------------------------------------------------------------------

def _build_doctor_input_block(persona: dict) -> str:
    """Show the scripted turn_plan text."""
    turn_plan = persona.get("turn_plan", [])
    if not turn_plan:
        return "<p><em>无输入数据</em></p>"

    parts = ['<div class="doctor-input">']
    for step in turn_plan:
        turn_num = step.get("turn", "?")
        text = step.get("text", "")
        parts.append(
            f'<div class="turn-block">'
            f'<div class="turn-label">轮次 {_esc(str(turn_num))}</div>'
            f'<div class="turn-text">{_esc(text)}</div>'
            f'</div>'
        )
    parts.append('</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _build_html(
    results: List[dict],
    server_url: str,
    db_path: str = "",
    ai_analyses: Optional[List[dict]] = None,
) -> str:
    date = _human_date()
    p: list[str] = []

    p.append(f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>")
    p.append(f"<title>医生模拟测试报告 -- {_esc(date)}</title>")
    p.append(f"<style>{_CSS}</style></head><body>")

    p.append(f"<h1>医生模拟测试报告</h1>")
    p.append(f'<div class="meta">{_esc(date)} · '
             f'服务器: <code>{_esc(server_url)}</code> · 测试角色: {len(results)}</div>')

    # Navigation
    p.append('<nav class="toc"><strong>快速跳转：</strong> <ul>')
    for r in results:
        persona = r.get("persona", {})
        pid = persona.get("id", "?")
        name = persona.get("name", "?")
        anchor = f"persona-{pid}"
        result_icon = "+" if r.get("pass") else "-"
        p.append(f'<li><a href="#{anchor}">{result_icon} {_esc(pid)} {_esc(name)}</a></li>')
    p.append('</ul></nav>')

    # Summary table — 3 dimension columns
    p.append(
        "<table><tr>"
        "<th>角色</th><th>轮次</th><th>数据库</th>"
        '<th class="summary-dim-header">提取召回</th>'
        '<th class="summary-dim-header">字段归类</th>'
        '<th class="summary-dim-header">质量</th>'
        "<th>结果</th></tr>"
    )
    for r in results:
        persona = r.get("persona", {})
        pid = _esc(persona.get("id", "?"))
        name = _esc(persona.get("name", "?"))
        style = _esc(persona.get("style", ""))
        anchor = f"persona-{persona.get('id', '?')}"
        turns = r.get("turns", "?")
        has_record = "PASS" if r.get("record_id") else "FAIL"
        db_badge = _badge(has_record)
        scores = _dim_scores(r)
        overall = _badge(_overall_result(r))

        p.append(
            f'<tr><td><a href="#{anchor}" style="text-decoration:none;color:inherit">'
            f'<strong>{pid} {name}</strong><br><small>{style}</small></a></td>'
            f'<td>{turns}</td><td>{db_badge}</td>'
            f'<td class="summary-dim">{_dim_score_badge(scores["extraction_recall"])}</td>'
            f'<td class="summary-dim">{_dim_score_badge(scores["field_accuracy"])}</td>'
            f'<td class="summary-dim">{_dim_score_badge(scores["record_quality"])}</td>'
            f'<td>{overall}</td></tr>'
        )
    p.append("</table>")

    # Per-persona details
    for r in results:
        persona = r.get("persona", {})
        pid = persona.get("id", "?")
        name = persona.get("name", "?")
        style = persona.get("style", "")
        description = persona.get("description", "")
        label = f"{pid} {name}"
        anchor = f"persona-{pid}"
        result_icon = "+ 通过" if r.get("pass") else "- 未通过"

        p.append(f'<div class="persona-section" id="{anchor}">')
        p.append(f"<h2>{_esc(label)} -- {_esc(style)} [{result_icon}]</h2>")
        if description:
            p.append(f'<p style="color:#666;font-size:0.85rem;margin-bottom:12px">{_esc(description)}</p>')

        # Medical Record from snapshot
        record = r.get("soap_snapshot", {})
        if record:
            p.append(f"<details><summary>病历记录</summary>")
            p.append(_build_medical_record_block(record))
            p.append("</details>")

        # Scorecard (3-dimension evaluation)
        val = r.get("validation", {})
        combined = val.get("combined_score", -1)
        score_label = f" -- {combined}/100" if combined >= 0 else ""
        p.append(f'<details open><summary>评估记分卡{_esc(score_label)}</summary>')
        p.append(_build_scorecard(r))
        p.append("</details>")

        # Doctor input (scripted turn_plan)
        p.append(f'<details><summary>医生输入（{r.get("turns", "?")} 轮）</summary>')
        p.append(_build_doctor_input_block(persona))
        p.append("</details>")

        # Error display
        if r.get("error"):
            p.append(f'<details open><summary>错误信息</summary>'
                     f'<div style="padding:12px 16px;color:#721c24">{_esc(r["error"])}</div>'
                     f'</details>')

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

        p.append('<script>document.querySelector("nav.toc ul")?.insertAdjacentHTML("beforeend", '
                 '"<li><a href=\\"#ai-analysis\\">AI专家分析</a></li>")</script>')

    p.append("</body></html>")
    return "\n".join(p)


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def _build_json(results: List[dict], server_url: str) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server_url": server_url,
        "persona_count": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_reports(
    results: List[dict],
    server_url: str,
    output_dir: Optional[str] = None,
    db_path: str = "",
    ai_analyses: Optional[List[dict]] = None,
) -> Tuple[str, str]:
    """Generate HTML and JSON reports for a doctor simulation run.

    Returns:
        Tuple of (html_path, json_path).
    """
    out = Path(output_dir or _DEFAULT_OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    html_name = f"docsim-{ts}.html"
    json_name = f"docsim-{ts}.json"

    html_path = out / html_name
    json_path = out / json_name

    html_content = _build_html(results, server_url, db_path=db_path, ai_analyses=ai_analyses)
    html_path.write_text(html_content, encoding="utf-8")

    json_data = _build_json(results, server_url)
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return str(html_path), str(json_path)
