# Next Session TODO — Admin & Debug Consolidation

## Status: All Issues Fixed — Ready to Commit & Deploy

## What's Done
1. Debug consolidation: `/debug` route, 3 tabs (LLM/Benchmark/Logs), DebugPage.jsx deleted
2. Admin overview API: 6 endpoints with LLM call counting, AI adoption, task completion stats
3. Admin frontend: 3-tab layout, overview with all 6 stats populated, doctor drill-down with full stats
4. Data contract fixes: alert format, field names, profile flattening, timeline items key
5. Test doctor filter: expanded prefixes (debug_, intsim_, clean_, demo_) — 170→155 doctors in dev DB
6. LLM调用 1H stat: reads from logs/llm_calls.jsonl
7. Doctor detail: patients count, AI采纳率, 任务完成率 all showing real data

## To Commit
```bash
# 1. Debug consolidation
git add src/channels/web/doctor_dashboard/debug_handlers.py \
  src/channels/web/doctor_dashboard/debug.html \
  frontend/web/src/App.jsx
git rm frontend/web/src/pages/admin/DebugPage.jsx
git commit -m "refactor: consolidate debug to /debug, delete React DebugPage"

# 2. Admin API + filter fix
git add src/channels/web/doctor_dashboard/admin_overview.py \
  src/channels/web/doctor_dashboard/__init__.py \
  src/channels/web/doctor_dashboard/filters.py
git commit -m "feat: admin overview API with stats, alerts, doctor detail, timeline"

# 3. Admin frontend
git add frontend/web/src/pages/admin/AdminPage.jsx \
  frontend/web/src/pages/admin/AdminOverview.jsx \
  frontend/web/src/pages/admin/AdminRawData.jsx \
  frontend/web/src/pages/admin/AdminDoctorDetail.jsx
git commit -m "feat: admin dashboard with overview, doctor drill-down, grouped raw data"

# 4. Specs & plans
git add docs/specs/2026-03-30-admin-debug-consolidation-design.md \
  docs/specs/2026-03-30-admin-debug-mockup.html \
  docs/plans/2026-03-30-admin-debug-consolidation.md
git commit -m "docs: admin/debug consolidation design spec and plan"
```

## Deploy
```bash
git push origin main && git push gitee main
ssh tencent "cd /home/ubuntu/doctor-ai-agent && git fetch origin && git reset --hard origin/main && sudo systemctl restart doctor-ai-backend && cd frontend/web && npm run build && cp -r dist ../dist"
```
