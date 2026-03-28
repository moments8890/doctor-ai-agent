#!/bin/bash
# Stop hook: checks if changed files require doc updates that weren't made.
# Uses the file→doc matrix from AGENTS.md §8 "Keep docs current".
# Exit 0 = allow stop. JSON {"decision":"block","reason":"..."} = block.

INPUT=$(cat)

# Prevent infinite loop: if already blocking, let it stop
ACTIVE=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stop_hook_active', False))" 2>/dev/null)
if [ "$ACTIVE" = "True" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

# Get changed files (staged + unstaged)
CHANGED=$(git diff --name-only HEAD 2>/dev/null; git diff --name-only 2>/dev/null; git diff --cached --name-only 2>/dev/null)
if [ -z "$CHANGED" ]; then
  exit 0
fi

WARNINGS=""

# File → doc matrix from AGENTS.md §8
# Only check the most critical mappings to avoid false positives

# db/models changed → architecture.md should be updated
if echo "$CHANGED" | grep -q "src/db/models/"; then
  if ! echo "$CHANGED" | grep -q "docs/architecture.md"; then
    WARNINGS="${WARNINGS}\n- DB models changed but docs/architecture.md not updated (schema section)"
  fi
fi

# agent/prompts changed → prompts/README.md should be updated
if echo "$CHANGED" | grep -qE "src/agent/prompts/intent/|src/agent/prompts/common/|src/agent/prompts/domain/"; then
  if ! echo "$CHANGED" | grep -q "src/agent/prompts/README.md"; then
    WARNINGS="${WARNINGS}\n- Prompt files changed but src/agent/prompts/README.md not updated"
  fi
fi

# API routes changed → architecture.md should be updated
if echo "$CHANGED" | grep -qE "src/channels/web/.*\.py$|src/channels/wechat/.*\.py$"; then
  if echo "$CHANGED" | grep -qE "(router|endpoint|@router)"; then
    if ! echo "$CHANGED" | grep -q "docs/architecture.md"; then
      WARNINGS="${WARNINGS}\n- API routes may have changed but docs/architecture.md not updated"
    fi
  fi
fi

# New spec/plan files → check for Cascading Impact and workflow diagram
if echo "$CHANGED" | grep -qE "docs/specs/.*\.md$|docs/plans/.*\.md$"; then
  for SPECFILE in $(echo "$CHANGED" | grep -E "docs/(specs|plans)/.*\.md$"); do
    if [ -f "$SPECFILE" ]; then
      if ! grep -q "Cascading Impact" "$SPECFILE" 2>/dev/null; then
        WARNINGS="${WARNINGS}\n- $SPECFILE missing Cascading Impact Analysis section (AGENTS.md requirement)"
      fi
      if ! grep -q "mermaid" "$SPECFILE" 2>/dev/null; then
        WARNINGS="${WARNINGS}\n- $SPECFILE missing workflow diagram (AGENTS.md: Design Artifacts)"
      fi
    fi
  done
fi

if [ -n "$WARNINGS" ]; then
  REASON=$(echo -e "Doc sync check found issues:$WARNINGS\n\nUpdate the docs or confirm these are intentional omissions.")
  echo "{\"decision\":\"block\",\"reason\":$(python3 -c "import json; print(json.dumps('$REASON'))" 2>/dev/null || echo "\"Doc updates may be needed\"")}"
  exit 0
fi

exit 0
