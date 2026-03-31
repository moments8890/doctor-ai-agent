# Admin & Debug Dashboard Consolidation — Design Spec

**Date:** 2026-03-30
**Status:** Approved
**Mockup:** [admin-debug-mockup.html](2026-03-30-admin-debug-mockup.html) (dense layout)

## Goal

Consolidate two overlapping debug pages and redesign the admin page for beta
monitoring. Separate concerns: `/debug` for LLM/system debugging, `/admin` for
operational monitoring of doctors, patients, and AI quality.

## URL Structure

| URL | Tech | Purpose |
|-----|------|---------|
| `/debug?token=X` | Standalone HTML | LLM debugging, benchmarks, logs |
| `/admin` | React (MUI) | Beta ops: doctor activity, AI quality, workflows |
| `/api/debug/*` | FastAPI | Debug API endpoints (unchanged) |

## Debug Dashboard (`/debug`)

### Route Change
- New: `GET /debug` serves debug.html (same file as current `/api/debug/dashboard`)
- Keep `/api/debug/dashboard` as backward-compat alias
- Auth: `?token=X` URL param or localStorage prompt (unchanged)

### 3 Tabs

**1. LLM Calls** (default)
- Existing LLM call inspector
- Op filter, search, errors-only toggle, pagination
- Click-to-expand: full prompt/response, trace ID, provider, tokens, latency

**2. Benchmark**
- Provider table: name, model, model selector, pricing, status, roles
- Latency benchmark: run button, runs selector, history
- Structured output eval: run button, pass/fail per provider, expandable raw output

**3. Logs**
- Source filter: app.log, tasks.log, scheduler.log
- Level filter: ALL, DEBUG, INFO, WARNING, ERROR, CRITICAL
- Line limit control

### Removed Features
- Routing Metrics (fast vs LLM hit counts) — vanity metric, not actionable
- Observability (traces, spans, timeline) — not actionable at beta scale
- Requests tab — overlaps with logs
- Health tab — SSH is more useful

### Deleted Files
- `frontend/web/src/pages/admin/DebugPage.jsx` — React debug page removed
- `/debug` and `/debug/:section` routes removed from App.jsx

## Admin Dashboard (`/admin`)

### Design Principles
- **Workflow-shaped, not table-shaped** — navigation follows doctor → patient → case chain
- **Dense, structured, informative** — dev-friendly, 11px base font, compact tables
- **Anomalies surface automatically** — color-coded rows, alert strip, status chips
- **Raw data accessible but demoted** — grouped table browser behind "原始数据" tab

### 3 Tabs

#### Tab 1: 总览 (Overview)

**Stat Strip** — horizontal bar with 6 metrics:
- 活跃医生 (active/total, inactive warning)
- 患者消息 24h (total, replied, pending)
- 病历 24h (count, complete vs incomplete)
- AI建议 (count, 采纳/编辑/拒绝 breakdown)
- 任务 (pending count, overdue highlight)
- LLM调用 1h (count, error count, avg latency)

**Alert Strip** — red/amber rows for:
- Overdue tasks (>24h)
- Unanswered patient messages (>2h)
- Inactive doctors (>3 days)
- Records missing key fields
- AI suggestion rejection spikes

**Side-by-side panels:**

Left: **医生表** — doctor, specialty, patients, today messages, AI adoption rate,
pending items, last active, KB count. Yellow row for inactive. Clickable to drill-down.

Right: **最近活动** — time, doctor, event type, detail, status chip.
Color-coded: 采纳(green), 待回复(amber), 拒绝(red), 完成(green).

Bottom left: **任务管道** — doctor, patient, task, created, status, elapsed time.
Red row for overdue. Status chips: 逾期/待处理/进行中/完成.

Bottom right: **AI建议 24h** — time, doctor, patient, type, result, edit percentage.
Highlights rejections and high-edit items.

#### Tab 2: 医生 (Doctor Drill-Down)

Clicking a doctor name navigates to this view.

**Header** — one line: name, specialty, ID, registration date, last active.
Inline setup checklist: ✓ 邀请码, ✓ KB×N, ✓ 上下文, ✓ 首患者, ✓ 首AI, ✓ 首病历.

**Stat Strip** — 6 metrics for this doctor:
- 患者 (total, weekly delta)
- 消息 7d (inbound, AI replies)
- AI采纳率 (percent, 采纳/编辑/拒绝 counts)
- 病历 7d (count, complete/incomplete)
- 任务完成率 (percent, complete/overdue/pending)
- 平均响应 (median, min, max)

**患者表** — patient, gender/age, registered, message count, records, AI suggestion
status, pending items, last message, status chip. Red row for patients needing attention.

**案例时间线** — chronological view of a selected patient:
- Patient registration
- Patient messages (content preview)
- AI replies
- Record creation (field summary)
- AI suggestions (type, result, edit %)
- Tasks (status)
- Each row includes trace ID linking to `/debug` LLM Calls tab

This directly supports the "AI said something weird" investigation flow:
doctor → patient → messages → AI suggestion → trace ID → LLM call details.

#### Tab 3: 原始数据 (Raw Data)

Grouped table tabs:

**核心运营:** doctors, patients, patient_messages, medical_records, ai_suggestions,
doctor_tasks, message_drafts

**设置与学习:** knowledge_items, doctor_contexts, interview_sessions, chat_log

**系统:** audit_log, invite_codes, system_prompts, runtime_config, labels

Each tab shows row count. Full table with all columns, sortable. Same phpMyAdmin
power as today, just organized and demoted from the default view.

### Visual Signals

| Signal | Color | Trigger |
|--------|-------|---------|
| Red row | `#fce4ec` | Overdue task, rejected AI suggestion |
| Amber row | `#fffde7` | Inactive doctor, pending >2h, incomplete record |
| Red chip | `c-r` | 逾期, 拒绝, 关注 |
| Amber chip | `c-a` | 待回复, 待处理, 缺字段 |
| Green chip | `c-g` | 采纳, 完成, 正常 |
| Blue chip | `c-b` | 完整, 编辑 |

### Critical Tables for Beta Monitoring

**Primary (drive the dashboard):**
- doctors — activity, onboarding status
- patients — growth, per-doctor panel
- patient_messages — inbound volume, response time
- medical_records — creation, completeness
- ai_suggestions — accept/edit/reject behavior
- doctor_tasks — pipeline status, overdue detection
- message_drafts — AI reply generation pipeline

**Secondary (drill-down):**
- doctor_knowledge_items — setup quality
- doctor_chat_log — doctor-to-AI interaction
- interview_sessions — intake status

**System (raw data only):**
- audit_log, invite_codes, system_prompts, runtime_config, labels

### Backend API Needs

New endpoints for the overview dashboard:

- `GET /api/admin/overview` — aggregated stats (counts, rates, alerts)
- `GET /api/admin/doctors` — doctor list with activity metrics
- `GET /api/admin/doctors/:id` — doctor detail with setup checklist, stats
- `GET /api/admin/doctors/:id/patients` — patient list with status
- `GET /api/admin/doctors/:id/timeline` — case timeline for a patient
- `GET /api/admin/activity` — recent activity feed

Existing raw table endpoints stay unchanged.

## Cascading Impact

1. **DB schema** — None. No new tables or columns.
2. **ORM models** — None.
3. **API endpoints** — New: `GET /debug` route, 6 admin overview endpoints. Changed: none. Removed: none.
4. **Domain logic** — New aggregation queries for overview stats (counts, rates, last-active). No business logic changes.
5. **Prompt files** — None.
6. **Frontend** — Delete DebugPage.jsx, remove `/debug` routes from App.jsx, rewrite AdminPage.jsx with new 3-tab layout.
7. **Configuration** — None.
8. **Existing tests** — None affected.
9. **Cleanup** — Remove DebugPage.jsx, remove debug routes from App.jsx.

## Ship Order

1. Debug consolidation: add `GET /debug` route, remove tabs from debug.html, delete DebugPage.jsx
2. Admin overview tab: stat strip, alert strip, side-by-side panels
3. Admin doctor drill-down: header, stats, patient table, case timeline
4. Admin raw data tab: grouped table browser (mostly existing code, reorganized)
