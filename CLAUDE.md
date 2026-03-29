# Claude Code Rules — Doctor AI Agent

## Source of Truth

- `AGENTS.md` is the authoritative repo instruction file for workflow, testing
  policy, planning, and push behavior.
- Claude should read and follow `AGENTS.md` first when both files are present.
- If `CLAUDE.md` and `AGENTS.md` ever differ, `AGENTS.md` wins.

## Purpose

- This file contains only Claude Code-specific runtime rules (session management,
  subagent dispatch). All repo-level policy lives in `AGENTS.md`.

## Execution Speed (CRITICAL)

- **Batch independent tool calls in the same turn.** If you need to read 3
  files, read all 3 in one turn — not 3 separate turns. If you need to edit 2
  unrelated files, edit both in one turn. Every single-tool turn is a wasted
  round-trip. Currently 99.99% of turns use only 1 tool. This must improve.
- **Do not narrate what you are about to do.** Just do it. No "Let me read the
  file", no "I'll now edit this", no "Let me check if that worked". Act first,
  explain only if the result is surprising or the user needs context.
- **Do not verify every edit individually.** Make all related edits, then verify
  once at the end with `git diff --stat` or a single test run. Do not read a
  file back after editing it just to confirm the edit applied.
- **Batch read → edit sequences.** When modifying multiple files for one change:
  read all needed files in one turn, then edit all files in the next turn.
  Not: read A → edit A → read B → edit B → read C → edit C.

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
  in `AGENTS.md`.
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
