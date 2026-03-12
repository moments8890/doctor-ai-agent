# Goal

Turn the current product and architecture reviews into one execution plan for a
Web-first MVP centered on a single doctor hero loop, a single benchmark gate,
and one shared workflow contract across channels.

# Status

- Proposed on 2026-03-11.
- Revised into an execution plan on 2026-03-11.
- Working release assumption: Web doctor workbench is the primary MVP surface.
- Supporting assumption: WeChat remains supported, but it must follow the same
  workflow semantics instead of defining MVP behavior independently.

# MVP contract

## Primary channel

- Web doctor workbench is the release-defining channel.

## Hero loop

- identify or create the patient
- dictate or append the clinical note
- create a pending draft
- explicitly confirm or abandon the draft
- query recent history or continue follow-up from the same patient context

## Product rules that must hold

- one visible working context per turn
- no silent patient rebinding
- no silent draft persistence
- one core patient-scoped transaction per turn
- only allowlisted same-turn compound intents
- unsupported mixed-intent turns clarify instead of executing partially

# In scope

- doctor-facing Web workbench flow
- shared workflow semantics for Web and WeChat
- bounded compound-intent handling
- benchmark automation on the dedicated `8001` deployment
- release checklist and benchmark cadence

# Out of scope for this cycle

- mini-program as an MVP-defining surface
- patient portal work
- broad admin/dashboard expansion
- new specialty feature expansion
- general multi-intent execution planner
- large onboarding/settings projects beyond minimal advisory doctor profile

# Success criteria

The iteration is successful only if all of the following are true:

1. A new doctor can complete the hero loop on Web without leaving the primary
   chat/workbench surface.
2. Web and WeChat produce equivalent workflow outcomes for the same core doctor
   messages.
3. The benchmark can be run by one standard command against `8001`, producing
   baseline-vs-candidate artifacts automatically.
4. Binding, draft confirmation, and unsupported mixed-intent behavior are
   benchmarked and treated as release blockers.
5. Non-MVP surfaces stay non-gating and do not redefine workflow semantics.

# Affected files

- Workflow and handler code in the shared domain and intent-workflow layers
- Web and WeChat channel adapters
- Doctor workbench frontend
- Benchmark scripts, dataset, and documentation
- Architecture / release-process documentation

# Execution phases

## Phase 0. Freeze scope and release rules

Target window: 1-2 days

Purpose:

- stop new scope drift before implementation starts

Implementation steps:

1. Convert the MVP contract above into the short release checklist used for this
   cycle.
2. Label current work as:
   - `P0 hero loop`
   - `P1 supporting`
   - `Deferred`
3. Explicitly mark non-gating surfaces and features as out of scope.
4. Treat ADRs and the AI contract as authoritative for:
   - draft-first persistence
   - turn-context authority
   - bounded single-turn compound intents

Deliverables:

- plan approved as the execution baseline
- one release checklist
- one non-goals section copied into the iteration tracker / release note

Exit criteria:

- every active engineering item maps to `P0`, `P1`, or `Deferred`
- no new MVP-scope work starts without fitting the hero loop

## Phase 1. Harden the workflow semantics first

Target window: 4-6 days

Purpose:

- make the backend behavior safe and deterministic before polishing UX

Implementation steps:

1. Make the hero-loop transaction explicit in the shared workflow:
   - patient identification or creation
   - add/update note draft
   - explicit confirm / abandon
   - query continuation
2. Implement the bounded compound-intent policy from ADR 0005:
   - allow:
     - `create_patient + add_record`
     - `create_patient + add_record + create_task`
     - `add_record + create_task`
     - `create/add_record + same-turn correction`
   - clarify:
     - `query + any write`
     - `update_record + create/add_record`
     - multiple-patient turns
     - destructive/admin + anything else
3. Replace residual keyword-gate logic with shared text normalization for
   create/add-record compounding.
4. Treat same-turn correction as rewriting the current unsaved payload, not as a
   second persisted `update_record`.
5. Keep deterministic fast paths only for exact low-risk commands:
   - greetings
   - task completion
   - patient count
   - similar exact command-style flows

Deliverables:

- one shared compound-intent normalization path
- explicit unsupported-combo clarification behavior
- updated workflow/gate semantics

Exit criteria:

- the core hero loop is defined by shared workflow logic, not channel-specific
  heuristics
- unsupported mixed-intent turns no longer partially execute

## Phase 2. Converge Web and WeChat onto the same workflow

Target window: 4-6 days

Purpose:

- remove semantic drift between channels

Implementation steps:

1. Identify the canonical shared surfaces for:
   - patient binding
   - pending draft creation
   - confirm / abandon
   - query continuation
   - compound-intent normalization
2. Move remaining business semantics out of channel-specific orchestration where
   the behavior should be identical.
3. Keep channel code responsible only for:
   - request/response shape
   - platform-specific formatting
   - platform-specific transport constraints
4. Document any temporary compatibility shim explicitly instead of letting it
   become a hidden fork.

Deliverables:

- reduced duplication in Web and WeChat core doctor flow
- one documented canonical workflow boundary

Exit criteria:

- the same doctor input corpus yields equivalent workflow outcomes on Web and
  WeChat
- channel code no longer defines different business rules for binding, draft
  state, or compound handling

## Phase 3. Tighten the Web workbench as the MVP front door

Target window: 3-5 days

Purpose:

- make the hero loop obvious and fast for first use

Implementation steps:

1. Keep `/doctor` composer-first and working-context-first.
2. Ensure the first screen always shows:
   - current patient or no active patient
   - pending draft state if any
   - next required action if blocked
3. Keep recent useful outputs visible in context:
   - latest draft preview
   - recent note/query result
   - immediate next-step affordance
4. Keep tasks/settings/admin reachable but secondary.
5. Add only minimal advisory doctor profile fields if they directly help
   routing or structuring:
   - specialty
   - common visit scenario
   - preferred note style

Deliverables:

- first-run doctor workbench flow
- visible working-context header
- minimal onboarding/profile capture if still justified after review

Exit criteria:

- a first-time doctor can complete the hero loop without entering a management
  page
- the page reads like a workbench, not a HIS-style dashboard

## Phase 4. Turn the benchmark into a real release gate

Target window: 3-5 days

Purpose:

- make accuracy review operational instead of manual

Implementation steps:

1. Standardize one benchmark command that targets the dedicated `8001` service.
2. Emit:
   - machine-readable JSON
   - short markdown comparison summary
3. Automate `baseline` vs `candidate` comparison.
4. Lock the first benchmark dimensions for MVP:
   - patient binding correctness
   - pending-draft lifecycle correctness
   - allowed compound-intent correctness
   - unsupported mixed-intent clarification correctness
   - query success rate
   - fatal error rate
5. Extend the MVP benchmark corpus with explicit hero-loop cases:
   - create + record + confirm
   - record + same-turn correction
   - record + task
   - query after saved note
   - unsupported mixed-intent clarification

Deliverables:

- one documented benchmark command
- baseline/candidate artifact format
- updated benchmark dataset and README

Exit criteria:

- any engineer can run the benchmark without tribal knowledge
- release review always includes a baseline-vs-candidate comparison from `8001`

## Phase 5. Make benchmark review part of the release cadence

Target window: 1-2 days to wire process, then ongoing

Purpose:

- keep the hero loop protected after the initial iteration

Implementation steps:

1. Add benchmark review to the release checklist.
2. Store one baseline artifact for every release candidate.
3. Treat regressions in the core MVP dimensions as release blockers.
4. Require any `P1` work to prove it does not degrade `P0` hero-loop behavior.

Deliverables:

- updated release checklist
- artifact naming/storage convention
- clear owner for reviewing benchmark diffs

Exit criteria:

- release review is benchmark-driven, not “it seems fine”
- hero-loop regression is visible before release, not after

## Phase 6. Close the iteration explicitly

Target window: 1-2 days

Purpose:

- prevent unfinished P1/P2 work from leaking into release scope

Implementation steps:

1. Re-check all open work against the MVP contract.
2. Move unfinished non-gating work out of the release path.
3. Update the architecture/review docs to match the actual shipped flow.
4. Record known follow-ups for the next cycle:
   - secondary channels
   - admin experience
   - specialty expansion
   - broader evaluation automation

Deliverables:

- final MVP release note / checklist
- updated architecture and benchmark docs
- explicit carry-over list

Exit criteria:

- shipped scope matches planned scope
- deferred work is visible and intentional, not hidden in the release branch

# Detailed acceptance scenarios

The following scenarios should all be explicitly covered before release:

1. `创建患者王芳，胸痛3天`
   - creates or reuses the patient
   - creates a pending draft
   - does not silently persist without confirmation

2. `创建患者王芳，胸痛，说错了，头痛`
   - creates or reuses the patient
   - drafts the final payload as `头痛`
   - does not save an intermediate `胸痛` record

3. `给张三补充胸闷，明天提醒复查`
   - creates one record draft
   - creates one reminder/task
   - preserves one patient scope

4. `查张三最近病历`
   - returns query output only
   - does not trigger write-path side effects

5. `查张三最近病历并把诊断改成高血压`
   - does not partially execute
   - asks the doctor to choose query or correction first

6. `创建赵六，再删除王芳`
   - does not partially execute
   - asks for clarification / one primary action

7. The same scenario above yields equivalent workflow results on Web and WeChat.

# Risks / open questions

- The biggest implementation risk is still Web/WeChat drift; if shared workflow
  logic is not pulled up early, one channel will get the new semantics and the
  other will quietly diverge.
- Benchmark metric definitions must converge quickly. If the team keeps
  re-debating metrics, the release gate will remain ceremonial.
- Minimal doctor profile capture should stay small. If it turns into settings
  expansion, it will dilute the MVP.
- Some pending-draft confirmation paths may still need benchmark-runner
  improvements if the current runner cannot express the full confirmation loop.
- If leadership decides the next release must be WeChat-first instead of
  Web-first, the sequencing stays mostly the same, but Phase 3 ownership and
  benchmark prioritization need to shift immediately.
