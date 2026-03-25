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

## Code Style

- In mermaid diagrams, use `<br/>` for line breaks in node labels, never `\n`.

## Learnings

1. I need to refactor [FEATURE] across the codebase. Before writing any code, create a plan that divides work into independent streams by directory/concern. Then spawn sub-agents for each stream with these rules: 1) Each agent works ONLY on files in its assigned directories, 2) Each agent creates a descriptive commit for each logical change, 3) No agent modifies files outside its scope, 4) After all agents complete, review all changes together for cross-cutting issues like import mismatches or interface contract breaks. Present the full plan and stream assignments for my approval before spawning any agents.
2. Run a pre-deployment QA audit for the doctor-ai-agent app. Steps: 1) Check all Alembic migration heads match the SQLAlchemy models—flag any column in models not in migrations or vice versa. 2) Start the FastAPI server locally and hit every endpoint defined in the router files with valid test payloads, checking for 500s or unhandled exceptions. 3) Run the patient simulation pipeline against the local server with 5 sample cases and validate responses with the LLM judge. 4) Check for any imports referencing deleted modules (`grep -r` for known removed modules). 5) Verify all environment variables referenced in code exist in .env.example. Produce a markdown report with PASS/FAIL for each check and block-quoted error details for any failures.
