#!/bin/bash
# PreToolUse guard for Bash commands.
# Blocks known footguns defined in AGENTS.md.
# Exit 0 = allow, exit 2 = block (reason on stderr).

INPUT=$(cat)
CMD=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)

# Skip checks for git commit/log/diff — message text is not a command
if echo "$CMD" | grep -qE '^git (commit|log|diff|show|tag|blame)'; then
  exit 0
fi

# 1. Block alembic (AGENTS.md: "No Alembic migrations")
if echo "$CMD" | grep -qiE '\balembic\b'; then
  echo "BLOCKED: alembic is not allowed (AGENTS.md: No Alembic migrations until production launch)" >&2
  exit 2
fi

# 2. Block sed -i / perl -pi (AGENTS.md: "prefer the Edit tool, sed has corrupted files")
if echo "$CMD" | grep -qE 'sed\s+-i|perl\s+-pi'; then
  echo "BLOCKED: sed -i / perl -pi not allowed — use the Edit tool instead (AGENTS.md: Workflow #5)" >&2
  exit 2
fi

# 3. Block creating .env files for main app (AGENTS.md: "never create .env / .env.local")
if echo "$CMD" | grep -qE '(cat|echo|tee|touch|cp|mv)\s.*\.env(\s|$|\.local|\.dev|\.prod)'; then
  echo "BLOCKED: Do not create .env files — use config/runtime.json instead (AGENTS.md: Configuration)" >&2
  exit 2
fi

# 4. Block tests/sims targeting port 8000 (AGENTS.md: "Test server runs on port 8001")
if echo "$CMD" | grep -qE '(pytest|test\.sh|run_patient_sim|run_doctor_sim)' && echo "$CMD" | grep -qE '(localhost:8000|127\.0\.0\.1:8000|:8000)'; then
  echo "BLOCKED: Tests must target port 8001, not 8000 (AGENTS.md: Configuration)" >&2
  exit 2
fi

exit 0
