# Claude Code Rules — Doctor AI Agent

## Code Style

- **Python 3.9 compatibility** — always use `from __future__ import annotations` at the top of new files; use `Optional[X]` not `X | None`, `Tuple[...]` not `tuple[...]`
- **No auto-commit** — never commit unless explicitly asked
- **Preserve medical abbreviations** — do not translate or expand STEMI, BNP, PCI, EGFR, ANC, HER2, EF, NYHA, ICD, etc.
- **Tests mock all I/O** — unit tests in `tests/` must not make real LLM, DB, or network calls; use `AsyncMock` / `patch`
- **DB schema changes** — add to `db/models.py`; `create_tables()` handles creation automatically; document any manual cleanup/migration impact in the commit message and PR description
- **LLM provider defaults** — local model is `qwen2.5:14b` via Ollama; prefer this in examples and defaults

## Configuration
- `config/runtime.json` is the **sole local configuration file** — never create or suggest `.env` / `.env.local` for the main application
- `config/runtime.json` is gitignored; `config/runtime.json.sample` is the reference template
- Scripts under `scripts/` may use `python-dotenv` standalone, but this does not affect the main app
- **Always prefer the LAN inference server (`http://192.168.0.123:11434`) over local Ollama** — set `OLLAMA_BASE_URL` and `OLLAMA_VISION_BASE_URL` to the LAN address in `config/runtime.json`; never use `ollama serve` locally
- **Benchmark server runs on port 8001** — the separate benchmark/integration system runs on port 8001, not 8000; start with `uvicorn main:app --port 8001 --reload`

## Codex Execution Rules

- **Full permissions** — Codex has full permission to run commands needed to complete tasks.
- **Complex task decomposition** — for complex tasks, break work into smaller subtasks and spawn sub-agents when beneficial.
- **Development default** — during normal implementation and iteration, skip running tests and skip adding/updating tests by default. Only add or run tests when:
  - the user explicitly asks for tests
  - you are fixing a failing test or test-only issue
  - you are preparing to push / publish and need to satisfy the repo gate

## Branch & PR Workflow

Direct pushes to `main` are allowed.

### Steps for every change

1. **Unit tests** — `.venv/bin/python -m pytest tests/ -v` — must be 100% green before pushing
   - **Coverage gates** — overall coverage must be `>80%`, and changed/new lines coverage in PR must be `>80%`
   - **Every new function or branch** (new `def`, `if`, `except`, `elif`) must have at least one test that exercises it directly
   - **Verify diff coverage locally before pushing** — run the full check:
     ```bash
     bash scripts/test.sh unit
     git fetch --no-tags origin main
     .venv/bin/diff-cover reports/coverage/coverage.xml --compare-branch=origin/main --diff-range-notation=.. --fail-under=81
     ```
     If diff-cover reports missing lines, add tests for those lines before pushing.
2. **Integration tests** — `pytest e2e/integration/` — only when LLM pipeline or prompt changed (requires `uvicorn main:app --reload` + `ollama serve`); auto-skipped if deps not running
3. **Corpus/E2E replay** (optional) — `bash scripts/test.sh chatlog-full` — full human-language chatlog replay against API + DB checks
4. **Document changes in commit message** — include what changed and any migration/manual cleanup impact
5. **Update `ARCHITECTURE.md`** — only if schema, env vars, API endpoints, or service structure changed
6. **Update progress** — tick completed items in `debug/iteration_*.md`

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


以后你说"self train"，我会按"全量 E2E + 修复直到通过"的流程执行。现在我先直接跑全量 E2E（chatlog full + integration full）并按失败项逐个修复。
