#!/bin/bash
# Start datasette DB inspector (default port 8002 to avoid conflict with
# the E2E benchmark server on 8001 and the dev server on 8000).
# Usage: bash scripts/start_db_ui.sh [port]

PORT=${1:-8002}
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="${PATIENTS_DB_PATH:-$ROOT/patients.db}"

if [ ! -f "$DB" ]; then
  echo "DB not found at $DB — set PATIENTS_DB_PATH or start the app first to create tables."
  exit 1
fi

echo "Opening DB UI at http://localhost:$PORT"
"$(dirname "$0")/../.venv/bin/datasette" "$DB" \
  --port "$PORT" \
  --host 0.0.0.0 \
  --setting sql_time_limit_ms 3000 \
  --setting max_returned_rows 500
