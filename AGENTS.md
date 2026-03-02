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
- **DB schema changes** — add to `db/models.py`; `create_tables()` handles creation automatically; note in CHANGELOG if existing data may need manual cleanup
- **LLM provider defaults** — local model is `qwen2.5:7b` via Ollama; prefer this in examples and defaults

## Branch & PR Workflow

**Never push directly to `main`.** Every change — including small fixes — must go through a PR.

### Steps for every change

1. **Unit tests** — `.venv/bin/python -m pytest tests/ -v` — must be 100% green before pushing
2. **Integration tests** — `pytest tests/integration/` — only when LLM pipeline or prompt changed (requires `uvicorn main:app --reload` + `ollama serve`); auto-skipped if deps not running
3. **Corpus tests** (optional) — `python tools/train.py --clean [--cases ...]` — full corpus validation, also requires Ollama
4. **Update `CHANGELOG.md`** — add entry for what changed
5. **Update `ARCHITECTURE.md`** — only if schema, env vars, API endpoints, or service structure changed
6. **Update progress** — tick completed items in `debug/iteration_*.md`

### Publishing

After the above, always:

```bash
# 1. Create a branch (never commit on main)
git checkout -b <type>/<short-slug>   # e.g. feat/my-feature, fix/bug-name, ci/workflow

# 2. Commit, then push
git push -u origin HEAD

# 3. Open a draft PR immediately after pushing
gh pr create --draft --title "<title>" --body "<body>"

# 4. Share the PR URL immediately after creation
gh pr view --json url -q .url

# 5. Enable auto-merge so it lands as soon as CI is green
gh pr merge --auto --squash
```

- Branch naming: `feat/`, `fix/`, `ci/`, `refactor/`, `docs/`
- PR title follows conventional commits: `feat:`, `fix:`, `ci:`, etc.
- PRs must be blocked from merge until required CI checks pass (`unit` + `integration`)
- Auto-merge is squash-merge and only activates after required CI checks are green
- When a PR is created, always provide the PR link in the status update to the user
- Delete the branch after merge (`gh pr merge` does this automatically with `--delete-branch`)
