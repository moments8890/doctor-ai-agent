You are performing a codebase cleanup audit for the doctor-ai-agent project.

## Architecture Context

The project has undergone multiple architecture iterations. Each left potential debris.
Read ALL design specs in `docs/superpowers/specs/` BEFORE scanning — they define what's current vs legacy.

### Design Specs (read in order, newest = most authoritative)

| Spec | Date | What changed | What it superseded |
|------|------|-------------|-------------------|
| `2026-03-18-react-mcp-architecture-design.md` | 03-18 | **ReAct agent replaces UEC pipeline** | `services/runtime/*`, intent handlers, DoctorCtx, compose, understand |
| `2026-03-17-patient-pre-consultation-design.md` | 03-17 | Patient interview pipeline (ADR 0016) | Old patient chat flow |
| `2026-03-17-wechat-miniapp-design.md` | 03-17 | WeChat Mini App thin shell | Direct WeChat H5 approach |
| `2026-03-16-medical-record-import-export-design.md` | 03-16 | Vision import + PDF export | Manual record entry only |
| `2026-03-15-web-frontend-simplification-design.md` | 03-15 | Frontend cleanup — dead pages/routes deleted | Old multi-page layout with HomeSection, ChatPage |
| `2026-03-15-structured-medical-record-fields-design.md` | 03-15 | Structured fields on records | Unstructured content-only records |

Also read:
- `src/agent/prompts/README.md` — current prompt architecture with mermaid diagrams
- `docs/superpowers/specs/adr/` — ADR documents (0011-0017) for historical decisions

### Cross-Spec Debris Patterns

Each spec may have left its own legacy:

**From 03-15 frontend simplification:**
- Dead frontend pages: `HomeSection.jsx`, `ChatPage.jsx`, duplicate draft confirmation code
- Old routes that should have been removed
- Working-context polling code marked for removal

**From 03-15 structured fields:**
- `_FIELD_KEYS` private list replaced by `OUTPATIENT_FIELDS` frozenset
- Dead `_build_structured_fields_from_record()` function (noted as dead code in spec)
- Old "always LLM" flow replaced by DB-first approach

**From 03-16 import/export:**
- `personal_history` field definition changed (no longer includes marital/reproductive)
- Any code still merging marital into personal_history

**From 03-17 patient interview:**
- Old patient chat flow (`patient-chat.md` prompt, `patient_pipeline.py` direct LLM call)
- Replaced by `advance_interview` tool + `patient-interview.md` prompt

**From 03-17 WeChat miniapp:**
- `wxmini_` stub doctors that should be cleaned up
- Any old H5 auth flow code

**From 03-18 ReAct agent (biggest change):**
- Entire `services/runtime/` pipeline (understand, compose, types, models, context, hooks)
- Intent handlers directory
- DoctorCtx/WorkflowState/MemoryState
- ActionType enum and all related dataclasses
- Removed LLM providers (openai, claude, gemini)

### Current Architecture (ReAct Agent)

```
Channel (Web / WeChat)
  → handle_turn(text, role, identity)         # src/agent/handle_turn.py
    → fast path (greeting, confirm/abandon)   # 0 LLM calls
    → SessionAgent.handle()                   # src/agent/session.py
      → LangChain AgentExecutor               # 1-4 LLM calls
        → @tool functions                     # src/agent/tools/doctor.py, patient.py
```

**Active modules (DO NOT flag):**
- `src/agent/` — handle_turn, session, setup, tools/, identity, archive
- `src/agent/prompts/` — doctor-agent.md, patient-agent.md, structuring.md, patient-interview.md, vision-*.md, report-extract.md
- `src/agent/tools/doctor.py` — query_records, list_patients, list_tasks, create_record, update_record, create_task, export_pdf, search_knowledge, search_patients, get_patient_timeline, complete_task
- `src/agent/tools/patient.py` — advance_interview
- `src/agent/tools/resolve.py` — name→ID resolution
- `src/domain/records/structuring.py` — medical record structuring (called inside create_record/update_record tools)
- `src/domain/patients/interview_turn.py` — interview engine (called inside advance_interview tool)
- `src/domain/records/confirm_pending.py` — pending draft confirmation
- `src/infra/llm/client.py` — provider registry (Chinese-focused: deepseek, groq, cerebras, sambanova, siliconflow, openrouter, tencent_lkeap, ollama)
- `src/channels/web/chat.py` — web channel
- `src/channels/wechat/router.py` — WeChat channel
- `src/db/` — all DB models, CRUD, engine

### Superseded by ReAct Agent (SHOULD be flagged)

These modules belonged to the UEC pipeline (ADR 0012/0013) and are replaced:

| Legacy module | Replaced by | Status |
|--------------|------------|--------|
| `services/runtime/turn.py` | `agent/handle_turn.py` + LangChain | Should be deleted or gutted |
| `services/runtime/understand.py` | Agent LLM handles reasoning | Delete entirely |
| `services/runtime/compose.py` | Agent LLM composes replies | Delete entirely |
| `services/runtime/types.py` | `@tool` definitions replace ActionType enum | Delete entirely |
| `services/runtime/models.py` | DoctorCtx/WorkflowState/MemoryState eliminated | Delete entirely |
| `services/runtime/context.py` | Only `archive_turns`/`get_recent_turns` survive | Gut to archive only |
| `services/runtime/resolve.py` | `agent/tools/resolve.py` | Delete if duplicated |
| `services/runtime/read_engine.py` | Called by @tool functions directly | May be dead |
| `services/runtime/commit_engine.py` | Called by @tool functions directly | May be dead |
| `services/runtime/dedup.py` | Moved to channel layer | Delete from runtime |
| `services/domain/intent_handlers/` | Agent decides which tool | Delete entire directory |
| `services/hooks.py` | 6 UEC hook stages no longer exist | Delete entirely |
| `prompts/understand.md` | Replaced by `prompts/doctor-agent.md` | Delete |
| `prompts/patient-chat.md` | Replaced by `prompts/patient-agent.md` | Delete |

### Superseded Concepts (flag code referencing these)

| Dead concept | What replaced it |
|-------------|-----------------|
| `ActionType` enum | LangChain `@tool` definitions |
| `UnderstandResult` / `ActionIntent` / `ResolvedAction` | Tool args + tool results |
| `DoctorCtx` / `WorkflowState` / `MemoryState` | Session history in memory |
| `load_context()` / `save_context()` | No ctx lifecycle |
| `RESPONSE_MODE_TABLE` (direct_reply, llm_compose, template) | Agent always generates reply |
| `Clarification` model (7 kinds) | Agent generates clarifications naturally |
| `ChannelAdapter` protocol | `handle_turn(text, role, identity)` is the interface |
| `compose_llm` (separate LLM for reads) | Agent sees tool result, summarizes |
| `draft_guard` / `pending_guard` | DB query in fast path |
| `memory_patch` / working_note / candidate_patient | Dead fields, retained for column compat only |

### Removed Providers (flag references)

| Removed | Reason |
|---------|--------|
| `openai` (GPT-4o) | Not Chinese-focused |
| `claude` (Anthropic) | Not Chinese-focused |
| `gemini` (Google) | Not Chinese-focused |

Flag any code that still references these providers (special-case headers for claude, openai model overrides, gemini API key env vars).

## Phase 1: Scan (read-only — do NOT modify any files)

Run ALL scans in parallel using subagents:

### 1A. Legacy UEC Code Still Present
Check if any of the "superseded" modules above still exist in `src/`. For each that exists:
- Count lines
- Check if any active code imports from it
- Determine: fully dead (delete) vs partially alive (gut) vs actively imported (migrate callers first)

### 1B. References to Dead Concepts
Grep `src/` for references to superseded concepts:
- `ActionType`, `UnderstandResult`, `ActionIntent`, `ResolvedAction`
- `DoctorCtx`, `WorkflowState`, `MemoryState`, `load_context`, `save_context`
- `RESPONSE_MODE_TABLE`, `compose_llm`, `draft_guard`, `pending_guard`
- `ChannelAdapter`, `Clarification`
- `memory_patch`, `working_note`, `candidate_patient`
Classify each reference: import, type annotation, runtime usage, comment, or dead code

### 1C. Dead Modules (beyond UEC)
Find Python files never imported by any other file:
- For each `.py` in `src/`, check if module name appears in any import
- Exclude: `__init__.py`, `main.py`, `conftest.py`, `scripts/`
- Cross-reference with active architecture above

### 1D. Unused Imports
For each Python file in `src/`, find imports never used in that file:
- Check each `import X` / `from X import Y` — is it referenced in the file body?
- Ignore: `from __future__ import annotations`, re-exports in `__init__.py`, `TYPE_CHECKING` guards

### 1E. Dead Functions/Classes
Find functions and classes defined but never called/referenced:
- Grep for each `def` and `class` definition
- Check for references (excluding definition line)
- Ignore: `@tool` decorated (LangChain), `@router` decorated (FastAPI), dunder methods, test fixtures

### 1F. Removed Provider References
Grep for: `openai` provider (not the library), `claude` provider, `gemini` provider, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `claude-sonnet`, `gpt-4o`
- In `runtime_config.py`, `client.py`, `structuring.py`, `interview_turn.py`, config files

### 1G. Duplicate Logic
Find similar patterns repeated across files:
- `_parse_tags()` — multiple implementations
- `AsyncOpenAI` client construction — repeated boilerplate
- Provider resolution with `_PROVIDERS.get()` — repeated pattern
- `json.loads()` with try/except fallback — repeated pattern

### 1H. Frontend Debris (from 03-15 spec)
Check `frontend/web/src/` for:
- Dead pages: `HomeSection.jsx`, `ChatPage.jsx`, or any page not wired in `App.jsx` routes
- Duplicate draft confirmation UI (should only exist in ChatSection.jsx confirm buttons)
- Working-context polling code marked for removal in spec
- Dead routes in `App.jsx` that point to removed pages
- Unused component imports

### 1I. Oversized Modules
Files over 300 lines — report line count, suggest split points

### 1J. Stale Documentation
Check these docs for references to deleted/superseded modules:
- `ARCHITECTURE.md`
- `CLAUDE.md`
- `AGENTS.md`
- `src/agent/prompts/README.md`
- `docs/dev/llm-providers.md`
- Cross-check each spec's "delete" section against actual codebase state

## Phase 2: Report

Present findings grouped by action type:

```
## Cleanup Report

### 1. Legacy UEC Modules (delete or gut)
[module path — line count — status — who imports it]

### 2. Dead Concept References (remove or migrate)
[file:line — concept — usage type — action]

### 3. Dead Code (safe to remove)
[file:line — function/class — evidence]

### 4. Unused Imports (safe to remove)
[file — import list]

### 5. Removed Provider References (clean up)
[file:line — what — action]

### 6. Duplicate Logic (consolidate)
[pattern — file locations — suggested single location]

### 7. Oversized Modules (split)
[file — line count — suggested splits]

### 8. Stale Documentation (update)
[file — what's stale — what it should say]
```

Confidence: HIGH / MEDIUM / LOW for each item.

## Phase 3: Plan

Ask the user: "Which categories should I clean up?"
Wait for response before proceeding.

## Phase 4: Execute

Only after user approval:
1. **Deletions** (dead modules, dead code, unused imports) → apply in bulk
2. **Migrations** (callers of legacy modules → new module paths) → one by one with examples
3. **Consolidation** (duplicate logic) → propose each, wait for confirmation
4. After all changes: verify no broken imports with a grep scan

## Rules

- NEVER modify files during Phase 1-2
- NEVER delete a file without checking for dynamic imports (`importlib`, `__import__`)
- NEVER remove code referenced in CLAUDE.md / AGENTS.md / ARCHITECTURE.md without flagging
- Check `git log --oneline -5 <file>` for recent activity before flagging
- Medical abbreviations (STEMI, BNP, etc.) are domain terms, not dead code
- DB model fields marked as "dead" in memory notes (working_note, candidate_patient, summary) are retained for column compatibility — flag but do NOT delete
- The `tags` column on records is still used by vision import, interview summary, and categorization — only structuring LLM stopped generating tags
