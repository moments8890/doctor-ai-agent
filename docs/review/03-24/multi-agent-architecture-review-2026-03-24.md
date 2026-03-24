# Multi-Agent Architecture Review — 2026-03-24

**Method**: 3 independent OpenAI Codex agents (gpt-5.4, reasoning=xhigh) each explored
the codebase independently, then debated each other's findings across 5 rounds.
15 substantive responses total. ~40M tokens consumed.

**Scope**: High-level directions, design principles, and systemic issues. No code changes.

**Post-review fixes (same session):**
- [x] Auth unified — single JWT system, deleted miniprogram_auth.py
- [x] Chat history durable — DB-backed via doctor_chat_log with in-memory cache
- [x] Stub surfaces removed — deleted review/diagnosis/case-history/label/prompt handlers + frontend cleanup
- [x] Cross-channel imports fixed — moved import_history to domain/records/
- [x] Duplicate DB tables cleaned — deleted chat_archive, patient_chat_log, consolidated needs_review→status
- [x] ARCHITECTURE.md updated to match reality
- [x] Legacy sweep — deleted 10 dead files, fixed 20+ stale references across src/tests/scripts
- [x] Patient portal auth bug fixed — _authenticate_patient signature corrected
- [ ] Process-local triage rate limits — accepted for now (resets on restart)
- [ ] Contract tests — not yet added
- [ ] Diagnosis as single action — future feature

---

## ROUND 1: Independent Assessment

All 3 agents independently explored 50-100+ files each, reading thousands of lines.
Their findings converged on 6 core issues:

### Unanimous Findings

| Issue | Agent 1 | Agent 2 | Agent 3 |
|-------|---------|---------|---------|
| Auth fragmented | "Split-brain doctor auth" | "Auth model internally inconsistent" | "No canonical auth/identity model" |
| Docs unreliable | "Docs are lagging fiction" | "Architecture docs not trustworthy" | "No stable source of truth" |
| Layering not enforced | "Partially real, not defended" | "Aspirational, not enforced" | "Channel layer not thin" |
| False coherence | "Product theatre" | "Mid-migration system with ghost subsystems" | "Benchmark/test story overstates confidence" |
| State fragility | "Too much state is ad hoc" | "Process-local memory for critical state" | "Bootstrap fragility — import-time side effects" |
| Config contradictions | "Config governance contradictory" | "Config/schema discipline inconsistent" | "Privacy/compliance not production-safe" |

### Unique Contributions Per Agent

- **Agent 1** coined "product theatre" — the frontend renders review queue, diagnosis,
  case library, working context while backend returns empty/placeholder data
- **Agent 2** identified process-local memory as critical — chat history, escalation
  throttling, notification batching all in module globals, lost on restart
- **Agent 3** flagged privacy/compliance — `llm.py` writes full prompts to disk,
  plaintext secrets in config, raw logs on disk; also caught test confidence inflation
  (skipped groups counted as passing)

### What All 3 Praised

- Constrained LLM pipeline (route -> dispatch -> handler) — not an unconstrained super-agent
- Safety-first escalation bias in triage
- PHI egress gating
- Real audit/observability investment
- Clinical workflow thinking is genuine, not demo engineering

### Key File References (from Agent 1)

- Auth split: `src/infra/auth/request_auth.py:25`, `src/infra/auth/unified.py:18`,
  `src/channels/web/patient_portal_auth.py:96`, `src/channels/web/auth.py:181`
- Product theatre: `src/channels/web/ui/review_handlers.py:15`,
  `src/channels/web/ui/diagnosis_handlers.py:13`, `src/channels/web/ui/briefing_handlers.py:117`
- Process-local state: `src/agent/session.py:8`, `src/domain/patient_lifecycle/triage.py:77`
- Layering leaks: `src/channels/web/chat.py:172` (web imports WeChat logic),
  `src/main.py:73` (wires channel into domain notifications)

---

## ROUND 2: Cross-Reaction

**Key outcome: Strong convergence, no substantive disagreements.**

All 3 agreed the combined findings are worse than any single one:

- Identity fragmentation + placeholder workflows + process-local state =
  **unreliable auditability in a medical product**
- Agent 1: "The biggest meta-problem is unresolved architecture ownership"
- Agent 2: "The core problem is that the system's guarantees are not yet canonical,
  enforced, or honestly represented"
- Agent 3: "Auditability is not reliable... the dangerous version of architectural mess"

### What Each Agent Admitted Missing

- **Agent 1 missed**: process-local state, bootstrap fragility, privacy/compliance
  severity, benchmark confidence inflation
- **Agent 2 missed**: silent fallback identities, prompt/log/secret handling as
  production blocker, product-sprawl pattern
- **Agent 3 missed**: exact auth fracture line (`wxmini_*` identity minting),
  UI/backend contract failure detail, durable-state issue

### Emergent Meta-Risk: Self-Deception

Agent 1: "The combination of stale docs, polished product surface, and inflated test
signals suggests self-deception risk inside the project. The team may believe the system
is more unified and validated than it is."

---

## ROUND 3: Root Causes, Priorities, Medical Safety

### 1. Root Cause — CONSENSUS: "Unresolved Architecture Ownership"

| Agent | Position |
|-------|----------|
| Agent 1 | "Unresolved architecture ownership" — no owner for canonical identity, workflow state, and runtime truth |
| Agent 2 | Same — "unresolved architecture ownership over shared primitives" |
| Agent 3 | "Absence of a single authoritative contract for identity, state, and safety" |

All 3 agreed: "too many products" is an **amplifier**, not the root cause. Missing
bounded contexts is the **design symptom**. The root cause is that no one owns the
canonical contracts.

### 2. Top 3 Fixes Before Any New Features — CONSENSUS

| Priority | All 3 Agents Agree |
|----------|-------------------|
| **#1** | Unify identity and auth — one principal model per actor, one verifier path, remove body/query fallbacks, remove `wxmini_*` auto-creation |
| **#2** | Make critical state durable — move session/escalation/cursor/notification/audit out of process memory |
| **#3** | Cut product surface to what's real — delete or hard-disable stubbed review/diagnosis/prompt surfaces, rewrite docs to match |

Plan-and-Act migration ranked **below** all three by all agents.

### 3. False Confidence — CONSENSUS: Structural, Not Awareness

All 3 agreed: better docs alone won't fix it. The code itself preserves dead APIs,
compatibility fallbacks, and contradictory semantics. The system **manufactures coherence**.

Specific examples:
- Briefing hardcodes `pending_review: 0` and `red_flags: 0` (`briefing_handlers.py:117`)
- No-op template upload (`export_template.py:114`)
- Treatment-plan loader returns `None` but triage code pretends to use it (`treatment_plan.py:16`)
- Tests skip removed groups and relax assertions to "non-empty reply" while reporting as passing

### 4. Medical Safety — CONSENSUS: Controls Undermined by Architecture

All 3 agreed: safety controls exist but are **not sufficient** because:

- Escalation bias exists, but on triage failure, patient portal falls back to generic
  "doctor will reply" instead of safety-preserving escalation (`patient_portal_chat.py:155`)
- PHI egress gates exist, but system logs PHI-bearing content to disk
  (`diagnosis.py:33`, `diagnosis.py:480`, `wechat_media_pipeline.py:80`)
- Auditability is compromised — patient actions logged under literal `"patient"`,
  doctor identity can be synthetic
- Notification/escalation state is process-local and lost on restart
- WeChat patient safety uses a different keyword gate than web triage — channel behavior
  is inconsistent

### 5. Strategic Direction — CONSENSUS: Narrow First, Broaden Later

All 3 said: collapse to one coherent slice, make it trustworthy, then expand.

---

## ROUND 4: Concrete Scope Definition

### The Slice — All 3 Agents Independently Proposed the Same Thing

**"Doctor-only web workbench"**: login -> AI chat -> structured record interview ->
patient/record lookup -> task management

#### STAY (all 3 agreed)

- Doctor auth (one token system)
- `channels/web/chat.py` — doctor AI chat
- `channels/web/doctor_interview.py` — structured record creation
- `channels/web/tasks.py` — task management
- `channels/web/ui/patient_detail_handlers.py` — patient/record read views
- `channels/web/ui/record_edit_handlers.py` — record editing
- `channels/web/ui/doctor_profile_handlers.py` — profile management
- Core agent pipeline: `agent/handle_turn.py`, `agent/types.py`, `agent/dispatcher.py`,
  `agent/handlers/*`
- DB models: `records.py`, `tasks.py`, `interview_session.py`, `patient.py`, `doctor.py`
- Domain: `patients/interview_session.py`, `interview_turn.py`, `completeness.py`
- Infra: `llm/client.py`, `llm/egress.py`, `llm/resilience.py`
- Observability: `observability.py`, `audit.py`, `turn_log.py`

#### CUT/SUSPEND (all 3 agreed)

- **Entire WeChat channel**: `channels/wechat/*`, `frontend/miniprogram/*`
- **Entire patient portal**: `patient_portal*.py`, `patient_interview_routes.py`,
  `PatientPage.jsx`
- **Fake doctor features**: `review_handlers.py`, `diagnosis_handlers.py`,
  `case_history_handlers.py`, `label_handlers.py`, `prompt_handlers.py`,
  working-context header, briefing dashboard
- **Admin/debug surfaces**: `AdminPage.jsx`, `DebugPage.jsx`, `admin_handlers.py`
- **Unified auth routes**: `unified_auth_routes.py`, `unified.py`
  (cut as the initial platform — see Round 5)

### WeChat Decision — UNANIMOUS: Suspend

All 3 agents independently said suspend WeChat:

- It's a second product, not a thin adapter
- Separate auth/binding, webhook runtime, background sync, media pipelines
- Mini-program client targets nonexistent `/api/mini/*` routes
- WeChat patient messages incorrectly route through doctor-shaped `handle_turn`
- Agent 1: "Strategic later, maybe. Strategic now, no."

If live users exist, leave a maintenance ACK/fallback reply path while product logic
is suspended.

### Migration Path — All 3 Agreed on Sequence

1. **Hide scope in frontend** — remove patient/admin/debug routes from `App.jsx`,
   remove review badges/dashboard chrome. Don't delete backend yet.
2. **Fix identity** — switch web login to mint same token format doctor APIs already
   verify. This is the true migration gate.
3. **Make conversation state durable** — replace in-memory `session.py` dict with
   DB-backed state. Pick one chat table, delete the duplicate.
4. **Extract WeChat import logic** — `chat.py:172` imports WeChat import code.
   Move to domain service before unmounting WeChat.
5. **Unmount cut routers** — change `main.py` so only doctor-web routers mount.
   Put WeChat, patient portal, unified auth, admin/debug behind legacy flags.
6. **Simplify frontend** — remove review/diagnosis from task page, fix task contract
   mismatch (frontend defaults `follow_up/medication/checkup`, backend accepts
   `general/review`).
7. **Delete dead code** — only after a quiet period confirms nothing breaks.

### LLM Architecture — CONSENSUS: Sustainable Only If Kept Narrow

- Good for doctor commands: bounds prompts, keeps tool scope small, makes failures local
- Not sustainable as whole product architecture
- Already showing limits: doctor-only `TurnContext`, lossy `deferred` string, role
  mismatch for patient flows
- **Recommendation**: keep router/dispatcher/handler for top-level intent selection.
  Move any durable flow into explicit workflow modules with DB state. Interviews,
  imports, review, diagnosis, and patient messaging should be workflow/state-machine
  problems that the router enters, not new intents.

### What Was Missed — CONSENSUS: Contract Governance

All 3 identified the same gap: the missing discipline is not "more tests" but
**contract governance** — who owns the truth between frontend, backend, docs, and tests.

Specific broken contracts found:
- Web login uses unified tokens, but APIs verify miniprogram tokens
- Frontend task enums don't match backend enums
- Patient registration mints portal tokens, but patient auth validates unified tokens
- `patient_portal_chat.py` calls `_authenticate_patient()` with wrong argument count
- Mini-program client calls nonexistent `/api/mini/*` routes
- Tests still target old namespaces (`services.ai.intent`)

---

## ROUND 5: Auth Debate, Diagnosis Viability, Data Architecture, Solo Dev

### Auth Direction — CONSENSUS SHIFTED to Agent 3's Position

All 3 agents converged: **use the older app/miniprogram token system for the initial
slice** (lower migration risk), not unified auth.

| Agent | Final Position |
|-------|---------------|
| Agent 1 | "Lower migration risk is Agent 3's direction" |
| Agent 2 | "I would change my earlier position. Lower-risk is Agent 3's direction" |
| Agent 3 | "Keep invite code for signup, add doctor web login that mints same app token format" |

**Reasoning**: unified auth is only wired at the login UI level; all doctor APIs still
verify the older token format. Migrating all APIs to unified auth is a repo-wide rewrite,
while migrating login to match existing APIs is a single-endpoint change.

**Concrete proposal**: keep invite code for doctor claim/signup only, add or repurpose
a doctor web login that looks up the doctor and issues the same `channel="app"` token,
leave downstream doctor APIs alone.

### Diagnosis Question — CONSENSUS: Cut Surfaces, Not Core Capability

All 3 agreed:

- Current diagnosis/review is **dead surface**, not working core — review queue and
  diagnosis APIs are stubs returning empty/501
- Cutting it leaves a viable product **if repositioned** as "AI intake + record
  creation + follow-up assistant"
- Not viable if promise remains "doctor diagnostic copilot"
- Keep one minimal diagnosis capability later: on-demand suggestions on record detail
  page via `diagnosis.py:389`
- **Do not rebuild the removed review queue system**
- Important detail: interview flow still creates `pending_review` records and review
  tasks — those write paths need cleanup when cutting review surfaces

### Data Architecture — CONSENSUS: No Redesign Needed

All 3 agreed the core schema is sound:

- `medical_records` is already well-structured with explicit SOAP columns (not just
  JSON blob) — `records.py:22`
- `interview_sessions` storing `collected` and `conversation` as JSON text is fine
  for ephemeral workflow state — `interview_session.py:24`
- **What needs cleanup**:
  - Duplicate chat tables: `chat_archive` (on doctor model) vs `doctor_chat_log` table
  - Duplicate patient tables: `patient_messages` vs `patient_chat_log`
  - Conflicting record edit policies: append-only versioning (`record_edit_handlers.py:56`)
    vs in-place mutation (`crud/records.py:120`)
  - `needs_review` and `status` on records duplicate each other
  - `UniqueConstraint("doctor_id", "name")` on patients will break on common-name
    collisions

### Solo Dev Reality — CONSENSUS: Changes Everything

All 3 agreed the solo dev context fundamentally changes the recommendation:

- Current surface area is **too wide for one person** to keep coherent
- A solo-dev architecture should **collapse surfaces**, not add "proper" subsystems
- Don't build a unified cross-role auth layer or full diagnosis UI first
- The right architecture is the boring one: one auth path per role, one canonical
  table per concept, one working flow per actor
- Agent 2: "I would not recommend a big unification push first"
- Agent 3: "The current repo has too many parallel concepts for one person"

---

## FINAL CONSENSUS SUMMARY

### The 6 Pillars (All 3 Agents Agree)

1. **Root Cause**: Unresolved architecture ownership — no canonical contracts for
   identity, state, or truth
2. **Auth**: Use older app/miniprogram token system for initial slice; add simple
   doctor web login that mints same token format
3. **Scope**: Doctor-only web workbench; suspend WeChat, patient portal, admin, and
   all stub surfaces
4. **State**: Move all critical state out of process memory into DB before scaling
5. **Safety**: Current controls are undermined by architecture — not safe for clinical
   production yet
6. **Strategy**: Narrow first to one coherent slice, make it trustworthy, then broaden

### Priority-Ordered Action Plan (Unanimous)

| Order | Action | Why |
|-------|--------|-----|
| 1 | Unify doctor auth to one token system | Foundation for everything else |
| 2 | Make session/escalation/audit state durable | Auditability is fiction without this |
| 3 | Cut all stub/dead product surfaces | Stop manufacturing false coherence |
| 4 | Extract WeChat import logic into domain service | Prerequisite to unmounting WeChat |
| 5 | Suspend WeChat channel | Second product, not thin adapter |
| 6 | Suspend patient portal | Different auth, different safety model |
| 7 | Consolidate duplicate DB tables | `chat_archive` vs `doctor_chat_log` etc. |
| 8 | Rewrite docs to match surviving system | Last step, not first |
| 9 | Add contract tests for kept surfaces | Prevent re-fragmentation |
| 10 | Re-enable diagnosis as single action, not subsystem | Product value, minimal architecture |

### Remaining Disagreements (Minor)

| Topic | Divergence |
|-------|------------|
| Product viability of narrow slice | Agent 1 leans toward "just infrastructure"; Agents 2+3 say viable if repositioned |
| "Too many products" as root cause vs amplifier | Agent 1 leans toward root cause; Agents 2+3 say amplifier |
| Whether to keep `LoginPage.jsx` | Agent 3 would cut it; Agents 1+2 would keep with modified backend |
| Knowledge/embedding system evaluation | Not deeply evaluated (Codex usage limit hit before Round 6) |

### What The Multi-Agent Discussion Surfaced That No Single Review Would Have

1. The **false confidence meta-risk** — docs, UI, and tests all independently
   overstate system maturity
2. **Identity + placeholders + process-local state** combine into unreliable
   auditability — the medical safety version of architectural mess
3. The **"product theatre"** pattern — polished shells around removed features
   are worse than openly missing features
4. **Contract governance** as the missing discipline — not "more tests" but
   "who owns the truth"
5. The **solo dev context** fundamentally changes what architecture is appropriate
6. The auth debate resolution — all 3 initially assumed "unify forward" but
   converged on "match existing APIs" after examining the code

---

## STRENGTHS WORTH PRESERVING

Despite the critical findings, all 3 agents independently praised these aspects:

1. **Constrained LLM pipeline** — route -> dispatch -> handler is a better
   architectural choice than an unconstrained super-agent with a bag of tools
2. **Safety-first design intent** — escalation bias, PHI egress gating, production
   startup guards, timing-attack mitigation in patient portal
3. **Real clinical workflow thinking** — patient interview, structured SOAP records,
   doctor knowledge grounding, specialty-aware prompting
4. **Genuine observability investment** — audit queue, turn logging, routing metrics
5. **Self-critical culture** — dated review docs show awareness of problems;
   the project is harder on itself than most
6. **Frontend design language** — real design system with component patterns,
   not generic MUI sludge

---

*Review conducted 2026-03-24. 3 independent Codex agents (gpt-5.4, reasoning=xhigh),
5 rounds, 15 substantive responses, ~40M tokens total.*
