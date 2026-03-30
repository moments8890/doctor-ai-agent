"""Report generation for chat simulation runs."""
from __future__ import annotations

import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = str(_REPO_ROOT / "reports" / "chat_sim")


def _esc(t): return html.escape(str(t))
def _date_subdir(): return datetime.now().strftime("%Y%m%d")
def _time_slug(): return datetime.now().strftime("%H-%M-%S")
def _human_date(): return datetime.now().strftime("%Y-%m-%d %H:%M")


def _badge(t):
    if t in ("PASS","通过"): return '<span class="badge pass">通过</span>'
    if t in ("FAIL","未通过"): return '<span class="badge fail">未通过</span>'
    return f'<span class="badge na">{_esc(t)}</span>'


def _intent_badge(intent):
    colors = {
        "query_record": ("#e8f0fe", "#1a73e8"),
        "query_patient": ("#e8f0fe", "#1a73e8"),
        "query_task": ("#e8f0fe", "#1a73e8"),
        "create_record": ("#dafbe1", "#1a7f37"),
        "create_task": ("#dafbe1", "#1a7f37"),
        "daily_summary": ("#f3e8fd", "#7627bb"),
        "general": ("#e2e3e5", "#383d41"),
    }
    bg, fg = colors.get(intent, ("#e2e3e5", "#383d41"))
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:0.75rem;font-weight:600;background:{bg};color:{fg}">{_esc(intent)}</span>'


_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       line-height: 1.6; color: #1a1a1a; background: #f5f5f5; }
.layout { display: flex; height: 100vh; }
.sidebar { width: 280px; min-width: 280px; background: #fff; border-right: 1px solid #e0e0e0;
           display: flex; flex-direction: column; overflow: hidden; }
.sidebar-header { padding: 16px 16px 12px; border-bottom: 1px solid #e0e0e0; }
.sidebar-header h1 { font-size: 1.1rem; }
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
.scenario-meta { display: flex; gap: 16px; margin-top: 8px; font-size: 0.84rem; color: #666; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge.pass { background: #d4edda; color: #155724; }
.badge.fail { background: #f8d7da; color: #721c24; }
.badge.na   { background: #e2e3e5; color: #383d41; }
.check-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.check-item { font-size: 0.8rem; padding: 5px 8px; border-radius: 4px; }
.check-item.pass { background: #d4edda; color: #155724; }
.check-item.fail { background: #f8d7da; color: #721c24; }
.chat-area { display: flex; flex-direction: column; padding: 12px 16px; }
.chat-bubble { max-width: 85%; padding: 10px 14px; border-radius: 12px; margin-bottom: 8px;
               font-size: 0.88rem; line-height: 1.5; }
.chat-doctor { background: #e8f0fe; margin-right: auto; border-bottom-left-radius: 4px; }
.chat-ai { background: #d4edda; margin-left: auto; border-bottom-right-radius: 4px; }
.fail-detail { background: #fff3cd; border-left: 3px solid #ffc107; padding: 8px 12px;
               margin: 8px 0; font-size: 0.85rem; border-radius: 0 4px 4px 0; }
@media (max-width: 900px) { .check-grid { grid-template-columns: 1fr; } }
"""


def generate_reports(results, scenarios, server_url, db_path, output_dir=_DEFAULT_OUTPUT_DIR):
    date_dir = os.path.join(output_dir, _date_subdir())
    os.makedirs(date_dir, exist_ok=True)
    slug = _time_slug()
    html_path = os.path.join(date_dir, f"cxsim-{slug}-review.html")
    json_path = os.path.join(date_dir, f"cxsim-{slug}.json")

    scenario_map = {s["id"]: s for s in scenarios}
    passed_count = sum(1 for r in results if r.get("pass"))
    total = len(results)

    panels = []
    for idx, r in enumerate(results):
        sid = r["scenario_id"]
        sc = scenario_map.get(sid, {})
        passed = r.get("pass", False)
        exp = sc.get("expectations", {})
        active = ' active' if idx == 0 else ''

        p = [f'<div class="scenario-panel{active}" id="panel-{idx}">']
        p.append('<div class="scenario-header">')
        p.append(f'<h2>{_esc(sid)} — {_esc(sc.get("title", sid))} {_badge("PASS" if passed else "FAIL")}</h2>')
        expected_intent = exp.get("intent", "") or "/".join(exp.get("intent_any", []))
        actual_intent = r.get("intent", "?")
        p.append(
            f'<div class="scenario-meta">'
            f'<span>预期: {_intent_badge(expected_intent)}</span>'
            f'<span>实际: {_intent_badge(actual_intent)}</span>'
            f'<span>用时: <b>{r.get("response_time_s", 0)}s</b></span>'
            f'</div>')
        p.append('</div>')

        if r.get("error"):
            p.append(f'<div class="fail-detail">Error: {_esc(r["error"])}</div>')

        # Chat
        p.append('<div class="section-card">')
        p.append('<div class="section-card-header">对话</div>')
        p.append('<div class="section-card-body"><div class="chat-area">')
        p.append(f'<div class="chat-bubble chat-doctor">{_esc(r.get("message", ""))}</div>')
        reply = r.get("reply", "")
        if reply:
            p.append(f'<div class="chat-bubble chat-ai">{_esc(reply)}</div>')
        p.append('</div></div></div>')

        # Seeded data
        seeds = []
        for pt in sc.get("seed_patients", []):
            rec = pt.get("record", {})
            seeds.append(f'患者: {_esc(pt.get("name", ""))} — {_esc(rec.get("chief_complaint", ""))}')
        for t in sc.get("seed_tasks", []):
            seeds.append(f'任务: {_esc(t.get("title", ""))}')
        if seeds:
            p.append('<div class="section-card">')
            p.append('<div class="section-card-header">预置数据</div>')
            p.append('<div class="section-card-body">')
            for s in seeds:
                p.append(f'<div style="font-size:0.84rem;margin-bottom:4px;">{s}</div>')
            p.append('</div></div>')

        # Validation
        v = r.get("validation", {})
        checks = v.get("checks", {})
        if checks:
            p.append('<div class="section-card">')
            p.append('<div class="section-card-header">验证结果</div>')
            p.append('<div class="section-card-body"><div class="check-grid">')
            for name, info in checks.items():
                cls = "pass" if info["pass"] else "fail"
                icon = "✓" if info["pass"] else "✗"
                p.append(f'<div class="check-item {cls}">{icon} <b>{_esc(name)}</b>: {_esc(info.get("detail", ""))}</div>')
            p.append('</div></div></div>')

        p.append('</div>')
        panels.append("\n".join(p))

    js = "function switchTab(i){document.querySelectorAll('.sidebar-item').forEach(e=>e.classList.remove('active'));document.querySelectorAll('.scenario-panel').forEach(e=>e.classList.remove('active'));document.getElementById('tab-'+i).classList.add('active');document.getElementById('panel-'+i).classList.add('active');}"

    html_parts = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f'<title>聊天模拟报告 — {_human_date()}</title>',
        f'<style>{_CSS}</style></head><body>',
        '<div class="layout"><div class="sidebar">',
        f'<div class="sidebar-header"><h1>聊天模拟报告</h1><div class="meta">{_human_date()}</div>',
        f'<div class="sidebar-stats"><span class="stat pass-stat">✓ {passed_count}</span>',
        f'<span class="stat fail-stat">✗ {total - passed_count}</span>',
        f'<span class="stat">共 {total}</span></div></div>',
        '<div class="sidebar-list">',
    ]
    for idx, r in enumerate(results):
        sid = r["scenario_id"]
        sc = scenario_map.get(sid, {})
        passed = r.get("pass", False)
        active = ' active' if idx == 0 else ''
        cls = 'passed' if passed else 'failed'
        html_parts.append(
            f'<div class="sidebar-item {cls}{active}" id="tab-{idx}" onclick="switchTab({idx})">'
            f'<div class="status-dot"></div>'
            f'<span class="sid">{_esc(sid)}</span>'
            f'<span class="title">{_esc(sc.get("title", sid))}</span></div>')
    html_parts.append('</div></div><div class="main">')
    html_parts.append("\n".join(panels))
    html_parts.append(f'</div></div><script>{js}</script></body></html>')

    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    json_data = {"timestamp": _human_date(), "server_url": server_url,
                 "passed": passed_count, "total": total, "results": results}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    return html_path, json_path
