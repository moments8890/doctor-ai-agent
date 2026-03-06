#!/usr/bin/env bash
# ============================================================
# dev.sh — Local-only development startup for 专科医师AI智能体
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
LOG_UV="$HOME/Library/Logs/ai-agent-uvicorn.log"
LOG_FE="$HOME/Library/Logs/ai-agent-frontend.log"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_UV="$HOME/Library/LaunchAgents/com.aiagent.uvicorn.plist"
PLIST_FE="$HOME/Library/LaunchAgents/com.aiagent.frontend.plist"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; }
info() { echo -e "  → $*"; }

# ── Unified subcommands (bootstrap/test/e2e/load-data/...) ───────────────
if [[ $# -gt 0 && "${1:-}" != -* ]]; then
  CMD="$1"
  shift || true

  PYTHON_BIN="python3"
  [[ -x "$APP_DIR/.venv/bin/python" ]] && PYTHON_BIN="$APP_DIR/.venv/bin/python"

  case "$CMD" in
    help)
      cat <<'EOF'
Usage:
  ./dev.sh start [--background] [--no-frontend] [--menu]
  ./dev.sh stop
  ./dev.sh bootstrap [--with-frontend]    # project deps (venv/pip/npm)
  ./dev.sh vm-bootstrap [--with-frontend] [--with-mysql]  # one-time VM provisioning
  ./dev.sh vm-up [--runtime <path>] [--backend-host <host>] [--backend-port <port>] [--frontend-host <host>] [--frontend-port <port>] [--no-frontend]  # start mysql+backend+frontend
  ./dev.sh vm-down [--remove-mysql]
  ./dev.sh run-backend [--host <host>] [--port <port>] [--reload]
  ./dev.sh test [unit|integration|integration-full|chatlog-half|chatlog-full|all]
  ./dev.sh e2e [half|full]
  ./dev.sh data [preload|export-seed|import-seed|reset-from-seed] [args...]
  ./dev.sh load-data [args for scripts/preload_patients.py]   # compatibility alias
  ./dev.sh chat [base_url] [doctor_id]
  ./dev.sh inspect-db

Compatibility:
  ./dev.sh                # same as start (foreground)
  ./dev.sh --background   # legacy flags still work
EOF
      exit 0
      ;;
    start)
      # Continue into legacy startup flow with any passed flags.
      set -- "$@"
      ;;
    stop)
      exec "$0" --stop
      ;;
    bootstrap)
      WITH_FRONTEND=0
      [[ "${1:-}" == "--with-frontend" ]] && WITH_FRONTEND=1
      if [[ ! -d "$APP_DIR/.venv" ]]; then
        python3 -m venv "$APP_DIR/.venv"
      fi
      PYTHON_BIN="$APP_DIR/.venv/bin/python"
      if [[ ! -x "$APP_DIR/.venv/bin/pip" ]]; then
        "$PYTHON_BIN" -m ensurepip --upgrade || true
      fi
      "$PYTHON_BIN" -m pip install --upgrade pip
      "$PYTHON_BIN" -m pip install -r "$APP_DIR/requirements.txt"
      if [[ "$WITH_FRONTEND" -eq 1 ]]; then
        if ! command -v npm >/dev/null 2>&1; then
          echo "npm not found. Run: ./dev.sh vm-bootstrap --with-frontend"
          exit 1
        fi
        npm --prefix "$APP_DIR/frontend" install
      fi
      exit 0
      ;;
    vm-bootstrap|vm-boostrap)
      WITH_FRONTEND=0
      WITH_MYSQL=0
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --with-frontend)
            WITH_FRONTEND=1
            shift
            ;;
          --with-mysql)
            WITH_MYSQL=1
            shift
            ;;
          *)
            echo "Unknown vm-bootstrap arg: $1"
            echo "Usage: ./dev.sh vm-bootstrap [--with-frontend] [--with-mysql]"
            exit 2
            ;;
        esac
      done

      # VM baseline packages (Ubuntu/Debian oriented).
      if command -v apt-get >/dev/null 2>&1; then
        if command -v sudo >/dev/null 2>&1; then
          sudo apt-get update
          sudo apt-get install -y ca-certificates curl git python3 python3-venv python3-pip ffmpeg
        else
          apt-get update
          apt-get install -y ca-certificates curl git python3 python3-venv python3-pip ffmpeg
        fi
      else
        echo "Unsupported OS package manager. Install python3-venv/python3-pip/git/curl/ffmpeg manually."
        exit 1
      fi

      # Docker engine (for mysql container and future containerized paths).
      if ! command -v docker >/dev/null 2>&1; then
        curl -fsSL https://get.docker.com | sh
      fi
      if command -v sudo >/dev/null 2>&1; then
        sudo usermod -aG docker "${USER:-ubuntu}" || true
      else
        usermod -aG docker "${USER:-ubuntu}" || true
      fi

      # Optional frontend toolchain.
      if [[ "$WITH_FRONTEND" -eq 1 ]] && ! command -v npm >/dev/null 2>&1; then
        if command -v sudo >/dev/null 2>&1; then
          sudo apt-get install -y nodejs npm
        else
          apt-get install -y nodejs npm
        fi
      fi

      # Optional local mysql container.
      if [[ "$WITH_MYSQL" -eq 1 ]]; then
        MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-DrAI_Root_2026!x9}"
        MYSQL_DATABASE="${MYSQL_DATABASE:-doctor_ai}"
        MYSQL_USER="${MYSQL_USER:-doctor_ai}"
        MYSQL_PASSWORD="${MYSQL_PASSWORD:-DrAI_App_2026!x9}"
        docker rm -f doctor-ai-mysql >/dev/null 2>&1 || true
        docker run -d --name doctor-ai-mysql \
          --restart unless-stopped \
          -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_PASSWORD" \
          -e MYSQL_DATABASE="$MYSQL_DATABASE" \
          -e MYSQL_USER="$MYSQL_USER" \
          -e MYSQL_PASSWORD="$MYSQL_PASSWORD" \
          -p 127.0.0.1:3306:3306 \
          -v doctor_ai_mysql_data:/var/lib/mysql \
          mysql:8.0 \
          --default-authentication-plugin=mysql_native_password \
          --character-set-server=utf8mb4 \
          --collation-server=utf8mb4_unicode_ci

        mkdir -p "$APP_DIR/config"
        if [[ -f "$APP_DIR/deploy/tencent/runtime.prod.mysql-single-node.example.json" ]] && [[ ! -f "$APP_DIR/config/runtime.prod.json" ]]; then
          cp "$APP_DIR/deploy/tencent/runtime.prod.mysql-single-node.example.json" "$APP_DIR/config/runtime.prod.json"
          echo "Generated $APP_DIR/config/runtime.prod.json from mysql single-node template."
          echo "Remember to update DEEPSEEK_API_KEY and WECHAT_* values."
        fi
      fi

      # Reuse unified bootstrap.
      if [[ "$WITH_FRONTEND" -eq 1 ]]; then
        exec "$0" bootstrap --with-frontend
      fi
      exec "$0" bootstrap
      ;;
    vm-up|tencent-up)
      RUNTIME_PATH="$APP_DIR/config/runtime.json"
      BACKEND_HOST="0.0.0.0"
      BACKEND_PORT="8000"
      FRONTEND_HOST="0.0.0.0"
      FRONTEND_PORT_VM="5173"
      MYSQL_CONTAINER="${MYSQL_CONTAINER:-doctor-ai-mysql}"
      MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-DrAI_Root_2026!x9}"
      MYSQL_DATABASE="${MYSQL_DATABASE:-doctor_ai}"
      MYSQL_USER="${MYSQL_USER:-doctor_ai}"
      MYSQL_PASSWORD="${MYSQL_PASSWORD:-DrAI_App_2026!x9}"
      START_FRONTEND=1

      while [[ $# -gt 0 ]]; do
        case "$1" in
          --runtime)
            RUNTIME_PATH="${2:-$RUNTIME_PATH}"
            shift 2
            ;;
          --backend-host)
            BACKEND_HOST="${2:-$BACKEND_HOST}"
            shift 2
            ;;
          --backend-port)
            BACKEND_PORT="${2:-$BACKEND_PORT}"
            shift 2
            ;;
          --frontend-host)
            FRONTEND_HOST="${2:-$FRONTEND_HOST}"
            shift 2
            ;;
          --frontend-port)
            FRONTEND_PORT_VM="${2:-$FRONTEND_PORT_VM}"
            shift 2
            ;;
          --no-frontend)
            START_FRONTEND=0
            shift
            ;;
          *)
            echo "Unknown vm-up arg: $1"
            echo "Usage: ./dev.sh vm-up [--runtime <path>] [--backend-host <host>] [--backend-port <port>] [--frontend-host <host>] [--frontend-port <port>] [--no-frontend]"
            exit 2
            ;;
        esac
      done

      if ! command -v docker >/dev/null 2>&1; then
        echo "docker not found. Run: ./dev.sh vm-bootstrap --with-mysql"
        exit 1
      fi
      if [[ ! -x "$APP_DIR/.venv/bin/uvicorn" ]]; then
        echo "Missing .venv/uvicorn. Run: ./dev.sh bootstrap --with-frontend"
        exit 1
      fi
      if [[ "$START_FRONTEND" -eq 1 ]] && ! command -v npm >/dev/null 2>&1; then
        echo "npm not found. Run: ./dev.sh vm-bootstrap --with-frontend"
        exit 1
      fi

      # vm-up is runtime start only; provisioning belongs to vm-bootstrap.
      if docker ps -a --format '{{.Names}}' | grep -qx "$MYSQL_CONTAINER"; then
        docker start "$MYSQL_CONTAINER" >/dev/null
      else
        echo "MySQL container '$MYSQL_CONTAINER' not found. Run: ./dev.sh vm-bootstrap --with-mysql"
        exit 1
      fi

      echo "Waiting for MySQL container health..."
      READY=0
      for _ in $(seq 1 40); do
        STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$MYSQL_CONTAINER" 2>/dev/null || true)"
        if [[ "$STATUS" == "healthy" || "$STATUS" == "running" ]]; then
          READY=1
          break
        fi
        sleep 2
      done
      if [[ "$READY" -ne 1 ]]; then
        echo "MySQL container failed to become healthy. Check: docker logs $MYSQL_CONTAINER"
        exit 1
      fi

      # Ensure runtime config targets remote DeepSeek + local MySQL.
      DEEPSEEK_KEY_FROM_ENV="${DEEPSEEK_API_KEY:-}"
      env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - <<PY
from utils.runtime_json import load_runtime_json, save_runtime_json
cfg = load_runtime_json("$RUNTIME_PATH")
cfg["ROUTING_LLM"] = "deepseek"
cfg["STRUCTURING_LLM"] = "deepseek"
cfg["INTENT_PROVIDER"] = "model-driven"
cfg["DATABASE_URL"] = "mysql+aiomysql://$MYSQL_USER:$MYSQL_PASSWORD@127.0.0.1:3306/$MYSQL_DATABASE?charset=utf8mb4"
deepseek_env = """$DEEPSEEK_KEY_FROM_ENV""".strip()
if deepseek_env:
    cfg["DEEPSEEK_API_KEY"] = deepseek_env
if not str(cfg.get("DEEPSEEK_API_KEY", "")).strip():
    raise SystemExit("DEEPSEEK_API_KEY is empty. Set env DEEPSEEK_API_KEY or update runtime config.")
save_runtime_json(cfg, "$RUNTIME_PATH")
print("Runtime config updated:", "$RUNTIME_PATH")
PY

      mkdir -p "$APP_DIR/logs"
      PID_DIR="$APP_DIR/logs/pids"
      mkdir -p "$PID_DIR"
      BACKEND_LOG="$APP_DIR/logs/backend.vm.log"
      FRONTEND_LOG="$APP_DIR/logs/frontend.vm.log"
      BACKEND_PID_FILE="$PID_DIR/backend.vm.pid"
      FRONTEND_PID_FILE="$PID_DIR/frontend.vm.pid"

      for p in "$BACKEND_PORT" "$FRONTEND_PORT_VM"; do
        if lsof -ti :"$p" >/dev/null 2>&1; then
          lsof -ti :"$p" | xargs kill -9 2>/dev/null || true
          sleep 1
        fi
      done

      if [[ -f "$BACKEND_PID_FILE" ]]; then
        kill "$(cat "$BACKEND_PID_FILE")" 2>/dev/null || true
        rm -f "$BACKEND_PID_FILE"
      fi
      if [[ -f "$FRONTEND_PID_FILE" ]]; then
        kill "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null || true
        rm -f "$FRONTEND_PID_FILE"
      fi

      (
        cd "$APP_DIR"
        exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
          "$APP_DIR/.venv/bin/uvicorn" main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
      ) >>"$BACKEND_LOG" 2>&1 &
      echo $! > "$BACKEND_PID_FILE"

      if [[ "$START_FRONTEND" -eq 1 ]]; then
        if [[ ! -d "$APP_DIR/frontend/node_modules" ]]; then
          echo "frontend/node_modules missing. Run: ./dev.sh vm-bootstrap --with-frontend"
          exit 1
        fi
        (
          cd "$APP_DIR/frontend"
          exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT_VM"
        ) >>"$FRONTEND_LOG" 2>&1 &
        echo $! > "$FRONTEND_PID_FILE"
      fi

      echo ""
      echo "VM services started:"
      echo "  MySQL      : docker container $MYSQL_CONTAINER (127.0.0.1:3306)"
      echo "  Backend    : http://$BACKEND_HOST:$BACKEND_PORT (log: $BACKEND_LOG)"
      if [[ "$START_FRONTEND" -eq 1 ]]; then
        echo "  Frontend   : http://$FRONTEND_HOST:$FRONTEND_PORT_VM (log: $FRONTEND_LOG)"
      else
        echo "  Frontend   : skipped (--no-frontend)"
      fi
      echo "  Stop all   : ./dev.sh vm-down"
      exit 0
      ;;
    vm-down|tencent-down)
      REMOVE_MYSQL=0
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --remove-mysql)
            REMOVE_MYSQL=1
            shift
            ;;
          *)
            echo "Unknown vm-down arg: $1"
            echo "Usage: ./dev.sh vm-down [--remove-mysql]"
            exit 2
            ;;
        esac
      done

      PID_DIR="$APP_DIR/logs/pids"
      BACKEND_PID_FILE="$PID_DIR/backend.vm.pid"
      FRONTEND_PID_FILE="$PID_DIR/frontend.vm.pid"
      MYSQL_CONTAINER="${MYSQL_CONTAINER:-doctor-ai-mysql}"

      if [[ -f "$BACKEND_PID_FILE" ]]; then
        kill "$(cat "$BACKEND_PID_FILE")" 2>/dev/null || true
        rm -f "$BACKEND_PID_FILE"
      fi
      if [[ -f "$FRONTEND_PID_FILE" ]]; then
        kill "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null || true
        rm -f "$FRONTEND_PID_FILE"
      fi
      lsof -ti :8000 2>/dev/null | xargs kill -9 2>/dev/null || true
      lsof -ti :5173 2>/dev/null | xargs kill -9 2>/dev/null || true

      if command -v docker >/dev/null 2>&1; then
        if docker ps --format '{{.Names}}' | grep -qx "$MYSQL_CONTAINER"; then
          if [[ "$REMOVE_MYSQL" -eq 1 ]]; then
            docker rm -f "$MYSQL_CONTAINER" >/dev/null || true
            echo "Stopped and removed MySQL container: $MYSQL_CONTAINER"
          else
            docker stop "$MYSQL_CONTAINER" >/dev/null || true
            echo "Stopped MySQL container: $MYSQL_CONTAINER"
          fi
        fi
      fi

      echo "Stopped VM backend/frontend services."
      exit 0
      ;;
    run-backend)
      HOST="0.0.0.0"
      RUN_PORT="8000"
      RELOAD=0
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --host)
            HOST="${2:-$HOST}"
            shift 2
            ;;
          --port)
            RUN_PORT="${2:-$RUN_PORT}"
            shift 2
            ;;
          --reload)
            RELOAD=1
            shift
            ;;
          *)
            echo "Unknown run-backend arg: $1"
            echo "Usage: ./dev.sh run-backend [--host <host>] [--port <port>] [--reload]"
            exit 2
            ;;
        esac
      done
      if [[ ! -x "$APP_DIR/.venv/bin/uvicorn" ]]; then
        echo "Missing .venv/uvicorn. Run: ./dev.sh bootstrap"
        exit 1
      fi
      if [[ "$RELOAD" -eq 1 ]]; then
        exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
          "$APP_DIR/.venv/bin/uvicorn" main:app --host "$HOST" --port "$RUN_PORT" --reload
      fi
      exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        "$APP_DIR/.venv/bin/uvicorn" main:app --host "$HOST" --port "$RUN_PORT"
      ;;
    test)
      MODE="${1:-unit}"
      shift || true
      exec bash "$APP_DIR/scripts/test.sh" "$MODE" "$@"
      ;;
    e2e)
      MODE="${1:-half}"
      shift || true
      if [[ "$MODE" == "half" ]]; then
        exec bash "$APP_DIR/scripts/test.sh" chatlog-half "$@"
      elif [[ "$MODE" == "full" ]]; then
        exec bash "$APP_DIR/scripts/test.sh" chatlog-full "$@"
      else
        echo "Unknown e2e mode: $MODE (use half|full)"
        exit 2
      fi
      ;;
    data)
      SUB="${1:-}"
      shift || true
      case "$SUB" in
        preload|"")
          exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
            "$PYTHON_BIN" "$APP_DIR/scripts/preload_patients.py" "$@"
          ;;
        export-seed)
          exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
            "$PYTHON_BIN" "$APP_DIR/scripts/seed_db.py" --export "$@"
          ;;
        import-seed)
          exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
            "$PYTHON_BIN" "$APP_DIR/scripts/seed_db.py" --import "$@"
          ;;
        reset-from-seed)
          exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
            "$PYTHON_BIN" "$APP_DIR/scripts/seed_db.py" --reset --import "$@"
          ;;
        *)
          echo "Unknown data subcommand: $SUB"
          echo "Use: ./dev.sh data [preload|export-seed|import-seed|reset-from-seed]"
          exit 2
          ;;
      esac
      ;;
    load-data)
      exec "$0" data preload "$@"
      ;;
    chat)
      exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        "$PYTHON_BIN" "$APP_DIR/scripts/chat.py" "${1:-http://127.0.0.1:8000}" "${2:-test_doctor}"
      ;;
    inspect-db)
      exec env PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        "$PYTHON_BIN" "$APP_DIR/scripts/db_inspect.py" "$@"
      ;;
    *)
      echo "Unknown command: $CMD"
      echo "Run ./dev.sh help"
      exit 2
      ;;
  esac
fi

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
  echo "000"
}

extract_tunnel_url() {
  echo ""
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

# ── 1. Python env ───────────────────────────────────────────
echo "[1/3] Checking Python environment..."
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

# ── 3. WeChat menu (optional, local only) ──────────────────
echo ""
echo "[3/3] WeChat menu..."
if [[ "$WANT_MENU" -eq 1 ]]; then
  if curl -sf "http://127.0.0.1:$PORT/" &>/dev/null; then
    RESULT=$(curl -sf -X POST "http://127.0.0.1:$PORT/wechat/menu" || echo '{"status":"error"}')
    echo "$RESULT" | grep -q '"ok"' && ok "Menu created" || warn "Menu response: $RESULT"
  else
    warn "Server not up yet — run after startup: curl -X POST http://127.0.0.1:$PORT/wechat/menu"
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
  echo "  WeChat URL : http://127.0.0.1:$PORT/wechat"
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
  echo "  WeChat URL : http://127.0.0.1:$PORT/wechat"
  echo "  Docs       : http://127.0.0.1:$PORT/docs"
  echo ""
  [[ "$WANT_FRONTEND" -eq 1 ]] && echo "  FE log     : tail -f $LOG_FE"
  echo "======================================================"
  echo ""
  cd "$APP_DIR"
  .venv/bin/uvicorn main:app --reload --port "$PORT"
fi
