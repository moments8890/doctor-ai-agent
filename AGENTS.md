# Claude Code Rules — Doctor AI Agent

## Planning Mode

When entering plan mode, write the execution plan to `plans/<short-slug>.md` before calling ExitPlanMode.

The plan file must include:
- **Goal** — one-line summary of what is being built or changed
- **Affected files** — list of files to create or modify
- **Steps** — numbered, concrete implementation steps
- **Risks / open questions** — anything that could go wrong or needs clarification

## Code Style

- **Python 3.9 compatibility** — always use `from __future__ import annotations` at the top of new files; use `Optional[X]` not `X | None`, `Tuple[...]` not `tuple[...]`
- **No auto-commit** — never commit unless explicitly asked
- **Preserve medical abbreviations** — do not translate or expand STEMI, BNP, PCI, EGFR, ANC, HER2, EF, NYHA, ICD, etc.
- **Tests mock all I/O** — unit tests in `tests/` must not make real LLM, DB, or network calls; use `AsyncMock` / `patch`
- **Testing policy** — integration tests are required for safety-critical modules (diagnosis pipeline, clinical decision support). For other modules, do not add unit tests unless the user explicitly asks. Prefer integration/E2E replay tests over unit tests for prompt-related changes.
- **DB schema changes** — add to `db/models/`; `create_tables()` handles creation automatically; document any manual cleanup/migration impact in the commit message and PR description
- **No Alembic migrations** — do not create or run Alembic migrations until first production launch; for dev, use `create_tables()` or manual `ALTER TABLE` statements
- **LLM provider defaults** — local model is `qwen3.5:9b` via Ollama; prefer this in examples and defaults

## Configuration
- `config/runtime.json` is the **sole local configuration file** — never create or suggest `.env` / `.env.local` for the main application
- `config/runtime.json` is gitignored; `config/runtime.json.sample` is the reference template
- Scripts under `scripts/` may use `python-dotenv` standalone, but this does not affect the main app
- **Always prefer the LAN inference server (`http://192.168.0.123:11434`) over local Ollama** — set `OLLAMA_BASE_URL` and `OLLAMA_VISION_BASE_URL` to the LAN address in `config/runtime.json`; never use `ollama serve` locally
- **Benchmark server runs on port 8001** — the separate benchmark/integration system runs on port 8001, not 8000; start with `uvicorn main:app --port 8001 --reload`

## Codex Execution Rules

- **Full permissions** — Codex has full permission to run commands needed to complete tasks.
- **Complex task decomposition** — for complex tasks, break work into smaller subtasks and spawn sub-agents when beneficial.
- **Development default** — prefer code changes plus doc updates without adding tests. For verification, favor integration / E2E / chatlog replay over new unit-test coverage during this phase.

## Branch & PR Workflow

Direct pushes to `main` are allowed.

### Steps for every change

1. **Testing** — integration tests are required for safety-critical modules (diagnosis pipeline). For other modules, do not add unit tests unless explicitly requested
2. **Integration tests** — `pytest tests/integration/` — run when the LLM pipeline, prompts, or end-to-end workflow behavior changed
3. **Corpus/E2E replay** — `bash scripts/test.sh chatlog-full` or `./dev.sh e2e <half|full>` — use for human-language regression checks on meaningful workflow changes
4. **Document changes in commit message** — include what changed and any migration/manual cleanup impact
5. **Update `ARCHITECTURE.md`** — only if schema, env vars, API endpoints, or service structure changed
6. **Update progress** — tick completed items in `debug/iteration_*.md`
7. **DO NOT RUN TESTS** - do not run tests (dont run the tests to validate)

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
