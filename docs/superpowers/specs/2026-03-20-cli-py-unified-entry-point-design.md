# cli.py — Unified Entry Point

> **Status: ✅ DONE** — spec implemented and shipped.

**Date:** 2026-03-20
**Status:** Draft
**Replaces:** `dev.sh` (980 lines bash)

## Goal

Replace `dev.sh` with a single Python script `cli.py` that serves as the entry point for both local development and production, using `argparse` with subcommands.

## CLI Surface

```
./cli.py -h
./cli.py start [-h] [--prod] [--provider {deepseek,groq,cerebras,sambanova,siliconflow,openrouter,tencent_lkeap,openai,ollama}]
               [--host HOST] [--port PORT] [--workers N] [--reload] [--no-frontend]
               [--background] [--tunnel] [--menu]
./cli.py stop [-h] [--remove-mysql]
./cli.py bootstrap [-h] [--vm]
```

## Commands

### `start`

Starts the backend (uvicorn) and optionally the frontend (Vite).

| Flag | Default (dev) | Default (prod) | Description |
|------|--------------|----------------|-------------|
| `--prod` | off | — | Production mode |
| `--provider P` | ollama | — | LLM provider; sets `ROUTING_LLM`, `STRUCTURING_LLM`, `CONVERSATION_LLM` env vars |
| `--host` | `127.0.0.1` | `0.0.0.0` | Bind address |
| `--port` | `8000` | `8000` | Backend port |
| `--workers` | 1 | 1 | Uvicorn worker count |
| `--reload` | off | off | Auto-reload on file change |
| `--no-frontend` | off | off | Skip Vite dev server |
| `--background` | off | off | macOS launchd background mode |
| `--tunnel` | off | off | Cloudflare quick tunnel |
| `--menu` | off | off | Create/update WeChat menu after startup |

#### Dev mode (default)

1. Verify `.venv/bin/uvicorn` exists
2. Set environment: `PYTHONPATH=<APP_DIR>/src`, `ENVIRONMENT=development`
3. If provider is `ollama` and endpoint is local:
   - Check Ollama is running, start via `brew services` if not (macOS only; skip with warning if `brew` unavailable)
   - Check configured model is available; auto-pull if missing and endpoint is local
4. If provider is not `ollama`: validate corresponding API key env var is set
5. Kill stray processes on backend port (and frontend port if applicable)
6. Start frontend subprocess (`npm run dev -- --host 127.0.0.1 --port 5173`) unless `--no-frontend`
   - If `--reload` is off: set `VITE_NO_HMR=1` env var for the frontend subprocess
7. `cd` into `APP_DIR/src` (working directory for uvicorn)
8. Start uvicorn: `uvicorn main:app --host 127.0.0.1 --port 8000`
9. If `--background`:
   - Generate launchd plists, `launchctl load` (macOS only; error on Linux)
   - Start `caffeinate -i` to prevent macOS sleep
10. If `--tunnel`: start `cloudflared tunnel` subprocess
11. If `--menu`: poll `http://127.0.0.1:<port>/` every 1s for up to 20s, then POST to `/wechat/menu`
12. Trap `SIGINT`/`SIGTERM` → kill child processes (frontend, tunnel, caffeinate), exit clean

#### Prod mode (`--prod`)

1. Validate `config/runtime.json` exists
2. Validate required keys present: `DATABASE_URL` must be non-empty; at least one LLM provider API key must be set (checked via the nested `.value` structure in runtime.json)
3. If `--provider` is given: write `ROUTING_LLM`, `STRUCTURING_LLM`, `CONVERSATION_LLM` values into `config/runtime.json` (same config-patching behavior as current `vm-up`)
4. Set environment: `PYTHONPATH=<APP_DIR>/src`, `ENVIRONMENT=production`
5. MySQL health check — wait for Docker container `doctor-ai-mysql` to be healthy (up to 80s, 2s intervals via `docker inspect`)
6. Kill stray processes on backend/frontend ports (using `lsof` on macOS, `ss -tlnp` on Linux as fallback)
7. Start frontend subprocess (`npm run dev -- --host 0.0.0.0 --port 5173`) unless `--no-frontend`
8. `cd` into `APP_DIR/src`
9. Start uvicorn: `uvicorn main:app --host 0.0.0.0 --port 8000 --workers N`
10. If `--tunnel`: start cloudflared
11. Trap signals → graceful shutdown of all children

#### `--provider` behavior

Sets three env vars (`ROUTING_LLM`, `STRUCTURING_LLM`, `CONVERSATION_LLM`) before launching uvicorn.

In `--prod` mode, also patches these values into `config/runtime.json`.

| Provider | Env var validated |
|----------|------------------|
| `deepseek` | `DEEPSEEK_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `cerebras` | `CEREBRAS_API_KEY` |
| `sambanova` | `SAMBANOVA_API_KEY` |
| `siliconflow` | `SILICONFLOW_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `tencent_lkeap` | `TENCENT_LKEAP_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `ollama` | — (no key needed) |

### `stop`

1. Read pid files from `logs/pids/` and kill processes
2. Port-scan `:8000` and `:5173` — kill anything found (`lsof` on macOS, `ss`/`fuser` on Linux)
3. Kill cloudflare tunnel if pid file exists
4. If launchd plists exist: `launchctl unload` them
5. Kill `caffeinate` if running
6. `--remove-mysql`: `docker rm -f doctor-ai-mysql`

### `bootstrap`

Installs project dependencies. With `--vm`, also provisions infrastructure (system packages, Docker, MySQL).

**Always (macOS + Linux):**
1. Create `.venv` if missing
2. `pip install --upgrade pip`
3. `pip install -r requirements.txt`
4. If `npm` is available: `npm install` in `frontend/web`

**With `--vm` flag (intended for VM/prod Linux hosts):**
5. Install system packages via `apt-get`: `python3 python3-venv python3-pip git curl ffmpeg nodejs npm`
6. Install Docker if missing (`curl -fsSL https://get.docker.com | sh`)
7. Add current user to `docker` group
8. Start MySQL container if not already running:
   - Image: `mysql:8.0`
   - Container name: `doctor-ai-mysql`
   - Ports: `127.0.0.1:3306:3306`
   - Volume: `doctor_ai_mysql_data`
   - Charset: `utf8mb4`
   - Credentials from env vars with defaults

## Implementation Details

### File

Single file: `cli.py` at project root (next to `dev.sh`).

### Dependencies

Zero new dependencies. Uses only stdlib: `argparse`, `subprocess`, `signal`, `os`, `sys`, `platform`, `shutil`, `time`, `json`, `pathlib`.

### Environment setup

Before launching uvicorn, `cli.py` sets:

| Variable | Dev | Prod |
|----------|-----|------|
| `PYTHONPATH` | `<APP_DIR>/src` (prepended to existing) | `<APP_DIR>/src` (prepended to existing) |
| `ENVIRONMENT` | `development` | `production` |
| `ROUTING_LLM` | from `--provider` | from `--provider` |
| `STRUCTURING_LLM` | from `--provider` | from `--provider` |
| `CONVERSATION_LLM` | from `--provider` | from `--provider` |

Working directory for the uvicorn subprocess: `APP_DIR/src`.

### Process management

- Child processes tracked in a list; `atexit` + signal handler kills them all
- Pid files written to `logs/pids/` for `stop` command
- `subprocess.Popen` for long-running children (uvicorn, vite, cloudflared, caffeinate)
- `subprocess.run` for short commands (lsof, kill, docker, brew, apt-get, npm install)

### Port scanning

- macOS: `lsof -ti :<port>`
- Linux: `ss -tlnp sport = :<port>` with pid extraction, falling back to `fuser <port>/tcp`

### Colored output

ANSI escape codes, same helpers as current `dev.sh`:
- `ok()` — green checkmark
- `warn()` — yellow warning
- `fail()` — red X
- `info()` — arrow prefix

Disable color when `stdout` is not a TTY (for CI/systemd journal).

### Constants

```python
APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR / "src"
FRONTEND_DIR = APP_DIR / "frontend" / "web"
VENV_PYTHON = APP_DIR / ".venv" / "bin" / "python"
VENV_UVICORN = APP_DIR / ".venv" / "bin" / "uvicorn"
PID_DIR = APP_DIR / "logs" / "pids"
LOG_DIR = APP_DIR / "logs"
RUNTIME_JSON = APP_DIR / "config" / "runtime.json"
DEFAULT_PORT = 8000
FRONTEND_PORT = 5173
```

### Ollama checks (dev mode)

When provider is `ollama`:
1. Read `OLLAMA_BASE_URL` from `config/runtime.json` (nested `.value` key), fallback to `http://localhost:11434/v1`
2. Read `OLLAMA_MODEL` from `config/runtime.json`, fallback to `qwen3.5:9b`
3. If endpoint is local (`localhost` / `127.0.0.1`):
   - Check if `ollama` process is running (`pgrep -x ollama`)
   - If not: try `brew services start ollama` on macOS (warn and skip if `brew` not found)
4. Probe `<base_url_without_v1>/api/tags` to check endpoint reachability
5. If model not listed in tags response and endpoint is local: run `ollama pull <model>`

### runtime.json structure

The config file uses a nested structure where each key maps to `{"value": <actual_value>, ...}`. When reading/writing, access via the `.value` sub-key. Example:

```json
{
  "llm": {
    "ROUTING_LLM": {"value": "deepseek", "description": "..."},
    "DEEPSEEK_API_KEY": {"value": "sk-...", "description": "..."}
  }
}
```

Validation in prod mode walks all groups, extracts `DATABASE_URL.value` and checks it is non-empty.

### launchd (macOS `--background`)

Generate `.plist` files to `~/Library/LaunchAgents/` — same behavior as current `dev.sh`. Only available on macOS; error on Linux if `--background` is used.

### Deprecation of `dev.sh`

Keep `dev.sh` temporarily with:
```bash
#!/usr/bin/env bash
# DEPRECATED — use ./cli.py instead
case "${1:-}" in
  test|e2e|data|load-data|chat|inspect-db)
    echo "Subcommand '$1' moved to scripts/. See ./cli.py -h" >&2
    exit 2
    ;;
esac
echo "DEPRECATED: use ./cli.py instead" >&2
exec "$(dirname "$0")/.venv/bin/python" "$(dirname "$0")/cli.py" "$@"
```

### systemd integration

The existing systemd service file changes from:
```
ExecStart=.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```
to:
```
ExecStart=.venv/bin/python cli.py start --prod
```

## Out of scope

These subcommands stay in their current locations and are not part of `cli.py`:

| Old command | Where it lives now |
|---|---|
| `./dev.sh test` | `scripts/test.sh` |
| `./dev.sh e2e` | `scripts/test.sh chatlog-*` |
| `./dev.sh data` | `scripts/preload_patients.py`, `scripts/seed_db.py` |
| `./dev.sh load-data` | `scripts/preload_patients.py` |
| `./dev.sh chat` | `scripts/chat.py` |
| `./dev.sh inspect-db` | `scripts/db_inspect.py`, `scripts/start_db_ui.sh` |
| `./dev.sh run-backend` | `./cli.py start --prod --no-frontend` (equivalent) |
| `./dev.sh help` | `./cli.py -h` |

Provider shortcut migration: `./dev.sh deepseek` → `./cli.py start --provider deepseek`.

## Migration

1. Build `cli.py` with all three commands
2. Replace `dev.sh` with deprecation shim (routes removed subcommands to helpful error)
3. Update systemd service to use `cli.py start --prod`
4. Update `AGENTS.md` / `ARCHITECTURE.md` references
