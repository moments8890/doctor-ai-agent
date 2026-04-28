#!/usr/bin/env bash
# validate-v2-e2e.sh — run the full Playwright e2e suite against a clean
# test backend on :8001. Per AGENTS.md, e2e MUST target :8001 (test server),
# never :8000 (dev server with real data).
#
# Usage:
#   1. Start a clean test backend on :8001 in another terminal:
#        PYTHONPATH=src ENVIRONMENT=development \
#          PATIENTS_DB_PATH=/tmp/e2e_test.db \
#          uvicorn main:app --port 8001
#      (or reuse an existing :8001 if you have one configured)
#   2. Make sure the frontend dev server is running on :5173.
#   3. Run this script:
#        bash scripts/validate-v2-e2e.sh
#
# Output: pass/fail summary + generated videos in frontend/web/test-results/

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend/web"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }

# ── Preflight ────────────────────────────────────────────────────────
echo "── Preflight ──"

# Backend on 8001
if ! curl -sS --max-time 2 http://127.0.0.1:8001/healthz >/dev/null 2>&1; then
  fail "Test backend on :8001 is not reachable.

Start it in another terminal with an isolated DB:
  PYTHONPATH=src ENVIRONMENT=development \\
    PATIENTS_DB_PATH=/tmp/e2e_test.db \\
    uvicorn main:app --port 8001"
fi
pass "Test backend :8001 healthy"

# Seed shared test doctor (test/123456) used by every spec via doctor-auth
# fixture. Idempotent — safe to run on every invocation. Without this,
# specs that pull the `doctor` / `doctorPage` fixture cannot log in.
TEST_DB="${PATIENTS_DB_PATH:-/tmp/e2e_test.db}"
if PYTHONPATH=src ENVIRONMENT=development PATIENTS_DB_PATH="$TEST_DB" \
     "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/ensure_welcome_code.py" >/dev/null 2>&1 \
   && PYTHONPATH=src ENVIRONMENT=development PATIENTS_DB_PATH="$TEST_DB" \
     "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/ensure_test_doctor.py" >/dev/null 2>&1 \
   && PYTHONPATH=src ENVIRONMENT=development PATIENTS_DB_PATH="$TEST_DB" \
     "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/ensure_test_patient.py" >/dev/null 2>&1; then
  pass "Test seed (WELCOME invite + test doctor + test patient) ready in $TEST_DB"
else
  fail "Failed to seed test DB at $TEST_DB. Run manually:
  PYTHONPATH=src ENVIRONMENT=development PATIENTS_DB_PATH=$TEST_DB \\
    .venv/bin/python scripts/ensure_welcome_code.py
  PYTHONPATH=src ENVIRONMENT=development PATIENTS_DB_PATH=$TEST_DB \\
    .venv/bin/python scripts/ensure_test_doctor.py
  PYTHONPATH=src ENVIRONMENT=development PATIENTS_DB_PATH=$TEST_DB \\
    .venv/bin/python scripts/ensure_test_patient.py"
fi

# E2E frontend dev server lives on :5174 with VITE_API_TARGET=http://127.0.0.1:8001.
# Its only job is to proxy /api → :8001 so UI form-login and API-direct seeding
# hit the SAME backend / DB. The default :5173 proxies to the dev backend on
# :8000, which causes asymmetric login (API helpers get the test patient,
# form-login gets the user's dev-DB patient) and is not safe for E2E.
if ! curl -sS --max-time 2 http://127.0.0.1:5174 >/dev/null 2>&1; then
  fail "E2E frontend on :5174 is not reachable. Start it with:
  cd frontend/web && VITE_API_TARGET=http://127.0.0.1:8001 \\
    npx vite --port 5174 --host 127.0.0.1"
fi
pass "E2E frontend :5174 reachable (proxies → :8001)"

# Guard against accidental :8000 use
if [[ "${E2E_API_BASE_URL:-}" == *":8000"* ]]; then
  fail "E2E_API_BASE_URL points at :8000. Tests must target :8001."
fi
if [[ "${E2E_BASE_URL:-}" == *":5173"* ]]; then
  fail "E2E_BASE_URL points at :5173 (dev frontend → :8000 backend).
Tests must target :5174 (proxies to :8001)."
fi

# ── Run ──────────────────────────────────────────────────────────────
echo ""
echo "── Running Playwright e2e suite against :8001 ──"
echo ""

rm -rf test-results
export E2E_API_BASE_URL="http://127.0.0.1:8001"
export E2E_BASE_URL="http://127.0.0.1:5174"

if npx playwright test; then
  echo ""
  pass "E2e suite green against :8001"
  exit 0
else
  echo ""
  warn "E2e suite had failures. Videos + traces in frontend/web/test-results/"
  exit 1
fi
