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
import os, re
from datetime import datetime

RESULTS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test-results"))
BASE = os.path.join(RESULTS_ROOT, "runs", "latest")
SPEC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "e2e"))
ARCHIVE_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test-results-archive"))
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M")

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
    best_title = name
    if spec_num in spec_tests:
        for t in spec_tests[spec_num]["tests"]:
            words = re.findall(r'[\u4e00-\u9fff]+|[A-Za-z]{3,}', t["name"])
            matched = sum(1 for w in words if w.lower() in name.lower())
            if matched >= 2 or (len(words) == 1 and matched == 1):
                best_title = t["name"]; break
    results.append({"dir": name, "spec": spec_num, "title": best_title,
        "describe": spec_tests.get(spec_num, {}).get("describe", ""),
        "status": status, "hasVideo": has_video, "screenshot": screenshot})

if not results:
    print("No test results found. Run `npx playwright test` first.")
    exit(0)

# --- Generate steps.html per test ---
for r in results:
    d = os.path.join(BASE, r["dir"])
    html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>{r["title"]}</title>
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
  <p class="summary"><span class="{r['status']}-badge">{"PASSED" if r["status"]=="pass" else "FAILED"}</span> &mdash; {r["describe"]}</p>
</div>
<div class="columns">
  <div class="info-col">
    <div class="field"><div class="field-label">Spec</div><div class="field-value">{r["spec"]} &mdash; {r["describe"]}</div></div>
    <div class="field"><div class="field-label">Test</div><div class="field-value">{r["title"]}</div></div>
    <div class="field"><div class="field-label">Status</div><div class="field-value"><span class="{r['status']}-badge">{"PASSED" if r["status"]=="pass" else "FAILED"}</span></div></div>
    {f'<div class="screenshot-thumb"><div class="field-label">Final Screenshot</div><img src="{r["screenshot"]}" onclick="window.open(this.src)" loading="lazy"></div>' if r["screenshot"] else ""}
  </div>
  <div class="video-col">
    {'<video src="video.webm" controls autoplay muted loop></video>' if r["hasVideo"] else (f'<img src="{r["screenshot"]}" />' if r["screenshot"] else '<div class="no-video">No video (API-only test)</div>')}
  </div>
</div>
</body></html>'''
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
    nav.append(f'  <div class="section-header">{sn} &mdash; {s["describe"]}</div>')
    for t in s["tests"]:
        short = t["title"][:38] + ("..." if len(t["title"]) > 38 else "")
        nav.append(f'  <a class="nav-link" onclick="load(\'runs/latest/{t["dir"]}/steps.html\',this)"><span class="nav-dot {t["status"]}"></span><span>{short}</span></a>')

total_pass = sum(1 for r in results if r["status"] == "pass")
skip_count = sum(1 for s in spec_tests.values() for t in s["tests"] if t["skipped"])

os.makedirs(RESULTS_ROOT, exist_ok=True)
with open(os.path.join(RESULTS_ROOT, "index.html"), "w") as f:
    f.write(f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Doctor AI — E2E Test Results</title>
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
.archive-header{{padding:10px 14px 4px;font-size:10px;color:#bbb;text-transform:uppercase;letter-spacing:1px;border-top:1px solid #f0f0f0;margin-top:8px}}
#main{{flex:1;display:flex;flex-direction:column;overflow:hidden}}
#content-frame{{flex:1;border:none;background:#f5f5f5}}
#welcome{{flex:1;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;color:#999}}
#welcome h2{{color:#07c160;font-size:20px}}
</style></head><body>
<div id="sidebar">
  <div id="sidebar-title">E2E Test Results</div>
  <div class="summary-bar"><span class="pass">{total_pass} passed</span> &bull; <span class="skip">{skip_count} skipped</span> &bull; {len(results)} recorded</div>
  <div class="timestamp">Last run: {TIMESTAMP}</div>
{"".join(nav)}
  {f'<div class="archive-header">Past Runs</div>{archive_links}' if archives else ''}
</div>
<div id="main">
  <div id="welcome"><h2>Doctor AI E2E Tests</h2><p>Select a test from the sidebar</p><p style="font-size:12px;color:#ccc">{total_pass}/{len(results)} passing &bull; {TIMESTAMP}</p></div>
  <iframe id="content-frame" style="display:none"></iframe>
</div>
<script>
var cur=null;
function load(src,el){{document.getElementById("welcome").style.display="none";var f=document.getElementById("content-frame");f.style.display="block";f.src=src;if(cur)cur.classList.remove("active");if(el){{el.classList.add("active");cur=el;}}}}
</script>
</body></html>''')

print(f"Generated index.html + {len(results)} steps.html ({total_pass} passed, {TIMESTAMP})")
