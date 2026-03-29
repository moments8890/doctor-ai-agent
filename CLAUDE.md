# Claude Code Rules — Doctor AI Agent

## Source of Truth

- `AGENTS.md` is the authoritative repo instruction file for workflow, testing
  policy, planning, and push behavior.
- Claude should read and follow `AGENTS.md` first when both files are present.
- If `CLAUDE.md` and `AGENTS.md` ever differ, `AGENTS.md` wins.
- Do not duplicate shared repo policy in this file. Update `AGENTS.md` instead.

## Purpose

- This file exists only as a compatibility pointer for tools that look for
  `CLAUDE.md`.
- After reading this file, load `AGENTS.md` and use that as the operative
  instruction set.

## Session Hygiene

- After finishing a self-contained task, suggest a fresh session (`/clear` or
  new terminal), especially before starting unrelated work.
- Suggest `/compact` when the task changes phase (exploration → implementation,
  bug A → bug B, backend → frontend), when old context is no longer needed, or
  around 30-50 turns in a continuing session.
- Strongly suggest reset for marathon sessions or when re-summarizing old context.
- **NEVER call `/compact` yourself** — only suggest it. The user decides when to
  compact.

## Subagent Rules (CRITICAL for performance)

- **Default max 2 parallel agents.** Use 1 when tasks share files, context, or
  rate-limited tools. 3+ requires explicit user approval.
- **Soft budget: ~20-30 tool calls per agent.** If an agent exceeds ~15 calls
  without converging on a concrete result, stop and reassess approach.
- **Bulk mechanical edits use CLI tools, not Edit loops** — see Bulk Edit Rules
  below.
- **Use cheaper models for low-risk mechanical tasks** (`model: "haiku"` for
  renames, search-replace, formatting). Reserve sonnet/opus for semantically
  complex or high-consequence work.
- **Prefer inline work** unless a subtask is clearly independent, non-blocking,
  and substantial enough to justify delegation.
- **Never spawn agents for:** single-file edits, trivial lookups, simple search
  tasks, or validation-only busywork a single command can confirm.
- **Never delegate the critical path** — if the next step depends on the result,
  do it inline.
- **Pre-spawn test** — before spawning, confirm all three:
  1. Is this independent? 2. Is it non-blocking? 3. Would inline slow the main path?
  If not all true, don't spawn.
- **Each agent must have:** concrete goal, owned files, explicit non-goals, and
  expected output format. Vague prompts cause exploration bloat.
- **One exploration owner** per subproblem — never let multiple agents duplicate
  repo discovery.
- **Stop conditions:** terminate agents that are retrying, reopening the same
  files, or bouncing between search/edit/verify without convergence.
- **No recursive delegation** — agents must not spawn more agents.
- **Close agents promptly** after completion. No idle agents kept alive.

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

- In mermaid diagrams, use `<br/>` for line breaks in node labels, never `\n`.

## Learnings

1. I need to refactor [FEATURE] across the codebase. Before writing any code, create a plan that divides work into independent streams by directory/concern. Then spawn sub-agents for each stream with these rules: 1) Each agent works ONLY on files in its assigned directories, 2) Each agent creates a descriptive commit for each logical change, 3) No agent modifies files outside its scope, 4) After all agents complete, review all changes together for cross-cutting issues like import mismatches or interface contract breaks. Present the full plan and stream assignments for my approval before spawning any agents.
2. Run a pre-deployment QA audit for the doctor-ai-agent app. Steps: 1) Check all Alembic migration heads match the SQLAlchemy models—flag any column in models not in migrations or vice versa. 2) Start the FastAPI server locally and hit every endpoint defined in the router files with valid test payloads, checking for 500s or unhandled exceptions. 3) Run the patient simulation pipeline against the local server with 5 sample cases and validate responses with the LLM judge. 4) Check for any imports referencing deleted modules (`grep -r` for known removed modules). 5) Verify all environment variables referenced in code exist in .env.example. Produce a markdown report with PASS/FAIL for each check and block-quoted error details for any failures.
3. MUI icons: verify the icon exists in the installed version before using. `FiberManualRecordIcon`, `RateReviewOutlinedIcon` are not available. Use CSS `Box` with `borderRadius: "50%"` for dots. Use `AssignmentOutlinedIcon` as a safe fallback.
4. Mock API data (`src/api/mockApi.js`) must include ALL fields the real backend returns, even if unused by current frontend. Missing `patient_id` caused navigation bugs. Mark display-only extras with `// display-only, not in real API`.
5. Always run `git add`/`git commit` from project root (`/Volumes/ORICO/Code/doctor-ai-agent`), not from `frontend/web/`. Paths resolve differently.
6. Browser Web Speech API uses Google ASR — blocked in China. Use `ASR_PROVIDER` env var: `browser` for dev, `tencent` for China prod. See `src/services/asr/provider.py`.
7. Chinese medical text title extraction: split on `：` (colon) before `。` (period). Max 20 chars for CJK. See `extract_title_from_text()` in `knowledge_crud.py`.
8. WeChat nav pattern: bottom nav on 4 main tabs only (我的AI/患者/审核/随访). Subpages hide bottom nav and show ‹ back chevron. All back navigation uses `navigate(-1)`, never hardcoded paths. See UI-DESIGN.md §3C.
