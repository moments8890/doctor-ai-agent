#!/bin/zsh
# Run Claude Code in a persistent tmux session.
# Usage: ./scripts/claude-tmux.sh [attach]
SESSION="claude-code"
DIR="/Volumes/ORICO/Code/doctor-ai-agent"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already exists. Attaching..."
  tmux attach -t "$SESSION"
else
  echo "Starting new '$SESSION' session..."
  tmux new-session -s "$SESSION" -c "$DIR" \; \
    send-keys "cd $DIR && claude" Enter
  tmux attach -t "$SESSION"
fi
