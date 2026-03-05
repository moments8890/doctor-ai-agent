# OpenClaw Management Agent Rules

## Purpose
Define the mandatory prep and control rules for OpenClaw-managed development (Codex/Claude orchestration).

## 5. Workspace Hygiene (Mandatory)

```bash
cd /Users/jingwuxu/Documents/code/doctor-ai-agent
git fetch origin
git checkout main
git pull --ff-only
```

Rule:
- Always start tasks from clean latest `main`.

## 6. GitHub Auth (Mandatory for PR Automation)

```bash
gh auth status
```

Rule:
- Must be logged in, with repo push permissions available.

## 7. Policy Prompt (Critical)

Create and reuse one controller prompt template that always includes:
- Branch naming rule
- Test command: `.venv/bin/python -m pytest tests/ -v`
- Coverage gate
- PR mode rule
- Auto-merge preference

### Reusable Controller Prompt (Template)

```text
You are the development orchestrator.

Repo:
/Users/jingwuxu/Documents/code/doctor-ai-agent

Execution policy:
1) Create feature branch using prefix: feat/, fix/, docs/, refactor/, ci/
2) Implement requested task with focused, minimal diffs
3) Run tests:
   .venv/bin/python -m pytest tests/ -v
4) Enforce coverage gate:
   - overall coverage >= 80%
   - changed lines coverage >= 80%
5) Open PR in ready-for-review mode (not draft) unless explicitly requested otherwise
6) Enable auto-merge with squash after checks pass
7) Report back:
   - branch name
   - test result
   - PR URL
   - merge status

Do not skip failing checks. If blocked, provide exact blocker and next command.
```

## 8. Optional but Useful Runtime Tools

```bash
openclaw dashboard
openclaw logs --follow
```

Use:
- `dashboard` for orchestration visibility
- `logs --follow` for live debugging and run monitoring
