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
