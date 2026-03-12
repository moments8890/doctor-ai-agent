# MVP Hero Loop — Execution Progress

Tracking file for the [execution plan](./mvp-hero-loop-execution-plan.md).
Last updated: 2026-03-12

---

## Review follow-up

A 2026-03-12 architecture re-review identified several closure gaps that
remained material even though the core MVP work shipped. Those items were
tracked in:

- [`architecture-gap-closure-plan-2026-03-12.md`](./architecture-gap-closure-plan-2026-03-12.md)

**All five closure workstreams are now complete** (2026-03-12):

- WS1: Doctor-scope authority fixed (workbench endpoints use resolved_id)
- WS2: Workbench context hydration (hydrate_session_state before get_session)
- WS3: Voice wired through shared workflow (draft-first safety model)
- WS4: Adapter convergence (parse_inbound/format_reply wired; send stubs deferred)
- WS5: Architecture docs and progress tracker updated to match shipped state

---

## Phase 0. Freeze scope and release rules

Status: **done**

- [x] MVP contract written in execution plan
- [x] P0 / P1 / Deferred labelling applied
- [x] Non-goals section documented
- [x] ADR 0004 (WeChat channel choice) and ADR 0005 (bounded compound intents) authoritative

---

## Phase 1. Harden the workflow semantics first

Status: **done** (delivered in commit `87be0cb` — Phase 1-4 intent workflow overhaul)

- [x] Hero-loop transaction explicit in shared workflow (`services/intent_workflow/`)
- [x] 5-layer pipeline: classify -> extract -> bind -> plan -> gate
- [x] Bounded compound-intent policy (planner.py): create+record, create+task, auto-create+record
- [x] Gate blocks write intents without patient
- [x] Shared text normalization for create/add-record compounding (`compound_normalizer.py`)
- [x] Deterministic fast paths for greetings, task completion, patient count
- [x] Clinical signal detection in `entities.py`

---

## Phase 2. Converge Web and WeChat onto the same workflow

Status: **done** (core convergence complete; remaining items deferred)

### Shared handler unification (HandlerResult pattern)

- [x] `HandlerResult` dataclass in `services/domain/intent_handlers/_types.py`
- [x] `handle_add_record` — unified in `_add_record.py` (Web + WeChat)
- [x] `handle_create_patient` — unified in `_create_patient.py`
- [x] `handle_query_records` — unified in `_query_records.py`
- [x] `handle_delete_patient` — unified in shared handlers
- [x] `handle_list_patients` — unified in shared handlers
- [x] `handle_list_tasks` — unified in shared handlers
- [x] `handle_complete_task` — unified in shared handlers
- [x] `handle_schedule_appointment` — unified in shared handlers
- [x] `handle_update_patient` — unified in shared handlers
- [x] `handle_update_record` — unified in shared handlers
- [x] `handle_cancel_task` — unified in shared handlers
- [x] `handle_postpone_task` — unified in shared handlers
- [x] `handle_schedule_follow_up` — unified in shared handlers
- [x] Web `records.py` dispatches through `_result_to_response(shared_handler(...))`
- [x] WeChat `wechat_flows.py` dispatches through `_hr_to_text(shared_handler(...))`

### Single-patient auto-bind

- [x] Promoted from WeChat-only to shared `_resolve_patient_name()` in `_add_record.py`
- [x] Web now also auto-binds when doctor has exactly one patient

### Patient-switch notification as separate field

- [x] `HandlerResult.switch_notification: Optional[str]` added
- [x] `ChatResponse.switch_notification: Optional[str]` added (Web wire format)
- [x] `_result_to_response()` passes through `switch_notification`
- [x] `_query_records.py` — sets `switch_notification` instead of prepending to reply
- [x] `_add_record.py` — sets `switch_notification` instead of prepending to reply
- [x] `_create_patient.py` — sets `switch_notification` instead of prepending to reply
- [x] WeChat `_hr_to_text()` helper prepends notification as separate line
- [x] All WeChat dispatch paths use `_hr_to_text()` for handlers that may switch patients
- [x] Old inline prepend cleaned up (legacy `records_intent_handlers.py` deleted)

### Deferred to next cycle

- [x] Wire `ChannelAdapter` protocol (`services/domain/adapters/`) into routers -- **done** (WS4): `parse_inbound` and `format_reply` wired; `send_reply`/`send_notification` documented as deferred stubs
- [x] Legacy `records_intent_handlers.py` deleted (all handlers now in shared layer)
- [x] `wechat_domain.py` cleaned — only WeChat-unique functions remain
- [ ] Confirm equivalent workflow outcomes via E2E corpus replay on both channels

---

## Phase 3. Tighten the Web workbench as the MVP front door

Status: **done** (core workbench shipped; remaining polish deferred)

- [x] Composer-first layout with working-context header (commit `f821126`)
- [x] Context API serving current patient + pending draft state

### Deferred to next cycle

- [ ] First-run doctor flow (no patient -> create prompt)
- [x] Visible pending-draft state in workbench header — `next_step` now shows alongside `pending_draft`
- [ ] Next-step affordance when blocked (e.g. "confirm or abandon draft")
- [x] Doctor profile fields (visit_scenario, note_style) — wired DB → session → LLM prompt → UI settings

---

## Phase 4. Turn the benchmark into a real release gate

Status: **done** (tooling complete; hero-loop cases need live validation)

- [x] Standardize one benchmark command targeting `:8001` (`bash scripts/test.sh hero-loop`)
- [x] Machine-readable JSON output (`reports/candidate/hero.json`)
- [x] Baseline vs candidate comparison automation (`scripts/compare_baseline.py`)
- [x] Save baseline script (`scripts/save_baseline.sh`)
- [x] Lock MVP benchmark dimensions (binding, draft lifecycle, compound, query, fatal errors)
- [x] MVP accuracy benchmark dataset (`e2e/fixtures/data/mvp_accuracy_benchmark.json`)

### Deferred to next cycle

- [ ] Extend benchmark corpus with full acceptance-scenario coverage (scenarios 2, 5, 6 from execution plan)
- [ ] Markdown comparison summary output (currently terminal-only)

---

## Phase 5. Make benchmark review part of the release cadence

Status: **done**

- [x] Release checklist with benchmark gate: [`mvp-release-checklist.md`](./mvp-release-checklist.md)
- [x] Baseline artifact storage convention documented (`reports/baseline/{sha}-hero.json`)
- [x] Regression = release blocker policy documented
- [x] P1 work must prove no P0 degradation (before/after hero-loop comparison required)

---

## Phase 6. Close the iteration explicitly

Status: **done**

- [x] Re-checked open work against MVP contract
- [x] Moved unfinished non-gating work to deferred sections in each phase
- [x] Release checklist updated with all gates
- [x] Carry-over list recorded (see below)

---

## Test health

As of 2026-03-12 (post-closure):
- **1645 passed**, 42 skipped, 0 failures
- Voice router rewritten to use shared 5-layer workflow (33 voice-specific tests)
- All shared handler mock targets updated for new module locations
- No regressions from closure work (WS1-WS5)
- Coverage target: >80% overall, >80% diff coverage on changed lines

---

## Release readiness

### Shipped (P0 hero loop)

- Shared 5-layer intent workflow pipeline (classify -> extract -> bind -> plan -> gate)
- Bounded compound-intent handling with safety gate
- All core handlers unified via `HandlerResult` pattern (Web + WeChat)
- Patient-switch notifications as structured field
- Single-patient auto-bind promoted to shared behavior
- Web doctor workbench: composer-first layout, working-context header, context API
- Hero-loop benchmark tooling: run, compare, save baseline
- Release checklist with benchmark regression gate

### Shipped (P1 supporting)

- ADR 0004 (prefer official WeChat channel) and ADR 0005 (bounded compound intents)
- State propagation across all patient-resolving handlers
- Clinical signal detection in entity extraction
- Per-layer latency tracking in workflow orchestrator
- Deterministic fast paths for low-risk commands

### Not shipped (deferred — non-gating)

See carry-over list below.

---

## Carry-over list

The following items are explicitly deferred to the next cycle. They are
**non-gating** for the current MVP release.

### Channel & adapter cleanup
- ~~Wire `ChannelAdapter` protocol into routers~~ -- **done** (WS4)
- ~~Remove legacy handler code~~ -- **done**: `records_intent_handlers.py` deleted, `wechat_domain.py` cleaned
- E2E corpus replay parity test (same input -> equivalent outcomes on Web, WeChat, Voice)

### Web workbench polish
- First-run doctor flow (empty state -> create patient prompt)
- Next-step affordance when blocked

### Secondary channel improvements
- Mini-program as independent surface
- Feishu / DingTalk channel adapters
- Patient portal work

### Admin dashboard expansion
- Broader admin/settings UI
- Doctor management beyond minimal profile

### Specialty feature expansion
- New specialty-specific structuring templates
- Specialty-aware routing rules

### Multi-intent execution planner
- General multi-intent planner beyond the bounded compound-intent policy
- Cross-turn intent chaining

### Broader evaluation automation
- CI-integrated benchmark runs (GitHub Actions)
- Markdown comparison summary output from `compare_baseline.py`
- Extended benchmark corpus covering all detailed acceptance scenarios
- Automated regression alerting
