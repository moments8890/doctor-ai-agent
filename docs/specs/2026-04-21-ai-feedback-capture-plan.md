# AI Feedback Capture — Flags + Behavior Log

> Date: 2026-04-21
> Status: Draft (Codex-ranked #1 post-inline-UI ship)
> Builds on: `docs/specs/2026-04-20-inline-suggestions-plan.md` (shipped)
> Targets: specialist doctors using the inline per-field review UI

## Problem

We just replaced the 9–15 card suggestion list with a 3-section inline
review flow (diagnosis / workup / treatment). Offline evals cover
structure (counts, enums, `[KB-N]` presence) but NOT clinical
correctness. For a neurosurgery post-op case, no 20-scenario sniff test
can tell us "the AI suggested MRI but CT was right." Only the doctor
can.

Without in-app feedback capture we're **optimizing to pass tests, not
to serve doctors**. We need two complementary signals:

1. **Explicit** — one-tap flag "this AI suggestion is wrong" with
   structured reason.
2. **Implicit** — what the doctor actually did (accepted, edited, cycled,
   rejected, ignored, time-to-finalize). Doctors rarely file feedback,
   but they reveal judgment through behavior.

## Target Experience

**Doctor** (during review flow):
- Every AI pending row has a subtle `⚠️` icon next to 修改. Tap opens
  a bottom sheet: choose reason tag + optional free-text, submit.
- Accepted ✓ rows also have the flag (doctor realized it was wrong
  after accepting).
- Flagging does NOT change the suggestion's decision state — it's
  orthogonal telemetry.
- No confirmation modal, no celebration. Toast "已反馈 · 感谢" and that's it.

**Doctor** (on MyAIPage, weekly):
- New section: "你的AI表现" card
- "本周 AI 共给出 N 条建议，你反馈 M 条不合理"
- Tappable drill-down: last 10 flags, grouped by section + reason
- Light-weight — a status report, not a dashboard

**Passive behavior log** (doctor doesn't see it):
- Every suggestion render → 1 event `suggestion_shown`
- Every 采纳 / 修改 / 换一条 → corresponding event
- 完成审核 → event with duration since page open, per-section
  acceptance rate
- No PII beyond `doctor_id` + record/suggestion context

## Data Model

### New table: `ai_feedback`

Explicit flag events. One row per flag.

```
id              int PK
suggestion_id   int FK → ai_suggestions.id  (nullable — see below)
record_id       int FK → medical_records.id
doctor_id       str(64)
section         str(16)  — differential / workup / treatment
reason_tag      str(32)  — wrong_diagnosis / insufficient_evidence
                            / against_experience / other
reason_text     text nullable
doctor_action   str(16)  — confirmed / edited / rejected / pending
                            (at time of flag)
prompt_version  str(64)  — git SHA of diagnosis.md at generation
                            time, for prompt regression attribution
created_at      datetime
```

`suggestion_id` nullable because doctor can also flag the ABSENCE of a
suggestion they expected ("AI 没提 X — 不合理"). Reason tag handles this.

### New table: `ai_behavior_event`

Passive events. Many rows per review session.

```
id              int PK
doctor_id       str(64)
record_id       int FK
suggestion_id   int FK nullable (null for page-level events)
section         str(16) nullable
event_type      str(32)  — suggestion_shown / accepted / edited
                            / rejected / cycled / finalized
                            / record_opened / record_closed
event_data      json nullable  — cycle index, edit delta length,
                                 finalize duration, etc.
prompt_version  str(64) nullable
created_at      datetime
```

High write volume — expect 50-200 rows per record reviewed. Index on
`(doctor_id, created_at)` for drill-down queries. Retention: 90 days
rolling (drop older partitions/rows).

## API

```
POST /api/doctor/feedback
  body: { suggestion_id?, record_id, section, reason_tag,
          reason_text?, doctor_action }
  returns: { id, created_at }

POST /api/doctor/behavior/events
  body: { events: [{event_type, record_id, suggestion_id?, ...}, ...] }
  returns: { count }
  — batched for network efficiency; frontend buffers up to 10 events
    or 5s, whichever first

GET /api/doctor/feedback/digest?days=7
  returns: { total_shown, total_flagged,
             by_section: {...}, by_reason: {...},
             recent: [{...}, ...] }
  — feeds the MyAIPage "你的AI表现" card
```

## Files to Change

### Backend (new)
- `src/db/models/ai_feedback.py` — `AIFeedback` + `AIBehaviorEvent` models
- `alembic/versions/<new>_ai_feedback_tables.py` — create both tables
- `src/channels/web/doctor_dashboard/feedback_handlers.py` — three endpoints above
- `src/channels/web/doctor_dashboard/__init__.py` — register router

### Frontend (v2)
- `frontend/web/src/v2/pages/doctor/FieldWithAI.jsx` — add ⚠️ flag button
  next to 修改 on both pending and accepted rows
- New `frontend/web/src/v2/components/FeedbackSheet.jsx` — bottom sheet
  with reason-tag radios + free-text
- `frontend/web/src/v2/pages/doctor/MyAIPage.jsx` — new "你的AI表现" card
  showing weekly digest
- New `frontend/web/src/lib/behaviorLog.js` — batched event logger
  (buffer 10 events or 5s, POST, retry once on failure, drop on second
  failure — this is telemetry, not business logic)
- `frontend/web/src/api.js` — add `submitFeedback`, `postBehaviorEvents`,
  `getFeedbackDigest` clients

### Prompt version tracking
- `src/domain/diagnosis_pipeline.py` — compute and attach
  `prompt_version = sha256(diagnosis.md)[:12]` to every emitted
  suggestion; stored on `ai_suggestions` (nullable column, new
  migration). Needed so feedback can attribute quality drift to a
  specific prompt commit.

## Phased Delivery

### Phase F1 — Explicit flag only (smallest shippable)
- `ai_feedback` table + POST endpoint
- ⚠️ button on FieldWithAI pending rows only (skip accepted for now)
- FeedbackSheet component
- No digest card on MyAIPage yet — flags land in DB silently, you query
  manually via `datasette` for the first week
- No passive behavior log
- No prompt_version (add later — ship the flag surface first)

Goal: start capturing ground truth within a week.

### Phase F2 — Passive behavior log
- `ai_behavior_event` table + batched POST endpoint
- `behaviorLog.js` client with buffer/retry
- Instrument ReviewPage events
- Still no doctor-facing digest

Goal: instrument the full signal surface.

### Phase F3 — Doctor-facing digest
- GET digest endpoint
- MyAIPage card rendering digest
- Drill-down list of recent flags

Goal: close the loop — doctors see that their flags matter.

### Phase F4 — Attribution + eval promotion
- `prompt_version` column on ai_suggestions
- Admin view: flags grouped by prompt_version, so regression after a
  prompt edit becomes visible
- Tool to promote a flagged suggestion → sniff test fixture

## Risks

- **Flag fatigue**: doctor flags once, nothing visibly happens, stops
  flagging. Mitigation: Phase F3 digest + a single-sentence email/WeChat
  notification "we acted on your N flags this week" when it's true.
- **High write volume on behavior log**: 50-200 events per record review.
  Mitigation: batched POST, 90-day rolling retention, MySQL partitioning
  if it becomes an issue.
- **Privacy**: `reason_text` is free-form. If doctor types patient
  identifiers, it leaks into our ops. Mitigation: explicit copy
  "不要输入患者姓名或身份证号 — 请描述 AI 建议本身的问题".
- **Regression to vanity metrics**: admin team obsesses over total-flag
  count. Mitigation: report digest as "flag rate per 100 shown" not raw
  count.
- **Prompt_version staleness**: computing sha256(diagnosis.md) at
  runtime assumes the file hasn't been edited mid-deploy. In practice
  deploys are atomic (systemd restart after git pull), so fine.

## Open Questions for Eng Review

1. Should `ai_feedback` and `ai_behavior_event` live in `patients.db`
   (same as other clinical data) or a separate telemetry DB? Easier to
   reason about retention + access control in a separate DB.
2. Batched event POST — server-side should accept partial success
   (some events valid, some malformed) or reject the whole batch?
   Leaning partial.
3. Flagging after 完成审核 — should the ✓ row keep its ⚠️ button
   forever, or lock after N days? (Clinical insight sometimes surfaces
   weeks later.)
4. Doctor can flag the same suggestion multiple times (doctor changes
   mind) — allow duplicates or UPSERT on (doctor_id, suggestion_id)?
   Leaning allow duplicates, each is a timestamped signal.
5. WeChat miniprogram parity — this plan is web-v2-only. WeChat users
   can't flag. Is that acceptable for Phase 1?

## Non-Goals

- Thumbs-up (positive feedback). Doctor approval is implicit in
  `decision=confirmed` — redundant surface.
- Public leaderboard / gamification. Zero.
- ML training on feedback. Phase F4 promotes flagged cases to eval
  fixtures manually, not via retraining.
- Admin UI for triaging flags. For now, query via datasette or a
  Python script — premature to build a UI until flag volume justifies.
