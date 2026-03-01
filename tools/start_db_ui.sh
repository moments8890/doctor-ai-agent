#!/bin/bash
# Start datasette DB inspector on port 8001
# Usage: bash tools/start_db_ui.sh [port]

PORT=${1:-8001}
DB="$(dirname "$0")/../patients.db"

if [ ! -f "$DB" ]; then
  echo "patients.db not found — start the app first to create tables."
  exit 1
fi

echo "Opening DB UI at http://localhost:$PORT"
"$(dirname "$0")/../.venv/bin/datasette" "$DB" \
  --port "$PORT" \
  --host 0.0.0.0 \
  --setting sql_time_limit_ms 3000 \
  --setting max_returned_rows 500
