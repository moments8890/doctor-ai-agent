#!/usr/bin/env bash
# ============================================================
# .dev.sh — Local development startup for 专科医师AI智能体
#
# Usage:
#   ./.dev.sh                  — LAN Ollama (default) + backend + frontend
#   ./.dev.sh local             — local Ollama fallback + backend + frontend
#   ./.dev.sh openrouter        — OpenRouter cloud LLM + backend + frontend
#   ./.dev.sh backend           — backend only (LAN Ollama)
#   ./.dev.sh backend local     — backend only (local Ollama)
#   ./.dev.sh backend openrouter — backend only (OpenRouter)
#   ./.dev.sh frontend          — frontend only
#   ./.dev.sh stop              — stop all
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$APP_DIR/frontend/web"
VENV="$APP_DIR/.venv/bin"
PORT="${PORT:-8000}"
FE_PORT=5173

LAN_OLLAMA_URL="http://192.168.0.123:11434"
LAN_OLLAMA_MODEL="qwen3.5:9b"
LOCAL_OLLAMA_URL="http://localhost:11434"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
fail() { echo -e "${RED}✗ $*${NC}"; exit 1; }

# ── Check LAN Ollama ─────────────────────────────────────────
check_lan_ollama() {
    echo "Checking LAN Ollama at $LAN_OLLAMA_URL ..."
    if curl -sf --connect-timeout 3 "$LAN_OLLAMA_URL/api/tags" &>/dev/null; then
        export OLLAMA_BASE_URL="$LAN_OLLAMA_URL/v1"
        export OLLAMA_VISION_BASE_URL="$LAN_OLLAMA_URL/v1"
        export OLLAMA_MODEL="$LAN_OLLAMA_MODEL"
        export OLLAMA_VISION_MODEL="qwen3-vl:8b"
        ok "LAN Ollama reachable ($LAN_OLLAMA_MODEL)"
        return 0
    else
        warn "LAN Ollama not reachable at $LAN_OLLAMA_URL"
        return 1
    fi
}

# ── Check local Ollama ────────────────────────────────────────
check_local_ollama() {
    if ! command -v ollama &>/dev/null; then
        fail "Ollama not found. Install: https://ollama.com/download"
    fi
    if ! curl -sf "$LOCAL_OLLAMA_URL/api/tags" &>/dev/null; then
        warn "Local Ollama not running. Starting..."
        ollama serve &>/dev/null &
        sleep 2
        if ! curl -sf "$LOCAL_OLLAMA_URL/api/tags" &>/dev/null; then
            fail "Could not start local Ollama"
        fi
    fi

    # Pick fastest available model (speed > accuracy for local dev)
    local model
    if ollama list 2>/dev/null | grep -q "qwen3.5:2b"; then
        model="qwen3.5:2b"
    elif ollama list 2>/dev/null | grep -q "qwen3:4b"; then
        model="qwen3:4b"
    else
        warn "No qwen3 model found. Pulling qwen3.5:2b (~2.7GB)..."
        ollama pull qwen3.5:2b
        model="qwen3.5:2b"
    fi

    export OLLAMA_BASE_URL="$LOCAL_OLLAMA_URL/v1"
    export OLLAMA_VISION_BASE_URL="$LOCAL_OLLAMA_URL/v1"
    export OLLAMA_MODEL="$model"
    export OLLAMA_VISION_MODEL="qwen3-vl:2b"
    ok "Local Ollama running ($model)"
}

# ── Setup cloud providers ─────────────────────────────────────
# API keys are loaded from config/runtime.json at app startup.
# .dev.sh only sets the provider routing env vars.
# To add keys: edit config/runtime.json (gitignored).

setup_openrouter() {
    export OPENROUTER_MODEL="${OPENROUTER_MODEL:-qwen/qwen3.5-9b}"
    ok "OpenRouter configured (model=$OPENROUTER_MODEL)"
}

setup_sambanova() {
    export SAMBANOVA_MODEL="${SAMBANOVA_MODEL:-Meta-Llama-3.3-70B-Instruct}"
    ok "SambaNova configured (model=$SAMBANOVA_MODEL)"
}

setup_groq() {
    export GROQ_MODEL="${GROQ_MODEL:-qwen/qwen3-32b}"
    ok "Groq configured (model=$GROQ_MODEL)"
}

setup_deepseek() {
    ok "DeepSeek configured (deepseek-chat)"
}

# ── Setup LLM provider ───────────────────────────────────────
setup_llm() {
    local mode="${1:-lan}"

    if [ "$mode" = "sambanova" ]; then
        setup_sambanova
    elif [ "$mode" = "groq" ]; then
        setup_groq
    elif [ "$mode" = "deepseek" ]; then
        setup_deepseek
    elif [ "$mode" = "openrouter" ]; then
        setup_openrouter
    elif [ "$mode" = "local" ]; then
        check_local_ollama
    else
        # Default: try LAN first, warn if unavailable
        if ! check_lan_ollama; then
            warn "Run './.dev.sh local' or './.dev.sh openrouter' instead"
            fail "LAN Ollama required for default mode"
        fi
    fi
}

# ── Environment ───────────────────────────────────────────────
setup_env() {
    local mode="${1:-ollama}"
    export ENVIRONMENT=development
    export PYTHONPATH="$APP_DIR/src"

    if [ "$mode" = "sambanova" ]; then
        export ROUTING_LLM=sambanova
        export STRUCTURING_LLM=sambanova
        export CONVERSATION_LLM=sambanova
        export VISION_LLM=ollama
    elif [ "$mode" = "groq" ]; then
        export ROUTING_LLM=groq
        export STRUCTURING_LLM=groq
        export CONVERSATION_LLM=groq
        export VISION_LLM=ollama
    elif [ "$mode" = "deepseek" ]; then
        export ROUTING_LLM=deepseek
        export STRUCTURING_LLM=deepseek
        export CONVERSATION_LLM=deepseek
        export VISION_LLM=ollama
    elif [ "$mode" = "openrouter" ]; then
        export ROUTING_LLM=openrouter
        export STRUCTURING_LLM=openrouter
        export CONVERSATION_LLM=openrouter
        export VISION_LLM=ollama
    else
        export OLLAMA_API_KEY="ollama"
        export ROUTING_LLM=ollama
        export STRUCTURING_LLM=ollama
        export CONVERSATION_LLM=ollama
        export VISION_LLM=ollama
    fi

    # LangFuse keys loaded from config/runtime.json (already gitignored)

    if [ "$mode" = "ollama" ] || [ "$mode" = "lan" ] || [ "$mode" = "local" ]; then
        ok "LLM: ${OLLAMA_BASE_URL:-} (model=${OLLAMA_MODEL:-})"
    else
        ok "LLM: $ROUTING_LLM"
    fi
}

# ── Backend ───────────────────────────────────────────────────
start_backend() {
    echo ""
    echo "Starting backend on :$PORT ..."
    cd "$APP_DIR"
    "$VENV/python" -m uvicorn main:app \
        --host 127.0.0.1 \
        --port "$PORT" \
        --reload \
        --reload-dir src \
        --app-dir src &
    BACKEND_PID=$!
    sleep 2
    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        ok "Backend running at http://localhost:$PORT (PID $BACKEND_PID)"
    else
        fail "Backend failed to start"
    fi
}

# ── Frontend ──────────────────────────────────────────────────
start_frontend() {
    echo ""
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo "Installing frontend dependencies..."
        (cd "$FRONTEND_DIR" && npm install)
    fi
    echo "Starting frontend on :$FE_PORT ..."
    (cd "$FRONTEND_DIR" && npx vite --host 127.0.0.1 --port "$FE_PORT") &
    FE_PID=$!
    sleep 2
    if kill -0 "$FE_PID" 2>/dev/null; then
        ok "Frontend running at http://localhost:$FE_PORT (PID $FE_PID)"
    else
        fail "Frontend failed to start"
    fi
}

# ── Stop ──────────────────────────────────────────────────────
stop_all() {
    echo "Stopping dev processes..."
    pkill -f "uvicorn main:app" 2>/dev/null && ok "Backend stopped" || true
    pkill -f "vite.*5173" 2>/dev/null && ok "Frontend stopped" || true
}

# ── Print banner ──────────────────────────────────────────────
print_banner() {
    local llm_label
    if [ "${ROUTING_LLM:-}" = "sambanova" ]; then
        llm_label="SambaNova (${SAMBANOVA_MODEL:-Meta-Llama-3.3-70B-Instruct})"
    elif [ "${ROUTING_LLM:-}" = "groq" ]; then
        llm_label="Groq (${GROQ_MODEL:-llama-3.3-70b-versatile})"
    elif [ "${ROUTING_LLM:-}" = "deepseek" ]; then
        llm_label="DeepSeek (deepseek-chat)"
    elif [ "${ROUTING_LLM:-}" = "openrouter" ]; then
        llm_label="OpenRouter (${OPENROUTER_MODEL:-})"
    elif [[ "${OLLAMA_BASE_URL:-}" == *"localhost"* ]]; then
        llm_label="local Ollama (${OLLAMA_MODEL:-})"
    else
        llm_label="LAN Ollama (${OLLAMA_MODEL:-})"
    fi
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}Dev environment ready!${NC}"
    echo ""
    echo "  Frontend : http://localhost:$FE_PORT"
    echo "  Backend  : http://localhost:$PORT"
    echo "  Admin UI : http://localhost:$PORT/admin"
    echo "  LLM      : $llm_label"
    echo ""
    echo "Press Ctrl+C to stop all"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ── Main ──────────────────────────────────────────────────────
CMD="${1:-}"
ARG2="${2:-}"

# Detect flags in any position
LLM_MODE="lan"
DEBUG_MODE=false
for arg in "$@"; do
    [ "$arg" = "local" ] && LLM_MODE="local"
    [ "$arg" = "openrouter" ] && LLM_MODE="openrouter"
    [ "$arg" = "debug" ] && DEBUG_MODE=true
done

if $DEBUG_MODE; then
    export LOG_LEVEL=DEBUG
    warn "Debug mode: LangChain will print full LLM prompts/responses"
fi

case "$CMD" in
    stop)
        stop_all
        exit 0
        ;;
    frontend)
        start_frontend
        echo -e "\n${GREEN}Frontend ready: http://localhost:$FE_PORT${NC}"
        echo "Press Ctrl+C to stop"
        wait
        ;;
    backend)
        setup_llm "$LLM_MODE"
        setup_env "$LLM_MODE"
        start_backend
        echo -e "\n${GREEN}Backend ready: http://localhost:$PORT${NC}"
        echo "Press Ctrl+C to stop"
        wait
        ;;
    local|openrouter|groq|sambanova|deepseek)
        setup_llm "$CMD"
        setup_env "$CMD"
        start_backend
        start_frontend
        print_banner
        wait
        ;;
    all|"")
        setup_llm "lan"
        setup_env "ollama"
        start_backend
        start_frontend
        print_banner
        wait
        ;;
    *)
        echo "Usage: ./.dev.sh [local|groq|openrouter|backend|frontend|stop]"
        echo ""
        echo "  (default)         — LAN Ollama + backend + frontend"
        echo "  local             — local Ollama (qwen3.5:2b) + backend + frontend"
        echo "  groq              — Groq cloud (llama-3.3-70b, fast!) + backend + frontend"
        echo "  openrouter        — OpenRouter cloud (qwen3.5-9b) + backend + frontend"
        echo "  backend           — backend only (LAN Ollama)"
        echo "  backend local     — backend only (local Ollama)"
        echo "  backend groq      — backend only (Groq)"
        echo "  backend openrouter — backend only (OpenRouter)"
        echo "  frontend          — frontend only"
        echo "  stop              — stop all"
        exit 1
        ;;
esac
