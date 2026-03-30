# Claude Code Rules — Doctor AI Agent

## Planning Mode

When entering plan mode, write the execution plan to `plans/<short-slug>.md` before calling ExitPlanMode.

The plan file must include:
- **Goal** — one-line summary of what is being built or changed
- **Affected files** — list of files to create or modify
- **Steps** — numbered, concrete implementation steps
- **Risks / open questions** — anything that could go wrong or needs clarification

## Documentation Standards

All documentation lives under `docs/`. These are the canonical folders:

| Folder | What goes here | Naming |
|--------|---------------|--------|
| `docs/plans/` | Active implementation plans | `YYYY-MM-DD-<feature-name>.md` |
| `docs/plans/archived/` | Completed plans (for traceability) | same |
| `docs/specs/` | Design specs (brainstorm output, architecture decisions) | `YYYY-MM-DD-<topic>-design.md` |
| `docs/product/` | Product strategy, requirements, gap analysis, UX reviews | descriptive name |
| `docs/review/` | Dated code/architecture reviews (create when needed) | `docs/review/MM-DD/<title>.md` |
| `docs/qa/` | QA reports, simulation results, UI checkpoint screenshots | descriptive name |
| `docs/dev/` | Developer guides (setup, LLM providers, simulation, test strategy) | descriptive name |
| `docs/deploy/` | Deployment & infrastructure guides | descriptive name |
| `docs/release/` | App store submission, compliance materials | descriptive name |
| `docs/ux/` | UX design spec, wireframes, mockups | descriptive name |

### Rules for all agents (including superpowers skills)

1. **Do NOT write to `docs/superpowers/`.** This prefix is deprecated. Use the folders above.
2. Plans go to `docs/plans/`, specs go to `docs/specs/`, product docs go to `docs/product/`.
3. When a plan is fully implemented (status ✅ DONE), move it to `docs/plans/archived/`.
4. Prefer updating an existing doc over creating a near-duplicate.
5. If a doc references stale file paths or old architecture, rewrite it — don't keep two versions.
6. Mockup HTML files go alongside their spec: `docs/specs/YYYY-MM-DD-mockups/`.
7. **Companion HTML for large docs:** Architecture and design docs over 200 lines MUST have a companion HTML visual version in the same directory. Link it at the top of the markdown: `> **Visual version:** [filename.html](filename.html)`. The markdown is the source of truth (AI reads it); the HTML is for human onboarding. When the markdown changes, update the HTML to match.

## Source of Truth

`README.md` § "Documentation" is the master registry.
The 5 entrypoints are: `AGENTS.md`, `docs/architecture.md`, `docs/product/README.md`,
`docs/ux/README.md`, `docs/dev/README.md`. Before creating a new doc, check if
a canonical entrypoint already covers the topic.

## Read Before Doing

Before starting any task, read the relevant docs for context:

| Task type | Read first |
|-----------|-----------|
| **Any feature work** | `docs/product/README.md` (product vision), `docs/architecture.md` (system design) |
| **Backend / API** | `docs/architecture.md` §3-6 (pipeline, intents, prompts, DB schema) |
| **Frontend / UI** | `docs/ux/README.md` (components, tokens), `docs/ux/design-spec.md` (UX flows) |
| **Diagnosis / CDS** | `docs/architecture.md` §7 (CDS pipeline) |
| **Patient portal** | `docs/architecture.md` §8 (channels) |
| **Prompts / LLM** | `src/agent/prompts/README.md`, `docs/dev/llm-prompting-guide.md` |
| **Testing** | `docs/TESTING.md`, `docs/dev/patient-simulation-guide.md` |
| **Deploy / Release** | `docs/dev/README.md`, `docs/deploy/tecenet-deployment/index.md` |
| **New feature design** | `docs/product/roadmap.md` (what's left), `docs/product/README.md` (product vision) |

Do not start implementation without understanding how your change fits the existing system.

## Code Style — Frontend

- **Flat icons only**: Use MUI outlined icons (`@mui/icons-material/*Outlined`). Never use emoji or Unicode symbols as icons. See UI-DESIGN.md principle #8.
- **Mock data shapes**: `mockApi.js` must return the same field structure as real backend APIs. Run `grep` on the backend handler to verify response shape before writing mock data.
- **Navigation back**: Always use `navigate(-1)` for back buttons, never hardcoded paths like `navigate("/doctor/settings")`.

## UI Design

Always read `docs/ux/README.md` before making any visual or UI decisions.
It defines which components to use for buttons, list rows, page layout,
knowledge base UI, and patient page patterns. Do not deviate without explicit user approval.

## UI Testing

Before release or after major frontend changes, run the 3-level UI audit
defined in `docs/dev/frontend-ui-audit.md`. This verifies features are
functional (Level 1), usable (Level 2), and fit real workflows (Level 3).
Save reports to `docs/qa/ui-audit-YYYY-MM-DD.md`.

## Bulk Edit Rules

Repetitive Edit/apply_patch loops across 3+ files are a **policy violation**
unless the agent explains why the CLI tools below are unsafe for that change.

**Tool selection by edit type:**
- **AST-aware code refactor** (JSX props, call shapes, function signatures):
  `sg -p 'old($A)' -r 'new($A)' -l tsx -U frontend/web/src/`
- **Plain text / regex replacement** (renames, labels, comments, imports):
  `fd -e jsx -e tsx -0 . frontend/web/src | xargs -0 sd 'old' 'new'`
- **Formatting after bulk edits:**
  - JS/JSX/TS/TSX: `npx biome format --write frontend/web/src/`
  - Python: `ruff format src/`
- **Linting autofix:**
  - JS/JSX/TS/TSX: `npx biome check --fix frontend/web/src/`
  - Python: `ruff check --fix src/`

**Required workflow for all bulk edits:**
1. **Preview** — `rg` or `sg scan` to confirm match count and candidate files
2. **Rewrite** — one bulk command
3. **Format** — `biome format --write` or `ruff format`
4. **Verify** — `git diff --stat` + targeted `rg` for old/new patterns

**Gotchas:**
- `ast-grep` can miss if pattern is not valid parseable code or wrong `--lang`
- `sd` replaces inside comments/strings unless file set is constrained
- `fd` ignores `.gitignore`d and hidden files by default
- Always use null-delimited pipelines: `fd -0 | xargs -0`
- Test on one file first for complex `ast-grep` patterns before repo-wide run

**When Edit is still correct:** changes to 1-2 files, or semantically complex
edits that require reading surrounding context to decide what to change.

## Code Style

- **In mermaid diagrams**, use `<br/>` for line breaks in node labels, never `\n`.
- **Python 3.9 compatibility** — always use `from __future__ import annotations` at the top of new files; use `Optional[X]` not `X | None`, `Tuple[...]` not `tuple[...]`
- **No auto-commit** — NEVER run `git commit` or `git add` unless the user explicitly says "commit". This is critical. Make code changes only — the user will commit when ready.
- **Preserve medical abbreviations** — do not translate or expand STEMI, BNP, PCI, EGFR, ANC, HER2, EF, NYHA, ICD, etc.
- **Tests mock all I/O** — unit tests in `tests/` must not make real LLM, DB, or network calls; use `AsyncMock` / `patch`
- **Testing policy** — integration tests are required for safety-critical modules (diagnosis pipeline, clinical decision support). For other modules, do not add unit tests unless the user explicitly asks. Prefer integration/E2E replay tests over unit tests for prompt-related changes.
- **Enums over strings** — use `(str, Enum)` for any DB column or Pydantic field with a fixed set of values (status, role, task_type, category, etc.). Never use raw strings with inline comments listing allowed values. This applies to all models in `src/db/models/` and `src/agent/types.py`.
- **DB schema changes** — add to `src/db/models/`; `create_tables()` handles creation automatically; document any manual cleanup/migration impact in the commit message and PR description
- **No Alembic migrations** — do not create or run Alembic migrations until first production launch; for dev, use `create_tables()` or manual `ALTER TABLE` statements
- **LLM provider defaults** — local model is `qwen3.5:9b` via Ollama; prefer this in examples and defaults

## Configuration
- `config/runtime.json` is the **sole local configuration file** — never create or suggest `.env` / `.env.local` for the main application
- `config/runtime.json` is gitignored; `config/runtime.json.sample` is the reference template
- Scripts under `scripts/` may use `python-dotenv` standalone, but this does not affect the main app
- **Always prefer the LAN inference server (`http://192.168.0.123:11434`) over local Ollama** — set `OLLAMA_BASE_URL` and `OLLAMA_VISION_BASE_URL` to the LAN address in `config/runtime.json`; never use `ollama serve` locally
- **Test server runs on port 8001** — ALL tests under `tests/` (E2E, integration, patient sim, prompt tests, scenario tests) MUST run against port 8001, never 8000. Port 8000 is the dev server with real data. Start the test server with: `PYTHONPATH=src ENVIRONMENT=development uvicorn main:app --port 8001`
- **Patient sim runs on port 8001** — `scripts/run_patient_sim.py` must use `--server http://127.0.0.1:8001`
- **Default LLM provider for tests** — use `groq` as the default LLM provider when running tests and simulations

## Codex Execution Rules

- **Full permissions** — Codex has full permission to run commands needed to complete tasks.
- **Complex task decomposition** — for complex tasks, break work into smaller subtasks and spawn sub-agents when beneficial.
- **Development default** — prefer code changes plus doc updates without adding tests. For verification, favor integration / E2E / chatlog replay over new unit-test coverage during this phase.

## Branch & PR Workflow

Direct pushes to `main` are allowed.

### Steps for every change

1. **Testing** — integration tests are required for safety-critical modules (diagnosis pipeline). For other modules, do not add unit tests unless explicitly requested
2. **Integration tests** — `pytest tests/integration/` — run when the LLM pipeline, prompts, or end-to-end workflow behavior changed
3. **Corpus/E2E replay** — `bash scripts/test.sh chatlog-full` — use for human-language regression checks on meaningful workflow changes
4. **Document changes in commit message** — include what changed and any migration/manual cleanup impact
5. **Update `docs/architecture.md`** — only if schema, env vars, API endpoints, or service structure changed
6. **Update progress** — tick completed items in `docs/debug/iteration_*.md`
7. **DO NOT RUN TESTS** - do not run tests during normal development (dont run the tests to validate)
8. **Pre-push gate** — before pushing, run `/test-gate` to validate no regressions against the existing test suite

### Publishing (Direct to Main)

After the above:

```bash
# 1. Commit your changes
git commit -m "<type>: <short-description>"

# 2. Push directly to main (GitHub + Gitee)
git push origin main
git push gitee main
```

- **User shorthand rule** — if the user says `push`, treat it as a direct push to `main` on both remotes: `origin` and `gitee`

- Commit message prefixes: `feat:`, `fix:`, `ci:`, `refactor:`, `docs:`


## Browser Testing

Two tools available — use the right one for the job:

| Tool | Speed | Resolution | Best for |
|------|-------|------------|----------|
| **gstack browse** | ~100ms/cmd | Standard | QA flows, quick checks, most daily work |
| **Playwright MCP (Edge)** | Slower (browser launch) | High (retina) | High-res screenshots, complex DOM interaction |

**Default to gstack browse** for all QA and browser testing. It's faster and needs
no browser installation. Only use Playwright MCP when you need high-res screenshots
or interactions gstack browse can't handle.

Playwright MCP is configured with `--browser msedge` (see plugin config). When using
Playwright, set viewport to desktop size (`1440×900`) for admin pages.

### gstack browse quick reference
```bash
B=~/.claude/skills/gstack/browse/dist/browse
$B goto http://localhost:5173
$B snapshot -i          # interactive elements
$B screenshot /tmp/x.png
$B console --errors
```

### QA Screenshot Walkthrough

Every QA session **must** produce a walkthrough HTML with embedded screenshots:

1. Create a dated session directory: `docs/qa/YYYY-MM-DD-<feature>/`
2. Save screenshots to `snapshots/` subdirectory
3. Save test assets (generated images, PDFs) to `test-assets/` subdirectory
4. Create `index.html` at session root with:
   - Filter bar (by input type: image, text, voice, pdf, edge, frontend, bugs)
   - Summary stats (total, pass, fail)
   - Each test as an expandable card: status badge, category badge, title, time, details
   - **Screenshots embedded as `<img>` tags** inside each card's detail section
   - Self-contained styling (no external deps)
5. Optionally create `qa-report.md` alongside for text-based summary
6. Reference files via relative paths (`snapshots/`, `test-assets/`)
7. Never put PNGs at `docs/qa/` root — always inside a session directory
8. Every screenshot taken during QA **must** appear in the walkthrough HTML — do not leave orphan PNGs

## Codebase Review Policy

When doing codebase reviews:
- **Non-logical fixes** (security, cleanup, hardening, dead code) → apply in bulk without per-item confirmation
- **Logical bugs** (wrong behavior) → discuss one by one with concrete examples, propose fix, wait for confirmation before applying
- If user says "do not touch" a category, respect that strictly

## E2E Failure Debugging Policy

When debugging failures in E2E / MVP benchmark tests:
1. **Investigate only** — diagnose the root cause (read code, check patterns, trace the flow)
2. **Do NOT make code or expectation changes** — never auto-fix the failing test, the benchmark JSON, or the product code
3. **Always ask the user** — present findings and ask which fix direction to take (e.g. fix product code vs. relax benchmark expectations vs. mark as known limitation)
4. This applies to all files: benchmark JSON, fast router patterns, handler logic, etc.

## Design Artifacts

When working on a design (spec, plan, or architecture document), always include a **workflow diagram** (mermaid) that shows the critical parts and their interactions with the current system. This applies to specs in `docs/specs/`, plans in `docs/plans/`, and any design discussion that will be saved. The diagram should show data flow, component boundaries, and how new pieces connect to existing modules.

## Cascading Impact Analysis

Every new feature design, spec, or plan **must** include a **Cascading Impact** section before implementation begins. Enumerate all downstream effects the change has on the existing system:

1. **DB schema** — new columns, altered types, removed fields; verify `create_tables()` / `_backfill_missing_columns()` will handle them; note any manual cleanup for existing data
2. **ORM models & Pydantic schemas** — which models in `src/db/models/` and request/response schemas need updating
3. **API endpoints** — new routes, changed request/response shapes, deprecated endpoints
4. **Domain logic** — functions, services, or pipelines whose behavior or signatures change
5. **Prompt files** — any `prompts/*.md` that reference changed fields, workflows, or terminology
6. **Frontend** — pages, components, API calls, or mock data that must be updated to match backend changes
7. **Configuration** — new env vars, `runtime.json` keys, or feature flags
8. **Existing tests** — tests that will break or need new fixtures/assertions
9. **Cleanup** — dead code, orphaned files, stale imports, or deprecated paths to remove

If a category has no impact, write "None." Do not omit the category. This section is the authoritative checklist for the implementation plan's scope — nothing ships until every item is addressed or explicitly deferred.

## Workflow

1. Never auto-implement code changes without explicit user approval. When reviewing specs, plans, or designs, present findings and wait for confirmation before writing code.
2. When reverting changes, revert ONLY the specific files/commits requested. Always confirm scope before reverting. Never revert unrelated files (e.g., AGENTS.md, config files) unless explicitly asked.
3. This is a production medical AI application, not a hackathon/demo. All code should be production-quality with proper error handling, logging, and testing.
4. Primary languages: Python (backend/AI), JavaScript (frontend), Markdown (docs/prompts). Use Chinese (中文) for user-facing strings and medical terminology. JSON keys should be English.
5. Before using sed for file modifications, prefer the Edit tool. sed has corrupted files multiple times in this project. If sed is necessary, always verify file integrity afterward.
6. After deleting or moving any module/class/function, immediately grep for all imports and references to that symbol and update them. Run tests before committing deletion changes.
7. **Implementation plan completion** — after finishing an implementation plan:
   - Report progress to the user (what was done, any deviations from the plan)
   - Update the corresponding spec in `docs/specs/` to mark status as "Completed" with the completion date
   - Move the plan from `docs/plans/` to `docs/plans/archived/`
8. **Keep docs current** — whenever designing or implementing a feature, update all affected canonical documents. Start from the 5 entrypoints in `README.md` § "Documentation":
   - `docs/architecture.md` — if schema, services, pipelines, intents, prompt system, or module boundaries changed
   - `docs/product/roadmap.md` — if a roadmap item's status changed (started, completed, deferred)
   - `docs/ux/README.md` — if new components were added or existing patterns changed
   - `src/agent/prompts/README.md` — if prompt files, intent routing, or LLM contracts changed
   - Do not defer doc updates to a separate task — update docs in the same work session as the code change

## Skill Routine — Proactive Reminders

Claude should proactively suggest these skills at the right moments. Do not wait
for the user to ask — suggest when the trigger condition is met.

### Per-Task (suggest during work)

| Trigger | Skill | What to say |
|---------|-------|-------------|
| Editing `src/agent/prompts/**/*.md` | `/prompt-surgeon` | "This is a prompt edit — want me to run `/prompt-surgeon` for eval coverage?" |
| Bug report or "something's broken" | `/investigate` | "Let me use `/investigate` for structured root cause analysis." |
| Agent/prompt behavior change | `/sim` | "This changes agent behavior — want me to run `/sim` to verify?" |
| UI component or page changes | `/design-review` | "UI changed — want me to run `/design-review` for visual QA?" |
| Before pushing >5 changed files | `/review` | "Big change set — suggest running `/review` before push." |
| Completed a plan or >3 commits in session | `/report` | "Implementation done — want me to generate `/report` for a visual summary?" |
| After pushing to main | `/document-release` | "Just shipped — want me to run `/document-release` to sync docs?" |

### Per-Session (suggest at session boundaries)

| Trigger | Skill | What to say |
|---------|-------|-------------|
| Friday or end of a multi-day sprint | `/retro` | "End of the week — want a `/retro` to review what shipped?" |
| Starting a new feature design | `/plan-eng-review` | "Before implementing — want `/plan-eng-review` to check architecture?" |
| Product direction uncertainty | `/office-hours` | "Sounds like a product question — `/office-hours` can help clarify." |
| Big architectural decision | `/codex consult` | "Big decision — want a `/codex` second opinion?" |

### Monthly (suggest when >30 days since last run)

| Skill | Purpose |
|-------|---------|
| `/cso` | Security audit — secrets, dependencies, OWASP, LLM trust boundaries |
| `/cleanup` | Dead code, unused imports, stale docs, oversized modules |
| `/retro` | Monthly velocity and pattern review |

## Codebase Learnings

1. **Refactoring pattern** — before writing any code, create a plan that divides work into independent streams by directory/concern. Spawn sub-agents per stream with: owned directories, descriptive commits per logical change, no cross-scope edits. Review all changes together for import mismatches or interface contract breaks after agents complete.
2. **Pre-deployment QA audit** — check Alembic heads vs SQLAlchemy models, hit every FastAPI endpoint with test payloads, run patient sim with 5 cases, grep for deleted-module imports, verify env vars in `.env.example`. Produce PASS/FAIL markdown report.
3. **MUI icons** — verify the icon exists in the installed version before using. `FiberManualRecordIcon`, `RateReviewOutlinedIcon` are not available. Use CSS `Box` with `borderRadius: "50%"` for dots. Use `AssignmentOutlinedIcon` as a safe fallback.
4. **Mock API data** — `src/api/mockApi.js` must include ALL fields the real backend returns, even if unused by current frontend. Missing `patient_id` caused navigation bugs. Mark display-only extras with `// display-only, not in real API`.
5. **Git from project root** — always run `git add`/`git commit` from project root (`/Volumes/ORICO/Code/doctor-ai-agent`), not from `frontend/web/`. Paths resolve differently.
6. **ASR in China** — Browser Web Speech API uses Google ASR (blocked in China). Use `ASR_PROVIDER` env var: `browser` for dev, `tencent` for China prod. See `src/services/asr/provider.py`.
7. **Chinese text title extraction** — split on `：` (colon) before `。` (period). Max 20 chars for CJK. See `extract_title_from_text()` in `knowledge_crud.py`.
8. **WeChat nav pattern** — bottom nav on 4 main tabs only (我的AI/患者/审核/随访). Subpages hide bottom nav and show ‹ back chevron. All back navigation uses `navigate(-1)`, never hardcoded paths. See UI-DESIGN.md §3C.

