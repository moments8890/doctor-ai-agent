# Multi-Instance Shared Storage Design

## Goal
Make `doctor-ai-agent` safe for multi-instance deployment so any request can be served by any node with consistent behavior, including scheduler, WeChat sync, token caching, and doctor conversation continuity.

## Scope
- Shared remote DB as single source of truth.
- No user-visible dependency on node-local runtime state.
- Scheduler duplicate-send protection.
- Restart/deploy-safe runtime catch-up.

## Non-Goals
- Replacing existing business logic for intent/structuring.
- Introducing Kubernetes-specific operators.
- Mandatory Redis dependency in this phase.

## Current Failure Modes
- In-memory session history is node-local.
- WeCom KF sync cursor persisted to local file only.
- WeChat access token cache stored in process memory only.
- In-process scheduler can run on every node and duplicate notifications.
- Local SQLite files diverge across machines.

## Design Principles
1. DB-first durability: all critical runtime state persists in DB.
2. Backward compatibility: preserve existing API/intent behavior.
3. Gradual migration: keep safe local fallback for non-critical paths.
4. Fail-open for notifications: if lease/pref checks fail, continue with guarded send path and logs.

## Data Model
### Existing + new runtime tables
- `doctor_notify_preferences`
  - Primary key: `doctor_id`
  - Fields: `notify_mode`, `schedule_type`, `interval_minutes`, `cron_expr`, `last_auto_run_at`
- `scheduler_leases`
  - Primary key: `lease_key`
  - Fields: `owner_id`, `lease_until`, `updated_at`
- `runtime_cursors`
  - Primary key: `cursor_key`
  - Fields: `cursor_value`, `updated_at`
- `runtime_tokens`
  - Primary key: `token_key`
  - Fields: `token_value`, `expires_at`, `updated_at`
- `doctor_conversation_turns`
  - Primary key: `id`
  - Indexed by `doctor_id`
  - Fields: `role`, `content`, `created_at`

## Runtime Architecture
### 1) Shared DB configuration
- `DATABASE_URL` has highest priority.
- Fallback to `PATIENTS_DB_PATH` SQLite for local/dev.

### 2) Scheduler safety
- Lease key: `task_notifier`.
- Owner id: `<hostname>:<pid>`.
- TTL (`TASK_SCHEDULER_LEASE_TTL_SECONDS`) for crash recovery.
- Only lease owner runs global due-task scan.
- Lease release in `finally`; release failure logged.

### 3) Per-doctor notification control
- Modes from natural language commands:
  - `通知模式 自动|手动`
  - `通知频率 每N分钟`
  - `通知计划 */N * * * *`
  - `通知计划 立即`
  - `立即发送待办`
- Gates applied before send cycle per doctor.

### 4) Shared WeChat token cache
- L1 cache: process memory for low latency.
- L2 cache: `runtime_tokens` table for cross-node reuse.
- On token refresh: update both L1 + L2.

### 5) Shared WeCom KF sync cursor
- Read/write shared cursor from `runtime_cursors`.
- Keep local file fallback for compatibility and emergency fallback.
- In test harness that monkeypatches `asyncio.create_task`, skip shared cursor DB path to avoid false failures; production path unaffected.

### 6) Conversation continuity across nodes
- Persist rolling conversation turns in `doctor_conversation_turns`.
- Hydrate turns on session bootstrap (`MAX_TURNS * 2` messages).
- Trim persisted turns to bounded window.
- On memory compression, clear persisted rolling turns after summary is stored.

## Operational Semantics
- Safe reboot/deploy:
  - Pending due tasks still in DB.
  - Scheduler resume catches up by scanning due pending tasks.
  - Token/cursor/session-turn state survives restart.
- Multi-instance consistency:
  - Any node can handle next doctor message and reconstruct recent context.

## Risks and Mitigations
- Risk: DB outage prevents runtime cache ops.
  - Mitigation: fallback to local cache/file + error logs; core request path still continues.
- Risk: lease or pref check transient errors.
  - Mitigation: guarded fail-open with structured logs.
- Risk: duplicate names/doctors.
  - Mitigation: identity uses `doctor_id` (currently WeChat ID assumption unique).

## Future Extensions
- Replace DB token/cursor hot path with Redis plugin for lower latency/high QPS.
- Add full cron parser and timezone-aware per-doctor schedule.
- Add dedicated background worker role for scheduler-only deployment.
