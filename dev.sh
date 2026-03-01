#!/usr/bin/env bash
# ============================================================
# dev.sh — Local development startup for 专科医师AI智能体
#
# Modes:
#   ./dev.sh              — foreground with --reload (active dev)
#   ./dev.sh --background — launchd background service (leave Mac running)
#   ./dev.sh --stop       — stop background service
#   ./dev.sh --menu       — recreate WeChat menu (any mode)
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8000
NATAPP_URL="http://n686efdb.natappfree.cc"
LOG_NATAPP="$HOME/Library/Logs/aiagent-natapp.log"
LOG_UV="$HOME/Library/Logs/ai-agent-uvicorn.log"
PLIST_UV="$HOME/Library/LaunchAgents/com.aiagent.uvicorn.plist"
PLIST_NATAPP="$HOME/Library/LaunchAgents/com.aiagent.natapp.plist"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; }
info() { echo -e "  → $*"; }

# ── --stop mode ────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
  echo ""
  echo "  Stopping background services..."
  launchctl unload "$PLIST_UV"     2>/dev/null && ok "uvicorn stopped" || warn "uvicorn was not running"
  launchctl unload "$PLIST_NATAPP" 2>/dev/null && ok "natapp stopped"  || warn "natapp was not running"
  lsof -ti :$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
  pkill -f "caffeinate.*dev" 2>/dev/null && ok "caffeinate stopped" || true
  echo ""
  exit 0
fi

echo ""
echo "======================================================"
echo "  专科医师AI智能体 — dev startup"
[[ "${1:-}" == "--background" ]] && echo "  Mode: background (launchd)" || echo "  Mode: foreground (--reload)"
echo "======================================================"
echo ""

# ── 1. natapp binary ───────────────────────────────────────
echo "[1/4] Checking natapp binary..."
if ! command -v natapp &>/dev/null; then
  fail "natapp not found. Download from natapp.cn → /usr/local/bin/natapp"
  exit 1
fi
ok "natapp: $(which natapp)"

# ── 2. Ollama service + model ──────────────────────────────
echo ""
echo "[2/4] Checking Ollama..."
if ! pgrep -x ollama &>/dev/null; then
  warn "Ollama not running — starting via brew services..."
  brew services start ollama
  sleep 3
fi

if curl -sf http://localhost:11434/api/tags &>/dev/null; then
  ok "Ollama running on :11434"
else
  fail "Ollama is not responding on localhost:11434"
  exit 1
fi

MODEL=$(grep OLLAMA_MODEL "$APP_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "qwen2.5:7b")
if curl -sf http://localhost:11434/api/tags | grep -q "${MODEL%%:*}"; then
  ok "Model '$MODEL' available"
else
  warn "Model '$MODEL' not found — pulling (this may take a while)..."
  ollama pull "$MODEL"
  ok "Model '$MODEL' pulled"
fi

# ── 3. natapp tunnel (always launchd) ──────────────────────
echo ""
echo "[3/4] Starting natapp tunnel..."
> "$LOG_NATAPP" 2>/dev/null || true
launchctl unload "$PLIST_NATAPP" 2>/dev/null || true
launchctl load   "$PLIST_NATAPP"

info "Waiting for tunnel to connect..."
for i in $(seq 1 15); do
  if grep -q "Online" "$LOG_NATAPP" 2>/dev/null; then
    ok "natapp tunnel online → $NATAPP_URL"
    break
  fi
  [ "$i" -eq 15 ] && warn "Could not confirm tunnel — check: tail -f $LOG_NATAPP"
  sleep 1
done

# ── 4. WeChat menu (optional) ──────────────────────────────
echo ""
echo "[4/4] WeChat menu..."
if [[ "${*}" == *"--menu"* ]]; then
  if curl -sf "http://127.0.0.1:$PORT/" &>/dev/null; then
    RESULT=$(curl -sf -X POST "$NATAPP_URL/wechat/menu" || echo '{"status":"error"}')
    echo "$RESULT" | grep -q '"ok"' && ok "Menu created" || warn "Menu response: $RESULT"
  else
    warn "Server not up yet — run after startup: curl -X POST $NATAPP_URL/wechat/menu"
  fi
else
  info "Skipping (add --menu flag to create/update WeChat menu)"
fi

# ── Launch uvicorn ─────────────────────────────────────────
echo ""
STRAY=$(lsof -ti :$PORT 2>/dev/null || true)
[ -n "$STRAY" ] && { warn "Port $PORT in use — killing PID(s) $STRAY"; echo "$STRAY" | xargs kill -9 2>/dev/null || true; sleep 1; }

if [[ "${1:-}" == "--background" ]]; then
  # ── Background mode: launchd manages uvicorn ─────────────
  launchctl unload "$PLIST_UV" 2>/dev/null || true
  launchctl load   "$PLIST_UV"

  info "Waiting for uvicorn to start..."
  for i in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:$PORT/" &>/dev/null; then
      ok "uvicorn healthy on :$PORT"
      break
    fi
    if [ "$i" -eq 20 ]; then
      fail "uvicorn did not start within 20s"
      tail -20 "$LOG_UV" 2>/dev/null || true
      exit 1
    fi
    sleep 1
  done

  # Prevent Mac from sleeping (kills network on sleep)
  pkill -f "caffeinate.*dev" 2>/dev/null || true
  caffeinate -i -w $$ &
  ok "caffeinate active — Mac will not sleep while running"

  echo ""
  echo "======================================================"
  echo -e "${GREEN}  Running in background — safe to close terminal${NC}"
  echo "======================================================"
  echo ""
  echo "  Local API  : http://127.0.0.1:$PORT"
  echo "  Public URL : $NATAPP_URL"
  echo "  WeChat URL : $NATAPP_URL/wechat"
  echo ""
  echo "  Logs : tail -f $LOG_UV"
  echo "  Stop : ./dev.sh --stop"
  echo "======================================================"
  echo ""
else
  # ── Foreground mode: uvicorn with --reload ────────────────
  echo "======================================================"
  echo -e "${GREEN}  Starting uvicorn — Ctrl+C to stop${NC}"
  echo "======================================================"
  echo ""
  echo "  Local API  : http://127.0.0.1:$PORT"
  echo "  Public URL : $NATAPP_URL"
  echo "  WeChat URL : $NATAPP_URL/wechat"
  echo "  Docs       : http://127.0.0.1:$PORT/docs"
  echo ""
  echo "  natapp log : tail -f $LOG_NATAPP"
  echo "======================================================"
  echo ""
  cd "$APP_DIR"
  exec .venv/bin/uvicorn main:app --reload --port $PORT
fi
