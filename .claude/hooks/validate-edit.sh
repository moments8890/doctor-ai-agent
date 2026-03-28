#!/bin/bash
# PostToolUse validator for Edit/Write.
# Runs cheap checks after file edits. Cannot block — only provides feedback.
# Output on stdout is fed back to Claude as context.

INPUT=$(cat)
FILE=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  exit 0
fi

# 1. Python files: syntax check
case "$FILE" in
  *.py)
    ERR=$(python3 -m py_compile "$FILE" 2>&1)
    if [ $? -ne 0 ]; then
      echo "WARNING: Python syntax error in $FILE"
      echo "$ERR"
    fi
    ;;
esac

# 2. Prompt files: remind about confirmation policy
case "$FILE" in
  */agent/prompts/*.md)
    echo "REMINDER: Prompt file edited ($FILE). Per feedback policy: show diff to user and get approval before finalizing."
    ;;
esac

exit 0
