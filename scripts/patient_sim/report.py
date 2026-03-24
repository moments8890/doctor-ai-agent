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


def _tier2_summary(result: dict) -> str:
    t2 = result.get("tier2", {})
    extraction = t2.get("extraction", {})
    if not extraction:
        return "N/A"
    total = len(extraction)
    matched = sum(1 for v in extraction.values() if v.get("match"))
    return f"{matched}/{total} fields"


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


def _badge(text: str) -> str:
    """Return a coloured badge span."""
    if text == "PASS":
        return '<span class="badge pass">PASS</span>'
    elif text == "FAIL":
        return '<span class="badge fail">FAIL</span>'
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
"""


def _build_extraction_table(result: dict) -> str:
    t2 = result.get("tier2", {})
    extraction = t2.get("extraction", {})
    if not extraction:
        return "<p><em>No extraction data.</em></p>"

    rows = []
    for field, info in extraction.items():
        expected = info.get("expected", [])
        expected_str = ", ".join(expected) if isinstance(expected, list) else str(expected)
        got = info.get("got", "")
        got_display = got[:120] + "…" if len(got) > 120 else got
        match = info.get("match", False)
        icon = "✓" if match else "✗"
        cls = "pass" if match else "fail"

        # Judge votes
        votes = info.get("votes", [])
        reasons = info.get("reasons", [])
        models = info.get("models", [])
        if votes:
            vote_parts = []
            for i, v in enumerate(votes):
                m = models[i] if i < len(models) else f"J{i+1}"
                vote_parts.append(f'{"✓" if v else "✗"} {_esc(m)}')
            vote_html = f'<div style="font-size:0.75rem;color:#888;margin-top:2px">{" · ".join(vote_parts)}</div>'
            if reasons:
                reason_html = '<div style="font-size:0.72rem;color:#999;margin-top:2px">' + \
                    "<br>".join(f"{_esc(models[i] if i < len(models) else f'J{i+1}')}: {_esc(r[:80])}" for i, r in enumerate(reasons)) + "</div>"
            else:
                reason_html = ""
        else:
            vote_html = ""
            reason_html = ""

        rows.append(
            f"<tr><td>{_esc(field)}</td><td>{_esc(expected_str)}</td>"
            f"<td>{_esc(got_display)}</td>"
            f"<td><span class='badge {cls}'>{icon}</span>{vote_html}{reason_html}</td></tr>"
        )

    return (
        "<table><tr><th>Field</th><th>Expected</th><th>Got</th><th>Match (3 judges)</th></tr>"
        + "".join(rows) + "</table>"
    )


def _build_conversation_block(result: dict) -> str:
    conversation = result.get("conversation", [])
    if not conversation:
        return "<p><em>No conversation recorded.</em></p>"

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
        return "<p><em>No medical record found.</em></p>"
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


def _build_html(results: List[dict], patient_llm: str, server_url: str, db_path: str = "") -> str:
    date = _human_date()
    p: list[str] = []

    p.append(f"<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>")
    p.append(f"<title>Patient Simulation Report — {_esc(date)}</title>")
    p.append(f"<style>{_CSS}</style></head><body>")

    p.append(f"<h1>Patient Simulation Report</h1>")
    p.append(f'<div class="meta">{_esc(date)} · Patient LLM: <code>{_esc(patient_llm)}</code> · '
             f'Server: <code>{_esc(server_url)}</code> · Personas: {len(results)}</div>')

    # Navigation
    p.append('<nav class="toc"><strong>Jump to:</strong> <ul>')
    for r in results:
        persona = r.get("persona", {})
        pid = persona.get("id", "?")
        name = persona.get("name", "?")
        anchor = f"persona-{pid}"
        result_icon = "✓" if r.get("pass") else "✗"
        p.append(f'<li><a href="#{anchor}">{result_icon} {_esc(pid)} {_esc(name)}</a></li>')
    p.append('</ul></nav>')

    # Summary table
    p.append("<table><tr><th>Persona</th><th>Turns</th><th>DB</th>"
             "<th>Extraction</th><th>Quality</th><th>Anomalies</th><th>Result</th></tr>")
    for r in results:
        persona = r.get("persona", {})
        pid = _esc(persona.get("id", "?"))
        name = _esc(persona.get("name", "?"))
        condition = _esc(persona.get("condition", ""))
        anchor = f"persona-{persona.get('id', '?')}"
        turns = r.get("turns", "?")
        db = _badge(_tier1_summary(r))
        ext = _tier2_summary(r)
        qual = _tier3_summary(r)
        t4 = r.get("tier4", {})
        anomaly_count = len(t4.get("anomalies", []))
        anomaly_high = t4.get("high", 0)
        anomaly_str = "0"
        if anomaly_high:
            anomaly_str = f'<span class="badge fail">{anomaly_count} ({anomaly_high} high)</span>'
        elif anomaly_count:
            anomaly_str = f'<span class="badge na">{anomaly_count}</span>'
        overall = _badge(_overall_result(r))
        p.append(
            f'<tr><td><a href="#{anchor}" style="text-decoration:none;color:inherit">'
            f'<strong>{pid} {name}</strong><br><small>{condition}</small></a></td>'
            f"<td>{turns}</td><td>{db}</td><td>{_esc(ext)}</td>"
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
        result_icon = "✓ PASS" if r.get("pass") else "✗ FAIL"

        p.append(f'<div class="persona-section" id="{anchor}">')
        p.append(f"<h2>{_esc(label)} — {_esc(condition)} [{result_icon}]</h2>")

        # Medical Record from DB
        record_id = r.get("record_id")
        if record_id and db_path:
            record = _load_medical_record(record_id, db_path)
            p.append(f"<details><summary>Medical Record (DB record #{record_id})</summary>")
            p.append(_build_medical_record_block(record))
            p.append("</details>")

        # Extraction
        p.append(f"<details open><summary>Extracted Facts</summary>")
        p.append(f'<div style="padding:12px 16px">')
        p.append(_build_extraction_table(r))
        t2 = r.get("tier2", {})
        cov = t2.get("checklist_coverage")
        if cov is not None:
            cp = "✓" if t2.get("checklist_pass") else "✗"
            p.append(f'<div class="checklist">Checklist coverage: {cov:.0%} {cp}</div>')
        p.append("</div></details>")

        # DB check failures
        t1 = r.get("tier1", {})
        if not t1.get("pass"):
            p.append("<details open><summary>DB Check Failures</summary><div style='padding:12px 16px'>")
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
            p.append(f"<details><summary>Quality — {t3['score']}/10 median ({valid_n}/{total_n} judges)</summary>")
            p.append('<div style="padding:12px 16px">')
            p.append(
                f"<table><tr><th>Dimension</th><th>Median</th><th>All Scores</th></tr>"
                f"<tr><td>Overall</td><td><strong>{t3['score']}/10</strong></td><td>{_esc(_fmt('all_scores'))}</td></tr>"
                f"<tr><td>Completeness</td><td>{t3.get('completeness', '?')}/10</td><td>{_esc(_fmt('all_completeness'))}</td></tr>"
                f"<tr><td>Appropriateness</td><td>{t3.get('appropriateness', '?')}/10</td><td>{_esc(_fmt('all_appropriateness'))}</td></tr>"
                f"<tr><td>Communication</td><td>{t3.get('communication', '?')}/10</td><td>{_esc(_fmt('all_communication'))}</td></tr>"
                f"</table>"
            )
            explanations = t3.get("all_explanations", [])
            if explanations:
                p.append('<div style="font-size:0.82rem;color:#666;margin-top:4px">')
                for i, exp in enumerate(explanations):
                    if exp and exp != "judge error":
                        p.append(f"<div>Judge {i+1}: <em>{_esc(exp[:120])}</em></div>")
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
            if high: counts.append(f'{high} high')
            if medium: counts.append(f'{medium} medium')
            if low: counts.append(f'{low} low')
            p.append(f"<details open><summary>Anomaly Review ({', '.join(counts)})</summary>")
            p.append('<div style="padding:12px 16px">')
            p.append("<table><tr><th>Severity</th><th>Type</th><th>Detail</th></tr>")
            for a in sorted(anomalies, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 3)):
                sev = a.get("severity", "low")
                sev_cls = "fail" if sev == "high" else ("na" if sev == "medium" else "pass")
                p.append(
                    f"<tr><td><span class='badge {sev_cls}'>{_esc(sev)}</span></td>"
                    f"<td>{_esc(a.get('type', ''))}</td>"
                    f"<td>{_esc(a.get('detail', ''))}</td></tr>"
                )
            p.append("</table>")
            summary = t4.get("summary", "")
            if summary:
                p.append(f"<p><em>{_esc(summary)}</em></p>")
            p.append("</div></details>")
        else:
            p.append(f'<div class="checklist">Anomaly Review: ✓ No anomalies found</div>')

        # Conversation
        p.append(f"<details><summary>Conversation ({r.get('turns', '?')} turns)</summary>")
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

def generate_reports(
    results: List[dict],
    patient_llm: str,
    server_url: str,
    output_dir: Optional[str] = None,
    db_path: str = "",
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

    html_content = _build_html(results, patient_llm, server_url, db_path=db_path)
    html_path.write_text(html_content, encoding="utf-8")

    json_data = _build_json(results, patient_llm, server_url)
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return str(html_path), str(json_path)
