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

## Push Workflow

Before every `git push`, always:

1. **Unit tests** — `.venv/bin/python -m pytest tests/ -v` — must be 100% green (no LLM needed)
2. **Integration tests** — `python tools/train.py --clean [--cases ...]` — only when LLM pipeline or prompt changed (requires Ollama running)
3. **Update `CHANGELOG.md`** — add entry for what changed
4. **Update `ARCHITECTURE.md`** — only if schema, env vars, API endpoints, or service structure changed
5. **Update progress** — tick completed items in `debug/iteration_*.md`
