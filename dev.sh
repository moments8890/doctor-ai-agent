#!/usr/bin/env bash
# DEPRECATED — use ./cli.py instead
#
# Subcommands that moved:
#   test, e2e        → scripts/test.sh
#   data, load-data  → scripts/preload_patients.py, scripts/seed_db.py
#   chat             → scripts/chat.py
#   inspect-db       → scripts/db_inspect.py
#   deepseek, groq…  → ./cli.py start --provider <name>
set -euo pipefail

case "${1:-}" in
  test|e2e|data|load-data|chat|inspect-db)
    echo "Subcommand '$1' is no longer in dev.sh." >&2
    echo "See ./cli.py -h or run the script directly from scripts/." >&2
    exit 2
    ;;
esac

echo "DEPRECATED: use ./cli.py instead" >&2
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/.venv/bin/python" "$DIR/cli.py" "$@"
