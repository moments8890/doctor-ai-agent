#!/usr/bin/env bash
# ============================================================
# dev.sh — Local development startup for 专科医师AI智能体
#
# Modes:
#   ./dev.sh              — foreground with --reload (active dev)
#   ./dev.sh --background — launchd background service (leave Mac running)
#   ./dev.sh --stop       — stop background service
#   ./dev.sh --menu       — recreate WeChat menu (any mode)
#   ./dev.sh --no-frontend — backend only (skip Vite dev server)
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$APP_DIR/frontend"
SHARED_ENV="/Users/jingwuxu/Documents/code/shared-db/.env"
PORT=8000
FRONTEND_PORT=5173
NATAPP_URL=""
LOG_TUNNEL="$HOME/Library/Logs/aiagent-cloudflared.log"
LOG_UV="$HOME/Library/Logs/ai-agent-uvicorn.log"
LOG_FE="$HOME/Library/Logs/ai-agent-frontend.log"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_UV="$HOME/Library/LaunchAgents/com.aiagent.uvicorn.plist"
PLIST_TUNNEL="$HOME/Library/LaunchAgents/com.aiagent.cloudflared.plist"
PLIST_FE="$HOME/Library/LaunchAgents/com.aiagent.frontend.plist"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; }
info() { echo -e "  → $*"; }

MODE="foreground"
WANT_MENU=0
WANT_FRONTEND=1
for arg in "$@"; do
  case "$arg" in
    --background) MODE="background" ;;
    --stop) MODE="stop" ;;
    --menu) WANT_MENU=1 ;;
    --no-frontend) WANT_FRONTEND=0 ;;
    --help|-h)
      cat <<'EOF'
Usage: ./dev.sh [--background] [--stop] [--menu] [--no-frontend]
  --background   Run backend/frontend via launchd
  --stop         Stop launchd services and kill local ports
  --menu         Recreate WeChat menu
  --no-frontend  Skip starting Vite frontend
EOF
      exit 0
      ;;
  esac
done

read_env_var() {
  local key="$1"
  local file="$2"
  [ -f "$file" ] || return 1
  local line
  line=$(grep -E "^${key}=" "$file" | tail -n 1 || true)
  [ -n "$line" ] || return 1
  echo "${line#*=}" | sed 's/^"//; s/"$//'
}

tunnel_http_code() {
  [ -n "$NATAPP_URL" ] || { echo "000"; return; }
  curl -sS -m 2 -o /dev/null -w "%{http_code}" "$NATAPP_URL" 2>/dev/null || echo "000"
}

extract_tunnel_url() {
  python3 - <<'PY'
import re
from pathlib import Path
p = Path.home() / "Library/Logs/aiagent-cloudflared.log"
try:
    s = p.read_text(encoding="utf-8", errors="ignore")
except Exception:
    print("")
    raise SystemExit
# Prefer quick tunnel URL when present; otherwise fallback to any public URL emitted by cloudflared.
quick = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', s)
if quick:
    print(quick[-1])
    raise SystemExit

generic = re.findall(r'https?://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s|]*)?', s)
for url in reversed(generic):
    if "127.0.0.1" in url or "localhost" in url:
        continue
    if "cloudflare.com" in url and "trycloudflare.com" not in url:
        continue
    print(url.rstrip(" .|"))
    raise SystemExit

print("")
PY
}

write_uvicorn_plist() {
  mkdir -p "$LAUNCH_AGENTS_DIR"
  cat > "$PLIST_UV" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.aiagent.uvicorn</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "$APP_DIR" &amp;&amp; exec "$APP_DIR/.venv/bin/uvicorn" main:app --host 127.0.0.1 --port $PORT</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_UV</string>
  <key>StandardErrorPath</key>
  <string>$LOG_UV</string>
</dict>
</plist>
EOF
}

write_frontend_plist() {
  local npm_bin="$1"
  mkdir -p "$LAUNCH_AGENTS_DIR"
  cat > "$PLIST_FE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.aiagent.frontend</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "$FRONTEND_DIR" &amp;&amp; exec "$npm_bin" run dev -- --host 127.0.0.1 --port $FRONTEND_PORT</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_FE</string>
  <key>StandardErrorPath</key>
  <string>$LOG_FE</string>
</dict>
</plist>
EOF
}

write_cloudflared_plist() {
  local cloudflared_bin="$1"
  mkdir -p "$LAUNCH_AGENTS_DIR"
  cat > "$PLIST_TUNNEL" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.aiagent.cloudflared</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>exec "$cloudflared_bin" tunnel --url http://127.0.0.1:$PORT</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_TUNNEL</string>
  <key>StandardErrorPath</key>
  <string>$LOG_TUNNEL</string>
</dict>
</plist>
EOF
}

wait_http_ready() {
  local url="$1"
  local label="$2"
  local log_file="${3:-}"
  local tries="${4:-20}"
  info "Waiting for $label..."
  for i in $(seq 1 "$tries"); do
    if curl -sf "$url" &>/dev/null; then
      ok "$label healthy: $url"
      return 0
    fi
    if [ "$i" -eq "$tries" ]; then
      fail "$label did not start within ${tries}s"
      [ -n "$log_file" ] && tail -20 "$log_file" 2>/dev/null || true
      return 1
    fi
    sleep 1
  done
  return 1
}

# ── --stop mode ────────────────────────────────────────────
if [[ "$MODE" == "stop" ]]; then
  echo ""
  echo "  Stopping background services..."
  launchctl unload "$PLIST_UV"     2>/dev/null && ok "uvicorn stopped" || warn "uvicorn was not running"
  launchctl unload "$PLIST_TUNNEL" 2>/dev/null && ok "cloudflared tunnel stopped"  || warn "cloudflared tunnel was not running"
  launchctl unload "$PLIST_FE"     2>/dev/null && ok "frontend stopped" || warn "frontend was not running"
  lsof -ti :$PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
  lsof -ti :$FRONTEND_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
  pkill -f "caffeinate.*dev" 2>/dev/null && ok "caffeinate stopped" || true
  echo ""
  exit 0
fi

echo ""
echo "======================================================"
echo "  专科医师AI智能体 — dev startup"
[[ "$MODE" == "background" ]] && echo "  Mode: background (launchd)" || echo "  Mode: foreground (--reload)"
echo "======================================================"
echo ""

# ── 1. cloudflared binary ──────────────────────────────────
echo "[1/4] Checking cloudflared binary..."
if ! command -v cloudflared &>/dev/null; then
  fail "cloudflared not found. Install via: brew install cloudflared"
  exit 1
fi
CLOUDFLARED_BIN="$(command -v cloudflared)"
ok "cloudflared: $CLOUDFLARED_BIN"

# ── 1.5 Python env ─────────────────────────────────────────
if [[ ! -x "$APP_DIR/.venv/bin/uvicorn" ]]; then
  fail "Missing $APP_DIR/.venv/bin/uvicorn. Create venv and install deps first."
  exit 1
fi
ok "uvicorn binary: $APP_DIR/.venv/bin/uvicorn"

# ── 1.6 Frontend env (optional) ───────────────────────────
NPM_BIN=""
if [[ "$WANT_FRONTEND" -eq 1 ]]; then
  if [[ ! -d "$FRONTEND_DIR" ]]; then
    warn "frontend directory missing: $FRONTEND_DIR; skipping frontend startup"
    WANT_FRONTEND=0
  elif ! command -v npm &>/dev/null; then
    warn "npm not found; skipping frontend startup"
    WANT_FRONTEND=0
  else
    NPM_BIN="$(command -v npm)"
    ok "npm: $NPM_BIN"
  fi
fi

# ── 2. Ollama service + model ──────────────────────────────
echo ""
echo "[2/4] Checking Ollama endpoint..."
OLLAMA_BASE_URL="$(read_env_var OLLAMA_BASE_URL "$SHARED_ENV" || read_env_var OLLAMA_BASE_URL "$APP_DIR/.env" || echo "http://localhost:11434/v1")"
OLLAMA_MODEL="$(read_env_var OLLAMA_MODEL "$SHARED_ENV" || read_env_var OLLAMA_MODEL "$APP_DIR/.env" || echo "qwen2.5:14b")"
OLLAMA_TAGS_URL="${OLLAMA_BASE_URL%/v1}/api/tags"
OLLAMA_HOST="$(echo "$OLLAMA_BASE_URL" | sed -E 's#^https?://([^/:]+).*#\1#')"

if [[ "$OLLAMA_HOST" == "localhost" || "$OLLAMA_HOST" == "127.0.0.1" ]]; then
  info "OLLAMA_BASE_URL points to local host ($OLLAMA_BASE_URL)"
  if ! pgrep -x ollama &>/dev/null; then
    warn "Ollama not running locally — starting via brew services..."
    brew services start ollama
    sleep 3
  fi
else
  info "Using LAN Ollama endpoint: $OLLAMA_BASE_URL"
fi

if curl -sf "$OLLAMA_TAGS_URL" &>/dev/null; then
  ok "Ollama endpoint reachable: $OLLAMA_TAGS_URL"
else
  fail "Ollama endpoint is not reachable: $OLLAMA_TAGS_URL"
  exit 1
fi

if curl -sf "$OLLAMA_TAGS_URL" | grep -q "${OLLAMA_MODEL%%:*}"; then
  ok "Model '$OLLAMA_MODEL' available on configured endpoint"
else
  if [[ "$OLLAMA_HOST" == "localhost" || "$OLLAMA_HOST" == "127.0.0.1" ]]; then
    warn "Model '$OLLAMA_MODEL' not found locally — pulling (this may take a while)..."
    ollama pull "$OLLAMA_MODEL"
    ok "Model '$OLLAMA_MODEL' pulled"
  else
    warn "Model '$OLLAMA_MODEL' not listed on LAN endpoint; skipping local pull"
  fi
fi

# ── 3. cloudflared tunnel (always launchd) ─────────────────
echo ""
echo "[3/4] Starting cloudflared tunnel..."
write_cloudflared_plist "$CLOUDFLARED_BIN"
> "$LOG_TUNNEL" 2>/dev/null || true
launchctl unload "$PLIST_TUNNEL" 2>/dev/null || true
launchctl load   "$PLIST_TUNNEL"

info "Waiting for tunnel to connect..."
for i in $(seq 1 30); do
  NATAPP_URL="$(extract_tunnel_url)"
  code="$(tunnel_http_code)"
  if [[ "$code" != "000" ]]; then
    ok "cloudflared tunnel reachable (HTTP $code) → $NATAPP_URL"
    break
  fi
  if grep -Eiq "trycloudflare|Registered tunnel connection|Quick Tunnel" "$LOG_TUNNEL" 2>/dev/null; then
    info "cloudflared connected, waiting for public URL..."
  fi
  if [[ -n "$NATAPP_URL" ]]; then
    info "cloudflared URL discovered: $NATAPP_URL"
  fi
  if [[ -n "$NATAPP_URL" && "$code" == "000" ]]; then
    sleep 1
    continue
  fi
  if [[ -n "$NATAPP_URL" ]]; then
    ok "cloudflared tunnel online → $NATAPP_URL"
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    warn "Could not confirm tunnel URL — check: tail -f $LOG_TUNNEL"
    tail -20 "$LOG_TUNNEL" 2>/dev/null || true
  fi
  sleep 1
done

# ── 4. WeChat menu (optional) ──────────────────────────────
echo ""
echo "[4/4] WeChat menu..."
if [[ "$WANT_MENU" -eq 1 ]]; then
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

if [[ "$WANT_FRONTEND" -eq 1 ]]; then
  FE_STRAY=$(lsof -ti :$FRONTEND_PORT 2>/dev/null || true)
  [ -n "$FE_STRAY" ] && { warn "Port $FRONTEND_PORT in use — killing PID(s) $FE_STRAY"; echo "$FE_STRAY" | xargs kill -9 2>/dev/null || true; sleep 1; }
fi

if [[ "$MODE" == "background" ]]; then
  # ── Background mode: launchd manages uvicorn ─────────────
  write_uvicorn_plist
  launchctl unload "$PLIST_UV" 2>/dev/null || true
  launchctl load   "$PLIST_UV"

  wait_http_ready "http://127.0.0.1:$PORT/" "uvicorn" "$LOG_UV" 20

  if [[ "$WANT_FRONTEND" -eq 1 ]]; then
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
      info "Installing frontend deps..."
      (cd "$FRONTEND_DIR" && "$NPM_BIN" install)
    fi
    > "$LOG_FE" 2>/dev/null || true
    write_frontend_plist "$NPM_BIN"
    launchctl unload "$PLIST_FE" 2>/dev/null || true
    launchctl load   "$PLIST_FE"
    wait_http_ready "http://127.0.0.1:$FRONTEND_PORT/" "frontend" "$LOG_FE" 35
  fi

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
  [[ "$WANT_FRONTEND" -eq 1 ]] && echo "  Frontend   : http://127.0.0.1:$FRONTEND_PORT"
  [[ "$WANT_FRONTEND" -eq 1 ]] && echo "  Dashboard  : http://127.0.0.1:$FRONTEND_PORT/admin"
  echo "  Public URL : $NATAPP_URL"
  echo "  WeChat URL : $NATAPP_URL/wechat"
  echo ""
  echo "  API log    : tail -f $LOG_UV"
  [[ "$WANT_FRONTEND" -eq 1 ]] && echo "  FE log     : tail -f $LOG_FE"
  echo "  Stop : ./dev.sh --stop"
  echo "======================================================"
  echo ""
else
  # ── Foreground mode: uvicorn with --reload ────────────────
  FE_PID=""
  if [[ "$WANT_FRONTEND" -eq 1 ]]; then
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
      info "Installing frontend deps..."
      (cd "$FRONTEND_DIR" && "$NPM_BIN" install)
    fi
    > "$LOG_FE" 2>/dev/null || true
    info "Starting frontend on :$FRONTEND_PORT..."
    (
      cd "$FRONTEND_DIR"
      exec "$NPM_BIN" run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" >>"$LOG_FE" 2>&1
    ) &
    FE_PID=$!
    wait_http_ready "http://127.0.0.1:$FRONTEND_PORT/" "frontend" "$LOG_FE" 35
  fi

  cleanup() {
    if [[ -n "${FE_PID:-}" ]]; then
      kill "$FE_PID" 2>/dev/null || true
    fi
  }
  trap cleanup EXIT INT TERM

  echo "======================================================"
  echo -e "${GREEN}  Starting uvicorn — Ctrl+C to stop${NC}"
  echo "======================================================"
  echo ""
  echo "  Local API  : http://127.0.0.1:$PORT"
  [[ "$WANT_FRONTEND" -eq 1 ]] && echo "  Frontend   : http://127.0.0.1:$FRONTEND_PORT"
  [[ "$WANT_FRONTEND" -eq 1 ]] && echo "  Dashboard  : http://127.0.0.1:$FRONTEND_PORT/admin"
  echo "  Public URL : $NATAPP_URL"
  echo "  WeChat URL : $NATAPP_URL/wechat"
  echo "  Docs       : http://127.0.0.1:$PORT/docs"
  echo ""
  echo "  tunnel log : tail -f $LOG_TUNNEL"
  [[ "$WANT_FRONTEND" -eq 1 ]] && echo "  FE log     : tail -f $LOG_FE"
  echo "======================================================"
  echo ""
  cd "$APP_DIR"
  .venv/bin/uvicorn main:app --reload --port "$PORT"
fi
