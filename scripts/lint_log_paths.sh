#!/usr/bin/env bash
# Lint: ensure no Python file under src/ uses relative "logs/" paths.
# All log paths must resolve to the project root logs/ directory via
# Path(__file__).resolve().parents[N] or os.environ.get("LOG_DIR").
#
# Run: bash scripts/lint_log_paths.sh
# Exit: 0 = clean, 1 = violations found

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/src"

# Patterns that indicate a relative "logs/" path (not anchored to project root).
# We look for string literals like "logs/..." or 'logs/...' that are NOT part of
# a parents[N] / "logs" expression or an os.environ.get() call.
VIOLATIONS=$(grep -rn --include='*.py' \
    -E '("|'"'"')logs/' "$SRC" \
    | grep -v '__pycache__' \
    | grep -v '\.pyc' \
    | grep -v 'parents\[' \
    | grep -v '_LOG_ROOT' \
    | grep -v '# noqa: log-path' \
    || true)

if [ -n "$VIOLATIONS" ]; then
    echo "ERROR: Relative log paths found in src/. All logs must write to {project_root}/logs/."
    echo ""
    echo "Use Path(__file__).resolve().parents[N] / \"logs\" to resolve to project root."
    echo "Or add '# noqa: log-path' to suppress a false positive."
    echo ""
    echo "Violations:"
    echo "$VIOLATIONS"
    exit 1
fi

echo "OK: No relative log paths found."
exit 0
