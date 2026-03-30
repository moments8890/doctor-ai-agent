"""Report generation for reply simulation runs."""
from __future__ import annotations

import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = str(_REPO_ROOT / "reports" / "reply_sim")


def _date_subdir() -> str:
    return datetime.now().strftime("%Y%m%d")


def _time_slug() -> str:
    return datetime.now().strftime("%H-%M-%S")


def _human_date() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _esc(text: str) -> str:
    return html.escape(str(text))


def _badge(text: str) -> str:
    if text in ("PASS", "通过"):
        return '<span class="badge pass">通过</span>'
    elif text in ("FAIL", "未通过"):
        return '<span class="badge fail">未通过</span>'
    return f'<span class="badge na">{_esc(text)}</span>'


def _cat_badge(cat: str) -> str:
    colors = {
        "informational": ("pass", "信息"),
        "symptom_report": ("score-yellow", "症状"),
        "side_effect": ("score-yellow", "副作用"),
        "general_question": ("na", "一般"),
        "urgent": ("fail", "紧急"),
    }
    cls, label = colors.get(cat, ("na", cat))
    return f'<span class="badge {cls}">{_esc(label)}</span>'


_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       line-height: 1.6; color: #1a1a1a; background: #f5f5f5; }
.layout { display: flex; height: 100vh; }
.sidebar { width: 280px; min-width: 280px; background: #fff; border-right: 1px solid #e0e0e0;
           display: flex; flex-direction: column; overflow: hidden; }
.sidebar-header { padding: 16px 16px 12px; border-bottom: 1px solid #e0e0e0; }
.sidebar-header h1 { font-size: 1.1rem; margin-bottom: 2px; }
.sidebar-header .meta { color: #666; font-size: 0.78rem; }
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
.main { flex: 1; overflow-y: auto; padding: 24px 32px; }
.scenario-panel { display: none; }
.scenario-panel.active { display: block; }
.section-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
                margin-bottom: 16px; overflow: hidden; }
.section-card-header { padding: 10px 16px; font-weight: 600; font-size: 0.9rem;
                       background: #fafafa; border-bottom: 1px solid #e0e0e0;
                       display: flex; justify-content: space-between; align-items: center; }
.section-card-body { padding: 14px 16px; }
.scenario-header { margin-bottom: 20px; }
.scenario-header h2 { font-size: 1.3rem; margin-bottom: 4px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
.scenario-meta { display: flex; gap: 16px; margin-top: 8px; font-size: 0.84rem; color: #666; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge.pass { background: #d4edda; color: #155724; }
.badge.fail { background: #f8d7da; color: #721c24; }
.badge.na   { background: #e2e3e5; color: #383d41; }
.badge.score-yellow { background: #fff3cd; color: #856404; }
.check-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.check-item { font-size: 0.8rem; padding: 5px 8px; border-radius: 4px; }
.check-item.pass { background: #d4edda; color: #155724; }
.check-item.fail { background: #f8d7da; color: #721c24; }
.chat-bubble { max-width: 80%; padding: 10px 14px; border-radius: 12px; margin-bottom: 8px;
               font-size: 0.88rem; line-height: 1.5; }
.chat-patient { background: #e8f0fe; color: #1a1a1a; margin-right: auto; border-bottom-left-radius: 4px; }
.chat-ai { background: #d4edda; color: #1a1a1a; margin-left: auto; border-bottom-right-radius: 4px; }
.chat-area { display: flex; flex-direction: column; padding: 12px 16px; }
.fail-detail { background: #fff3cd; border-left: 3px solid #ffc107; padding: 8px 12px;
               margin: 8px 0; font-size: 0.85rem; border-radius: 0 4px 4px 0; }
.kb-item { background: #f0f7ff; border-left: 3px solid #1a73e8; padding: 8px 12px;
           margin-bottom: 6px; border-radius: 0 6px 6px 0; font-size: 0.84rem; }
.record-field { margin-bottom: 4px; font-size: 0.84rem; }
.record-field b { color: #555; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } .check-grid { grid-template-columns: 1fr; } }
.record-field-rich { margin-bottom: 8px; font-size: 0.84rem; padding: 6px 8px; border-radius: 4px; background: #fafafa; }
.record-field-rich b { color: #555; }
.kb-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }
.kb-card.kb-relevant { border-left: 4px solid #1a73e8; background: #f8fbff; }
.kb-card.kb-irrelevant { border-left: 4px solid #dc3545; background: #fff8f8; }
.kb-card-header { font-size: 0.86rem; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
.kb-card-text { font-size: 0.82rem; color: #444; margin-bottom: 6px; line-height: 1.5; }
.kb-concepts { display: flex; flex-wrap: wrap; gap: 4px; }
.concept-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
.concept-tag.found { background: #d4edda; color: #155724; }
.concept-tag.missed { background: #f8d7da; color: #721c24; }
.concept-tag.excluded { background: #d4edda; color: #155724; }
.concept-tag.leaked { background: #f8d7da; color: #721c24; }
"""


def _tag_badge(tag: str) -> str:
    tag_colors = {
        "informational": ("#d4edda", "#155724"),
        "auto_reply": ("#d4edda", "#155724"),
        "escalation": ("#fff3cd", "#856404"),
        "urgent": ("#f8d7da", "#721c24"),
        "red_flag": ("#f8d7da", "#721c24"),
        "safety": ("#f8d7da", "#721c24"),
        "kb_injection": ("#e8f0fe", "#1a73e8"),
        "tricky": ("#f3e8fd", "#7627bb"),
        "ambiguous": ("#f3e8fd", "#7627bb"),
        "mixed": ("#f3e8fd", "#7627bb"),
        "baseline": ("#e6f4ea", "#137333"),
        "side_effect": ("#fff3cd", "#856404"),
        "symptom_report": ("#fff3cd", "#856404"),
    }
    bg, fg = tag_colors.get(tag, ("#e2e3e5", "#383d41"))
    return f'<span class="tag" style="background:{bg};color:{fg}">{_esc(tag)}</span>'


def generate_reports(
    results: List[Dict],
    scenarios: List[Dict],
    server_url: str,
    db_path: str,
    output_dir: str = _DEFAULT_OUTPUT_DIR,
) -> Tuple[str, str]:
    date_dir = os.path.join(output_dir, _date_subdir())
    os.makedirs(date_dir, exist_ok=True)
    slug = _time_slug()
    html_path = os.path.join(date_dir, f"rxsim-{slug}-review.html")
    json_path = os.path.join(date_dir, f"rxsim-{slug}.json")

    scenario_map = {s["id"]: s for s in scenarios}
    passed_count = sum(1 for r in results if r.get("pass"))
    total = len(results)

    # Build panels
    panels_html = []
    for idx, r in enumerate(results):
        sid = r["scenario_id"]
        sc = scenario_map.get(sid, {})
        passed = r.get("pass", False)
        tags = sc.get("tags", [])
        exp = sc.get("expectations", {})
        active = ' active' if idx == 0 else ''

        p = [f'<div class="scenario-panel{active}" id="panel-{idx}">']

        # Header
        p.append('<div class="scenario-header">')
        p.append(f'<h2>{_esc(sid)} — {_esc(sc.get("title", sid))} {_badge("PASS" if passed else "FAIL")}</h2>')
        p.append(f'<div class="tags">{" ".join(_tag_badge(t) for t in tags)}</div>')
        expected_cat = exp.get("triage_category", "") or "/".join(exp.get("triage_category_any", ["?"]))
        actual_cat = r.get("triage_category", "?")
        p.append(
            f'<div class="scenario-meta">'
            f'<span>预期分类: {_cat_badge(expected_cat)}</span>'
            f'<span>实际分类: {_cat_badge(actual_cat)}</span>'
            f'<span>AI处理: <b>{"是" if r.get("ai_handled") else "否"}</b></span>'
            f'<span>用时: <b>{r.get("response_time_s", 0)}s</b></span>'
            f'</div>')
        p.append('</div>')

        if r.get("error"):
            p.append(f'<div class="fail-detail">Error: {_esc(r["error"])}</div>')

        reply = r.get("reply", "")

        # --- Chat exchange (full width, prominent) ---
        p.append('<div class="section-card">')
        p.append('<div class="section-card-header">对话</div>')
        p.append('<div class="section-card-body"><div class="chat-area">')
        p.append(f'<div class="chat-bubble chat-patient">{_esc(r.get("message", ""))}</div>')
        if reply:
            p.append(f'<div class="chat-bubble chat-ai">{_esc(reply)}</div>')
        p.append('</div></div></div>')

        # --- Two columns: record context + KB context ---
        rec = sc.get("record", {})
        kb_items = sc.get("knowledge_items", [])

        p.append('<div class="two-col">')

        # Left: medical record with concept highlighting
        p.append('<div class="section-card">')
        p.append('<div class="section-card-header">病历上下文 → 如何影响回复</div>')
        p.append('<div class="section-card-body">')
        for key, label in [("chief_complaint", "主诉"), ("diagnosis", "诊断"),
                           ("treatment_plan", "治疗方案"), ("orders_followup", "医嘱随访")]:
            val = rec.get(key, "")
            if not val:
                continue
            # Check which parts of this field appear in the reply
            field_words = set()
            for chunk in val.replace("，", " ").replace("。", " ").replace("、", " ").split():
                if len(chunk) >= 2:
                    field_words.add(chunk)
            matched_in_reply = [w for w in field_words if w in reply] if reply else []
            match_badge = ""
            if matched_in_reply:
                match_badge = f' <span class="badge pass">→ 回复引用了: {_esc(", ".join(matched_in_reply[:5]))}</span>'
            p.append(f'<div class="record-field-rich"><b>{_esc(label)}：</b>{_esc(val)}{match_badge}</div>')
        p.append('</div></div>')

        # Right: KB items with full content + concept match
        if kb_items:
            p.append('<div class="section-card">')
            p.append(f'<div class="section-card-header">知识库注入 ({len(kb_items)}条) → 如何影响回复</div>')
            p.append('<div class="section-card-body">')
            for item in kb_items:
                title = item.get("title", "")
                relevant = item.get("relevant", True)
                concepts = item.get("key_concepts", [])
                # Parse content JSON to get text
                content_raw = item.get("content", "")
                try:
                    parsed = json.loads(content_raw)
                    kb_text = parsed.get("text", content_raw)
                except (json.JSONDecodeError, TypeError):
                    kb_text = content_raw

                # Check concepts in reply
                matched = [c for c in concepts if c in reply] if reply else []
                missed = [c for c in concepts if c not in reply] if reply else concepts

                rel_cls = "kb-relevant" if relevant else "kb-irrelevant"
                rel_label = "相关" if relevant else "不相关"
                p.append(f'<div class="kb-card {rel_cls}">')
                p.append(f'<div class="kb-card-header">')
                p.append(f'<span class="badge {"pass" if relevant else "fail"}">{_esc(rel_label)}</span> ')
                p.append(f'<b>{_esc(title)}</b></div>')
                p.append(f'<div class="kb-card-text">{_esc(kb_text)}</div>')

                # Show concept matching
                if concepts:
                    p.append('<div class="kb-concepts">')
                    for c in concepts:
                        if c in matched:
                            if relevant:
                                p.append(f'<span class="concept-tag found">{_esc(c)} ✓ 回复中出现</span>')
                            else:
                                p.append(f'<span class="concept-tag leaked">{_esc(c)} ⚠ 泄漏!</span>')
                        else:
                            if relevant:
                                p.append(f'<span class="concept-tag missed">{_esc(c)} ✗</span>')
                            else:
                                p.append(f'<span class="concept-tag excluded">{_esc(c)} ✓ 已排除</span>')
                    p.append('</div>')
                p.append('</div>')
            p.append('</div></div>')
        else:
            p.append('<div class="section-card">')
            p.append('<div class="section-card-header">知识库</div>')
            p.append('<div class="section-card-body" style="color:#999">无知识库注入</div>')
            p.append('</div>')

        p.append('</div>')  # close two-col

        # Validation
        validation = r.get("validation", {})
        if validation:
            p.append('<div class="section-card">')
            p.append('<div class="section-card-header">验证结果</div>')
            p.append('<div class="section-card-body">')
            for tier_key, tier_label in [
                ("tier1_triage", "T1 分类验证"),
                ("tier2_reply", "T2 回复内容"),
                ("tier3_kb", "T3 知识库引用"),
            ]:
                tier = validation.get(tier_key, {})
                checks = tier.get("checks", {})
                if not checks:
                    continue
                tier_pass = tier.get("pass", False)
                p.append(f'<div style="font-weight:600;margin:8px 0 4px">{tier_label} {_badge("PASS" if tier_pass else "FAIL")}</div>')
                items = []
                for name, info in checks.items():
                    cls = "pass" if info["pass"] else "fail"
                    icon = "✓" if info["pass"] else "✗"
                    items.append(f'<div class="check-item {cls}">{icon} <b>{_esc(name)}</b>: {_esc(info.get("detail", ""))}</div>')
                p.append(f'<div class="check-grid">{"".join(items)}</div>')
            p.append('</div></div>')

        p.append('</div>')
        panels_html.append("\n".join(p))

    # JavaScript
    js = "function switchTab(i){document.querySelectorAll('.sidebar-item').forEach(e=>e.classList.remove('active'));document.querySelectorAll('.scenario-panel').forEach(e=>e.classList.remove('active'));document.getElementById('tab-'+i).classList.add('active');document.getElementById('panel-'+i).classList.add('active');}"

    # Assemble
    html_parts = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>回复模拟报告 — {_human_date()}</title>',
        f'<style>{_CSS}</style></head><body>',
        '<div class="layout">',
        '<div class="sidebar">',
        '<div class="sidebar-header">',
        '<h1>回复模拟报告</h1>',
        f'<div class="meta">{_human_date()}</div>',
        f'<div class="sidebar-stats"><span class="stat pass-stat">✓ {passed_count}</span>'
        f'<span class="stat fail-stat">✗ {total - passed_count}</span>'
        f'<span class="stat">共 {total}</span></div></div>',
        '<div class="sidebar-list">',
    ]
    for idx, r in enumerate(results):
        sid = r["scenario_id"]
        sc = scenario_map.get(sid, {})
        passed = r.get("pass", False)
        active = ' active' if idx == 0 else ''
        status_cls = 'passed' if passed else 'failed'
        html_parts.append(
            f'<div class="sidebar-item {status_cls}{active}" id="tab-{idx}" onclick="switchTab({idx})">'
            f'<div class="status-dot"></div>'
            f'<span class="sid">{_esc(sid)}</span>'
            f'<span class="title">{_esc(sc.get("title", sid))}</span></div>')
    html_parts.append('</div></div>')
    html_parts.append('<div class="main">')
    html_parts.append("\n".join(panels_html))
    html_parts.append('</div></div>')
    html_parts.append(f'<script>{js}</script></body></html>')

    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    json_data = {"timestamp": _human_date(), "server_url": server_url,
                 "passed": passed_count, "total": total, "results": results}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    return html_path, json_path
