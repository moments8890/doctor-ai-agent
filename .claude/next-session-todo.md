# Next Session TODO — Debug Dashboard Redesign

## Decision: Grafana-style sidebar layout + GitHub Dark theme

## Theme
- GitHub Dark: bg #0d1117, card #161b22, border #30363d, text #c9d1d9
- Blue accent #58a6ff, orange active #f78166, green #3fb950, red #f85149
- Mockup: `/tmp/debug-layouts.html` (Layout B)

## Layout
- Left sidebar (200px): sections for LLM, Benchmark, System
- Sidebar items: Recent Calls (with count badge), By Provider, Errors Only (red badge)
- Benchmark section: Latency Test, Correctness Eval, Provider Compare
- System section: Logs (with error badge), Config
- Bottom: link back to Admin Dashboard
- Main content area: header + content per selected nav item
- Split pane can be added inside any section (e.g. LLM Calls list+detail)

## Implementation Plan
1. Rewrite debug.html CSS vars to GitHub Dark theme
2. Replace tab bar with sidebar navigation
3. Convert each tab's content into a "page" toggled by sidebar selection
4. Add health metrics in main header (calls/h, errors, avg TTFT, provider)
5. Add error count badges in sidebar nav items
6. Future: split pane for LLM Calls (list left, detail right)

## What Shipped This Session
- Admin dashboard: 3-tab layout, overview stats, doctor drill-down, raw data
- Debug dashboard: /debug route, 3 tabs, light mode, eval with production-sized prompts
- All pushed to origin + gitee (commit 986a653)

## Files to Change
- `src/channels/web/doctor_dashboard/debug.html` — full rewrite of layout + theme
- No backend changes needed — all APIs stay the same
