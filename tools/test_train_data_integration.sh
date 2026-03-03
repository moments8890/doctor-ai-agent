#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load repo .env so OLLAMA_BASE_URL and related vars are available by default.
# Keep explicit shell env vars higher priority than .env values.
if [[ -f ".env" ]]; then
  while IFS='=' read -r key value; do
    [[ -z "${key}" || "${key}" =~ ^[[:space:]]*# ]] && continue
    key="$(echo "$key" | xargs)"
    [[ -z "${!key:-}" ]] || continue
    value="${value#\"}"
    value="${value%\"}"
    export "${key}=${value}"
  done < ".env"
fi

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

SERVER_URL="${INTEGRATION_SERVER_URL:-http://127.0.0.1:8000}"
SUITE="all"
AUTO_FOLLOWUP="${AUTO_FOLLOWUP_TASKS_ENABLED:-false}"
TIMEOUT_SECONDS="${CHAT_TIMEOUT:-300}"

GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
BLUE='\033[34m'
BOLD='\033[1m'
RESET='\033[0m'

usage() {
  cat <<USAGE
Run train-data integration template tests with clear output.

Usage:
  bash tools/test_train_data_integration.sh [--suite all|deepseek|gemini] [--server URL] [--followup true|false]

Options:
  --suite      Which template suite to run (default: all)
  --server     Integration server base URL (default: INTEGRATION_SERVER_URL or http://127.0.0.1:8000)
  --followup   Enable follow-up task assertions (default: AUTO_FOLLOWUP_TASKS_ENABLED or false)
  -h, --help   Show this help

Examples:
  bash tools/test_train_data_integration.sh
  bash tools/test_train_data_integration.sh --suite deepseek
  bash tools/test_train_data_integration.sh --server http://127.0.0.1:18000 --followup true
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite)
      SUITE="${2:-}"
      shift 2
      ;;
    --server)
      SERVER_URL="${2:-}"
      shift 2
      ;;
    --followup)
      AUTO_FOLLOWUP="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo -e "${RED}[error] Unknown argument: $1${RESET}"
      usage
      exit 2
      ;;
  esac
done

if [[ "$SUITE" != "all" && "$SUITE" != "deepseek" && "$SUITE" != "gemini" ]]; then
  echo -e "${RED}[error] --suite must be one of: all, deepseek, gemini${RESET}"
  exit 2
fi

DEEPSEEK_TEST="tests/integration/test_deepseek_conversations_template.py"
GEMINI_TEST="tests/integration/test_gemini_wechat_template.py"

TEST_TARGETS=()
case "$SUITE" in
  all)
    TEST_TARGETS+=("$DEEPSEEK_TEST" "$GEMINI_TEST")
    ;;
  deepseek)
    TEST_TARGETS+=("$DEEPSEEK_TEST")
    ;;
  gemini)
    TEST_TARGETS+=("$GEMINI_TEST")
    ;;
esac

mkdir -p reports/junit
JUNIT_PATH="reports/junit/integration-train-data.xml"

echo -e "${BOLD}${BLUE}== Train Data Integration Test Runner ==${RESET}"
echo "[config] python: $PYTHON"
echo "[config] server: $SERVER_URL"
echo "[config] suite:  $SUITE"
echo "[config] followup assertions: $AUTO_FOLLOWUP"
echo "[config] chat timeout: ${TIMEOUT_SECONDS}s"

echo "[preflight] checking server..."
if ! curl -fsS "$SERVER_URL/" >/dev/null; then
  echo -e "${RED}[fail] server not reachable at $SERVER_URL${RESET}"
  echo "[hint] start app with: uvicorn main:app --reload"
  exit 1
fi
echo -e "${GREEN}[ok] server reachable${RESET}"

OLLAMA_BASE_URL_RESOLVED="${OLLAMA_BASE_URL:-http://localhost:11434/v1}"
OLLAMA_TAGS_URL="${OLLAMA_BASE_URL_RESOLVED%/}"
if [[ "$OLLAMA_TAGS_URL" == */v1 ]]; then
  OLLAMA_TAGS_URL="${OLLAMA_TAGS_URL%/v1}"
fi
OLLAMA_TAGS_URL="$OLLAMA_TAGS_URL/api/tags"

echo "[preflight] checking ollama..."
if ! curl -fsS "$OLLAMA_TAGS_URL" >/dev/null; then
  echo -e "${RED}[fail] ollama not reachable at $OLLAMA_TAGS_URL${RESET}"
  echo "[hint] verify OLLAMA_BASE_URL and run: ollama serve"
  exit 1
fi
echo -e "${GREEN}[ok] ollama reachable${RESET}"

echo "[run] executing pytest..."
set +e
INTEGRATION_SERVER_URL="$SERVER_URL" \
RUN_DEEPSEEK_TEMPLATE=1 \
RUN_GEMINI_TEMPLATE=1 \
AUTO_FOLLOWUP_TASKS_ENABLED="$AUTO_FOLLOWUP" \
CHAT_TIMEOUT="$TIMEOUT_SECONDS" \
"$PYTHON" -m pytest "${TEST_TARGETS[@]}" -v -m integration \
  --junitxml="$JUNIT_PATH" -rA
RC=$?
set -e

echo
if [[ $RC -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}[result] PASS${RESET}"
else
  echo -e "${RED}${BOLD}[result] FAIL (exit code: $RC)${RESET}"
fi

echo "[report] junit: $JUNIT_PATH"

echo "[note] cases can be SKIPPED when follow-up assertions are disabled"
exit $RC
