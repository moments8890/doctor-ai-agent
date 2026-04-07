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

- **Do NOT suggest `/compact`, `/clear`, or session reset unless context usage
  exceeds 50%.** Below 50%, never mention session management unprompted.
- Above 50%: suggest `/compact` when the task changes phase or old context is no
  longer needed. Suggest `/clear` or new terminal for unrelated work.
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
- **Each agent prompt must include:** concrete goal, owned files, explicit
  non-goals, expected output format, AND a reminder to use bulk CLI tools
  (ast-grep, sd, fd) instead of Edit loops for repetitive changes. Agents do
  not read CLAUDE.md — the dispatcher must embed the rules.
- **One exploration owner** per subproblem — never let multiple agents duplicate
  repo discovery.
- **Stop conditions:** terminate agents that are retrying, reopening the same
  files, or bouncing between search/edit/verify without convergence.
- **No recursive delegation** — agents must not spawn more agents.
- **Close agents promptly** after completion. No idle agents kept alive.

## UI Design System (MUST follow for all frontend changes)

These rules are enforced by `scripts/lint-ui.sh`. Run it before pushing.

### Tokens — never hardcode

| What | Use | Never |
|------|-----|-------|
| Colors | `COLOR.*` from theme.js | Hardcoded hex (`#07C160`, `#999`, etc.) |
| Font sizes | `TYPE.*` from theme.js | Hardcoded px (`fontSize: 14`) |
| Border radius | `RADIUS.*` from theme.js | Hardcoded px (`borderRadius: "8px"`) |
| Icon sizes | `ICON.*` from theme.js | Hardcoded numbers for icon fontSize |
| Highlight rows | `HIGHLIGHT_ROW_SX` from theme.js | `bgcolor: "#fffef5"` inline |

### Components — use shared, never inline

| Need | Use | Never |
|------|-----|-------|
| List rows | `ListCard` | Inline flex row with avatar+title+subtitle |
| Stat display | `StatColumn` | Inline stat with value+label |
| Filter tabs | `FilterBar` (with `dividers`, `activeColor`) | Inline tab bar JSX |
| Chat avatar | `MsgAvatar` | Inline Box with hospital/robot icon |
| Expand/collapse | MUI `Collapse` transition | `{open && children}` (instant show/hide) |
| Loading states | `SectionLoading` (skeleton by default) | Raw `CircularProgress` for content |
| Empty lists | `EmptyState` | Plain text ("暂无…") |
| Bottom sheets | `SheetDialog` (SwipeableDrawer inside) | Raw `Dialog` positioned at bottom |
| Confirm dialogs | `ConfirmDialog` | Custom dialog JSX |
| Citation preview | `CitationPopover` | Navigate away to knowledge page |
| Timestamps | `nowTs()` from utils/time.js | Inline `new Date()` formatting |

### Icons — MUI only, never emojis

- Use MUI `@mui/icons-material` for all icons in UI components
- **Never use emojis** (📄🌐✏) as icons in the app — they render inconsistently across devices
- Emojis are OK in mock HTML docs but never in shipped JSX

### Layout conventions

- **Tab switch:** `Fade` (150ms) — see `DoctorPage SectionContent`
- **Subpage push/pop:** `Slide` (300ms, direction="left") via `PageSkeleton mobileView`
- **Dialog buttons:** cancel LEFT (gray), primary RIGHT (green). Always.
- **Danger dialogs:** same layout, primary button red. No button-swap.
- **Mobile subpages:** must use `PageSkeleton mobileView` (auto-gets Slide transition)

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
