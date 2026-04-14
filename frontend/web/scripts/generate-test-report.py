#!/usr/bin/env python3
"""
Generate index.html + per-test steps.html for the E2E test results viewer.
Run after `npx playwright test` to create a browseable report.

Usage:
  python3 scripts/generate-test-report.py

Outputs:
  test-results/index.html          — sidebar navigation + iframe viewer
  test-results/<test>/steps.html   — per-test detail + video panel
"""
import json, os, re
from datetime import datetime

RESULTS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test-results"))
BASE = os.path.join(RESULTS_ROOT, "runs", "latest")
SPEC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "e2e"))
ARCHIVE_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test-results-archive"))
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M")

# --- Chinese translations for workflow names ---
WORKFLOW_CN = {
    "Workflow 00 — Seed smoke": "基础冒烟测试",
    "Workflow 01 — Auth": "登录认证",
    "Workflow 02 — Onboarding wizard": "引导向导",
    "Workflow 03 — My AI overview": "AI助手概览",
    "Workflow 04 — Persona rules": "AI风格规则",
    "Workflow 05 — Knowledge CRUD": "知识库管理",
    "Workflow 06 — Patient list": "患者列表",
    "Workflow 07 — Patient detail": "患者详情",
    "Workflow 08 — Review diagnosis": "审核诊断",
    "Workflow 09 — Draft reply send": "草稿回复",
    "Workflow 10 — Tasks": "任务管理",
    "Workflow 11 — Settings": "设置",
    "Workflow 12 — New record creation": "新建病历",
    "Workflow 13 — Persona pending review": "待确认风格",
    "Workflow 14 — Persona onboarding": "风格引导",
    "Workflow 15 — Persona teach-by-example": "教AI学偏好",
    "Workflow 16 — Template management": "模板管理",
    "Workflow 17 — QR invite + Patient preview": "二维码与预览",
    "Workflow 18 — Teaching loop round-trip": "教学闭环",
    "Workflow 20 — Patient auth": "患者登录",
    "Workflow 21 — Patient chat": "患者对话",
    "Workflow 22 — Patient records": "患者病历",
    "Workflow 23 — Patient tasks": "患者任务",
    "Workflow 24 — Patient onboarding": "患者引导",
}

def translate_workflow(desc):
    """Translate workflow describe string to Chinese, fallback to original."""
    return WORKFLOW_CN.get(desc, desc)

# --- Parse spec test names ---
spec_tests = {}
for fn in sorted(os.listdir(SPEC_DIR)):
    if not fn.endswith('.spec.ts'): continue
    spec_num = fn.split('-')[0]
    with open(os.path.join(SPEC_DIR, fn)) as f:
        content = f.read()
    desc_m = re.search(r'test\.describe\(["\'](.+?)["\']', content)
    desc = desc_m.group(1) if desc_m else fn.replace('.spec.ts', '')
    tests = []
    for m in re.finditer(r'test(\.skip)?\(["\'](.+?)["\']', content):
        tests.append({"name": m.group(2), "skipped": m.group(1) is not None})
    spec_tests[spec_num] = {"describe": desc, "tests": tests}

# --- Scan results ---
results = []
for name in sorted(os.listdir(BASE)):
    d = os.path.join(BASE, name)
    if not os.path.isdir(d) or name.startswith('.'): continue
    spec_num = re.match(r'^(\d+)', name).group(1) if re.match(r'^(\d+)', name) else "??"
    has_video = os.path.exists(os.path.join(d, "video.webm"))
    has_screenshot = os.path.exists(os.path.join(d, "test-finished-1.png"))
    has_failed = os.path.exists(os.path.join(d, "test-failed-1.png"))
    screenshot = "test-finished-1.png" if has_screenshot else ("test-failed-1.png" if has_failed else None)
    status = "fail" if has_failed else "pass"

    # Load result.json if present
    result_json_path = os.path.join(d, "result.json")
    result_data = None
    if os.path.exists(result_json_path):
        try:
            with open(result_json_path) as f:
                result_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            result_data = None

    best_title = name
    if spec_num in spec_tests:
        for t in spec_tests[spec_num]["tests"]:
            words = re.findall(r'[\u4e00-\u9fff]+|[A-Za-z]{3,}', t["name"])
            matched = sum(1 for w in words if w.lower() in name.lower())
            if matched >= 2 or (len(words) == 1 and matched == 1):
                best_title = t["name"]; break
    results.append({"dir": name, "spec": spec_num, "title": best_title,
        "describe": spec_tests.get(spec_num, {}).get("describe", ""),
        "status": status, "hasVideo": has_video, "screenshot": screenshot,
        "result_data": result_data})

if not results:
    print("No test results found. Run `npx playwright test` first.")
    exit(0)


def generate_steps_html_with_result(r, result_data):
    """Generate lmzy-web style steps.html when result.json exists."""
    steps = result_data.get("steps", [])
    suite = translate_workflow(result_data.get("suite", r["describe"]))
    test_name = result_data.get("test", r["title"])
    all_passed = result_data.get("allPassed", r["status"] == "pass")
    passed_count = sum(1 for s in steps if s.get("pass"))
    failed_count = len(steps) - passed_count
    duration = result_data.get("duration", "")

    badge = '<span class="pass-badge">通过</span>' if all_passed else '<span class="fail-badge">失败</span>'

    steps_html = ""
    for i, s in enumerate(steps):
        cls = "pass" if s.get("pass") else "fail"
        result_label = "通过" if s.get("pass") else "失败"
        detail = f'<div class="step-detail">{s["detail"]}</div>' if s.get("detail") else ""
        screenshot_html = ""
        if s.get("screenshot"):
            screenshot_html = f'<div class="step-screenshot"><img src="{s["screenshot"]}" loading="lazy" onclick="event.stopPropagation();openLightbox(this.src)"></div>'
        steps_html += f'''<div class="step" onclick="this.classList.toggle('open')">
  <div class="step-header">
    <div class="step-num {cls}">{i + 1}</div>
    <div class="step-name">{s.get("name", f"步骤 {i+1}")}{detail}</div>
    <div class="step-result {cls}">{result_label}</div>
  </div>
  {screenshot_html}
</div>
'''

    video_html = '<video src="video.webm" controls autoplay muted loop></video>' if r["hasVideo"] else (
        f'<img src="{r["screenshot"]}" style="max-width:100%;max-height:100%;object-fit:contain" />' if r["screenshot"]
        else '<div class="no-video">无视频（纯接口测试）</div>')

    summary_parts = [f"{passed_count} 通过"]
    if failed_count > 0:
        summary_parts.append(f"{failed_count} 失败")
    if duration:
        summary_parts.append(duration)

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>{test_name}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f8f9fa;color:#333;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
.header{{padding:12px 16px;border-bottom:1px solid #e0e0e0;flex-shrink:0;background:#fff}}
h1{{color:#07c160;font-size:16px;margin-bottom:2px}}
.suite-name{{color:#888;font-size:12px;margin-bottom:4px}}
.summary{{color:#888;font-size:12px}}
.pass-badge{{color:#07c160;font-weight:bold}}.fail-badge{{color:#e53935;font-weight:bold}}
.columns{{display:flex;flex:1;overflow:hidden}}
.steps-col{{flex:3;overflow-y:auto;padding:10px}}
.video-col{{flex:6;border-left:1px solid #e0e0e0;display:flex;flex-direction:column;background:#111;overflow:hidden}}
.video-col video{{width:100%;flex:1;object-fit:contain}}
.video-col img{{max-width:100%;max-height:100%;object-fit:contain}}
.video-col .no-video{{color:#666;font-size:13px;margin:auto}}
.step{{border:1px solid #e0e0e0;border-radius:8px;margin-bottom:8px;overflow:hidden;background:#fff}}
.step-header{{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;transition:background .15s}}
.step-header:hover{{background:#f0f0f0}}
.step-num{{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;flex-shrink:0}}
.step-num.pass{{background:#e8f5e9;color:#07c160}}.step-num.fail{{background:#fbe9e7;color:#e53935}}
.step-name{{flex:1;font-size:13px;line-height:1.4}}
.step-detail{{font-size:11px;color:#999;margin-top:2px}}
.step-result{{font-size:11px;font-weight:bold;flex-shrink:0}}
.step-result.pass{{color:#07c160}}.step-result.fail{{color:#e53935}}
.step-screenshot{{display:none;padding:8px;background:#f5f5f5;text-align:center}}
.step-screenshot img{{max-width:100%;max-height:220px;border-radius:6px;cursor:zoom-in;border:1px solid #e0e0e0}}
.step.open .step-screenshot{{display:block}}
.lightbox{{position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:999;display:flex;align-items:center;justify-content:center;cursor:zoom-out}}
.lightbox img{{max-width:95%;max-height:95%;border-radius:6px;box-shadow:0 0 40px rgba(0,0,0,.4)}}
</style></head><body>
<div class="header">
  <h1>{test_name}</h1>
  <p class="suite-name">{suite}</p>
  <p class="summary">{badge} &mdash; {", ".join(summary_parts)}</p>
</div>
<div class="columns">
  <div class="steps-col">
{steps_html}  </div>
  <div class="video-col">
    {video_html}
  </div>
</div>
<script>
function openLightbox(src){{
  var lb=document.createElement('div');
  lb.className='lightbox';
  lb.innerHTML='<img src="'+src+'">';
  lb.onclick=function(){{lb.remove()}};
  document.body.appendChild(lb);
}}
document.addEventListener('keydown',function(e){{
  if(e.key==='Escape'){{var lb=document.querySelector('.lightbox');if(lb)lb.remove()}}
}});
</script>
</body></html>'''


def generate_steps_html_fallback(r):
    """Generate basic steps.html (no result.json) — backwards compat."""
    badge_label = "通过" if r["status"] == "pass" else "失败"
    video_html = '<video src="video.webm" controls autoplay muted loop></video>' if r["hasVideo"] else (
        f'<img src="{r["screenshot"]}" />' if r["screenshot"]
        else '<div class="no-video">无视频（纯接口测试）</div>')

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>{r["title"]}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f8f9fa;color:#333;height:100vh;display:flex;flex-direction:column;overflow:hidden}}
.header{{padding:12px 16px;border-bottom:1px solid #e0e0e0;flex-shrink:0;background:#fff}}
h1{{color:#07c160;font-size:15px;margin-bottom:2px}}
.summary{{color:#888;font-size:12px}}
.pass-badge{{color:#07c160;font-weight:bold}}.fail-badge{{color:#e53935;font-weight:bold}}
.columns{{display:flex;flex:1;overflow:hidden}}
.info-col{{flex:3;overflow-y:auto;padding:12px;background:#fff}}
.video-col{{flex:6;border-left:1px solid #e0e0e0;display:flex;align-items:center;justify-content:center;background:#111;overflow:hidden}}
.video-col video{{max-width:100%;max-height:100%;object-fit:contain}}
.video-col img{{max-width:100%;max-height:100%;object-fit:contain}}
.video-col .no-video{{color:#666;font-size:13px}}
.field{{margin-bottom:10px}}
.field-label{{font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px}}
.field-value{{font-size:13px;line-height:1.6}}
.screenshot-thumb img{{max-width:200px;border-radius:6px;border:1px solid #eee;cursor:pointer;margin-top:8px}}
</style></head><body>
<div class="header">
  <h1>{r["title"]}</h1>
  <p class="summary"><span class="{r['status']}-badge">{badge_label}</span> &mdash; {translate_workflow(r["describe"])}</p>
</div>
<div class="columns">
  <div class="info-col">
    <div class="field"><div class="field-label">测试组</div><div class="field-value">{r["spec"]} &mdash; {translate_workflow(r["describe"])}</div></div>
    <div class="field"><div class="field-label">测试项</div><div class="field-value">{r["title"]}</div></div>
    <div class="field"><div class="field-label">状态</div><div class="field-value"><span class="{r['status']}-badge">{badge_label}</span></div></div>
    {f'<div class="screenshot-thumb"><div class="field-label">最终截图</div><img src="{r["screenshot"]}" onclick="window.open(this.src)" loading="lazy"></div>' if r["screenshot"] else ""}
  </div>
  <div class="video-col">
    {video_html}
  </div>
</div>
</body></html>'''


# --- Generate steps.html per test ---
for r in results:
    d = os.path.join(BASE, r["dir"])
    if r["result_data"] and r["result_data"].get("steps"):
        html = generate_steps_html_with_result(r, r["result_data"])
    else:
        html = generate_steps_html_fallback(r)
    with open(os.path.join(d, "steps.html"), "w") as f:
        f.write(html)

# --- Group by spec ---
specs = {}
for r in results:
    specs.setdefault(r["spec"], {"describe": r["describe"], "tests": []})["tests"].append(r)

# --- Archive links ---
archives = sorted(os.listdir(ARCHIVE_BASE)) if os.path.exists(ARCHIVE_BASE) else []
archive_links = "".join(
    f'<a href="../test-results-archive/{a}/index.html" style="display:block;padding:4px 14px;font-size:11px;color:#999;text-decoration:none">{a}</a>'
    for a in reversed(archives))

nav = []
for sn in sorted(specs.keys()):
    s = specs[sn]
    cn_name = translate_workflow(s["describe"])
    nav.append(f'  <div class="section-header">{sn} &mdash; {cn_name}</div>')
    for t in s["tests"]:
        short = t["title"][:38] + ("..." if len(t["title"]) > 38 else "")
        # Show step count when result.json has steps
        meta = ""
        rd = t.get("result_data")
        if rd and rd.get("steps"):
            steps = rd["steps"]
            passed_steps = sum(1 for st in steps if st.get("pass"))
            meta = f'<span class="nav-meta">{passed_steps}/{len(steps)}</span>'
        nav.append(f'  <a class="nav-link" onclick="load(\'runs/latest/{t["dir"]}/steps.html\',this)"><span class="nav-dot {t["status"]}"></span><span class="nav-text">{short}</span>{meta}</a>')

total_pass = sum(1 for r in results if r["status"] == "pass")
skip_count = sum(1 for s in spec_tests.values() for t in s["tests"] if t["skipped"])

os.makedirs(RESULTS_ROOT, exist_ok=True)
with open(os.path.join(RESULTS_ROOT, "index.html"), "w") as f:
    f.write(f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Doctor AI — 端到端测试报告</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:#f5f5f5;display:flex;height:100vh;overflow:hidden}}
#sidebar{{width:10vw;min-width:180px;max-width:260px;background:#fff;border-right:1px solid #e0e0e0;display:flex;flex-direction:column;overflow-y:auto}}
#sidebar-title{{padding:14px;font-size:15px;font-weight:bold;color:#07c160;border-bottom:1px solid #e0e0e0;text-align:center}}
.summary-bar{{padding:8px 14px;font-size:12px;color:#888;border-bottom:1px solid #f0f0f0}}
.summary-bar .pass{{color:#07c160;font-weight:600}}.summary-bar .skip{{color:#999;font-weight:600}}
.timestamp{{padding:4px 14px;font-size:10px;color:#bbb;border-bottom:1px solid #f0f0f0}}
.section-header{{padding:10px 14px 4px;font-size:10px;color:#999;text-transform:uppercase;letter-spacing:1px;border-top:1px solid #f0f0f0;margin-top:4px}}
.nav-link{{display:flex;align-items:center;gap:8px;padding:6px 14px;color:#555;cursor:pointer;border-left:3px solid transparent;transition:all .15s;font-size:12px;line-height:1.4}}
.nav-link:hover{{background:#f8f8f8;color:#333}}
.nav-link.active{{background:#e8f5e9;color:#07c160;border-left-color:#07c160;font-weight:600}}
.nav-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.nav-dot.pass{{background:#07c160}}.nav-dot.fail{{background:#e53935}}
.nav-text{{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.nav-meta{{font-size:10px;color:#aaa;margin-left:auto;flex-shrink:0}}
.archive-header{{padding:10px 14px 4px;font-size:10px;color:#bbb;text-transform:uppercase;letter-spacing:1px;border-top:1px solid #f0f0f0;margin-top:8px}}
#main{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
#content-frame{{flex:1;border:none;background:#f5f5f5}}
#welcome{{flex:1;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;color:#999}}
#welcome h2{{color:#07c160;font-size:20px}}
</style></head><body>
<div id="sidebar">
  <div id="sidebar-title">端到端测试报告</div>
  <div class="summary-bar"><span class="pass">{total_pass} 通过</span> &bull; <span class="skip">{skip_count} 跳过</span> &bull; {len(results)} 已录制</div>
  <div class="timestamp">运行时间：{TIMESTAMP}</div>
{"".join(nav)}
  {f'<div class="archive-header">历史记录</div>{archive_links}' if archives else ''}
</div>
<div id="main">
  <div id="welcome"><h2>Doctor AI 端到端测试</h2><p>从左侧选择测试查看详情</p><p style="font-size:12px;color:#ccc">{total_pass}/{len(results)} 通过 &bull; {TIMESTAMP}</p></div>
  <iframe id="content-frame" style="display:none"></iframe>
</div>
<script>
var cur=null;
function load(src,el){{document.getElementById("welcome").style.display="none";var f=document.getElementById("content-frame");f.style.display="block";f.src=src;if(cur)cur.classList.remove("active");if(el){{el.classList.add("active");cur=el;}}}}
</script>
</body></html>''')

print(f"Generated index.html + {len(results)} steps.html ({total_pass} 通过, {TIMESTAMP})")
