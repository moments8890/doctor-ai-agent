# /report — Implementation Report

Generate a human-friendly HTML report summarizing what was built. Use after completing
a large implementation task, plan execution, or multi-commit feature.

## Usage

- `/report` — auto-detect changes since last tag or last 24h
- `/report 3` — last 3 commits
- `/report abc123..HEAD` — specific commit range
- `/report --plan docs/plans/2026-03-27-feature.md` — compare against a plan

## Step 1: Determine Scope

Parse user input to determine the commit range.

**Auto-detect** (no args):
```bash
# Try last tag first
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -n "$LAST_TAG" ]; then
  RANGE="$LAST_TAG..HEAD"
else
  # Fall back to 24 hours
  RANGE="$(git log --since='24 hours ago' --format='%H' --reverse | head -1)..HEAD"
fi
echo "RANGE: $RANGE"
```

**Explicit commit count** (`/report N`):
```bash
RANGE="HEAD~N..HEAD"
```

**Explicit range** (`/report abc..HEAD`):
```bash
RANGE="abc..HEAD"
```

## Step 2: Gather Data

Run these in parallel:

### 2A. Commit log
```bash
git log $RANGE --format='%h|%s|%an|%ai' --no-merges
```

### 2B. File changes (diffstat)
```bash
git diff $RANGE --stat
git diff $RANGE --numstat
```

### 2C. Change classification
```bash
# Group changed files by type
git diff $RANGE --name-only | sort
```

Classify each file into:
- `backend` — `src/**/*.py`
- `frontend` — `frontend/**/*.{js,jsx,ts,tsx,css}`
- `test` — `tests/**/*`, `*.test.*`
- `prompt` — `src/agent/prompts/**/*.md`
- `doc` — `docs/**/*`, `*.md` (non-prompt)
- `config` — `*.json`, `*.yaml`, `*.yml`, `.claude/**/*`
- `skill` — `.claude/commands/**/*`

### 2D. Test results (if tests exist for touched modules)
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && \
PYTHONPATH=src ROUTING_LLM=deepseek .venv/bin/python -m pytest tests/core/ -q --tb=no \
  --ignore=tests/core/test_multi_gateway_e2e.py \
  --ignore=tests/core/test_p3_d2_parity_e2e.py 2>&1 | tail -3
```

### 2E. Frontend tests (if frontend changed)
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && npx vitest run --reporter=verbose 2>&1 | tail -5
```

### 2F. If `--plan` provided, read the plan file
Read the plan and extract task checkboxes to show completion status.

## Step 3: Generate HTML Report

Create the report at `docs/qa/YYYY-MM-DD-report/index.html`.

Use this structure — **match the project's existing QA report style**:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Implementation Report — {DATE}</title>
<style>
/* Use the project's standard QA report CSS:
   - System fonts: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
   - Max-width: 900px centered
   - Cards: white bg, 1px #eee border, 8px radius, 0 1px 3px shadow
   - Status badges: green (#07C160), red (#D65745), amber (#F59E0B), blue (#1B6EF3)
   - Collapsible sections with .open toggle
   - Subtle hover states (#fafafa)
*/
</style>
</head>
<body>
```

### Header
```
{Project Name} — Implementation Report
{Date} · {Branch} · {Commit Range} · {N commits}
```

### Summary Stats (4-column grid)
Show these as large stat cards:

| Stat | Value | Color |
|------|-------|-------|
| Files Changed | N | blue |
| Lines Added | +N | green |
| Lines Removed | -N | red |
| Tests Passing | N/N | green if all pass, red if failures |

### What Was Built (collapsible section, open by default)
For each commit, show a card with:
- Commit hash (monospace, clickable)
- Commit message (bold)
- Author + timestamp
- Files changed count
- Expand to see the file list

Group commits by type prefix (`feat:`, `fix:`, `refactor:`, `docs:`, etc.).

### Files Changed (collapsible, grouped by classification)
Show file tree grouped by the categories from Step 2C:

```
Backend (12 files, +340 -89)
├── src/domain/knowledge/knowledge_crud.py  (+45 -12)
├── src/domain/records/structuring.py       (+23 -8)
└── ...

Frontend (3 files, +120 -15)
├── frontend/web/src/store/doctorStore.test.js  (+35, new)
└── ...

Tests (4 files, +890, all new)
├── tests/core/test_knowledge_pure.py  (+380, new)
└── ...
```

Use green for additions, red for deletions, blue badge for "new" files.

### Test Results (collapsible)
Show test output with pass/fail badges:
- Backend: `N passed, N failed in X.XXs`
- Frontend: `N passed in X.XXs`
- Each failure as a red card with the error

### Plan Completion (only if --plan provided)
Show the plan's task checklist with completion status:
- [x] Task 1: Description — DONE
- [x] Task 2: Description — DONE
- [ ] Task 3: Description — PENDING

### Impact Summary (collapsible)
Auto-generated based on what changed:
- **DB schema**: if `db/models/` changed — list affected tables
- **API endpoints**: if `channels/web/` changed — list affected routes
- **Prompts**: if `prompts/` changed — list affected prompts
- **Config**: if config files changed — list what
- **Dependencies**: if `requirements.txt` or `package.json` changed

Each with a colored badge (green=addition, amber=modification, red=deletion).

### Footer
```
Generated {timestamp} by /report skill
Source: git {range} on branch {branch}
```

## Step 4: Add JavaScript

Include collapsible section toggles and an optional "copy summary" button that copies
a markdown version of the stats to clipboard.

```javascript
// Toggle sections
document.querySelectorAll('.section-header').forEach(function(h) {
  h.addEventListener('click', function() {
    this.parentElement.classList.toggle('open');
  });
});
```

## Step 5: Report Results

After generating, tell the user:

```
Report generated: docs/qa/YYYY-MM-DD-report/index.html

Summary:
  {N} commits · {N} files · +{N} -{N} lines
  Tests: {N}/{N} passing

Open in browser to view.
```

## Rules

- **Match existing QA report style** — same fonts, colors, card patterns as `docs/qa/` reports
- **Self-contained HTML** — no external CSS/JS dependencies
- **Human-readable** — a non-developer should understand what changed at the summary level
- **Collapsible details** — overview visible at a glance, details expandable
- **No auto-commit** — the report file is generated but not committed
- **Chinese-friendly** — handle Chinese filenames and commit messages correctly (UTF-8)
- **Screenshots directory** — create `docs/qa/YYYY-MM-DD-report/` even if no screenshots; the index.html goes there
