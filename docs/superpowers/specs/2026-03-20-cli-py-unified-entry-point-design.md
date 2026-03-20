# cli.py — Unified Entry Point

**Date:** 2026-03-20
**Status:** Draft
**Replaces:** `dev.sh` (980 lines bash)

## Goal

Replace `dev.sh` with a single Python script `cli.py` that serves as the entry point for both local development and production, using `argparse` with subcommands.

## CLI Surface

```
./cli.py -h
./cli.py start [-h] [--prod] [--provider {deepseek,groq,cerebras,sambanova,siliconflow,openrouter,ollama}]
               [--host HOST] [--port PORT] [--workers N] [--reload] [--no-frontend]
               [--background] [--tunnel] [--menu]
./cli.py stop [-h] [--remove-mysql]
./cli.py bootstrap [-h]
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
2. If provider is `ollama` and endpoint is local: check Ollama is running, start via `brew services` if not (macOS only)
3. If provider is not `ollama`: validate corresponding API key env var is set
4. Kill stray processes on backend port (and frontend port if applicable)
5. Start frontend subprocess (`npm run dev`) unless `--no-frontend`
6. Start uvicorn on `127.0.0.1:8000`
7. If `--background`: generate launchd plists, `launchctl load`
8. If `--tunnel`: start `cloudflared tunnel` subprocess
9. If `--menu`: POST to `/wechat/menu` once server is healthy
10. Trap `SIGINT`/`SIGTERM` → kill child processes, exit clean

#### Prod mode (`--prod`)

1. Validate `config/runtime.json` exists
2. Validate required keys present (DATABASE_URL, at least one LLM provider key)
3. MySQL health check — wait for Docker container `doctor-ai-mysql` to be healthy (up to 80s, 2s intervals)
4. Kill stray processes on backend/frontend ports
5. Start frontend subprocess (`npm run dev -- --host 0.0.0.0`) unless `--no-frontend`
6. Start uvicorn on `0.0.0.0:8000` with `--workers N`
7. If `--tunnel`: start cloudflared
8. Trap signals → graceful shutdown of all children

#### `--provider` behavior

Sets three env vars before launching uvicorn:

| Provider | Env var validated |
|----------|------------------|
| `deepseek` | `DEEPSEEK_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `cerebras` | `CEREBRAS_API_KEY` |
| `sambanova` | `SAMBANOVA_API_KEY` |
| `siliconflow` | `SILICONFLOW_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `ollama` | — (no key needed) |

### `stop`

1. Read pid files from `logs/pids/` and kill processes
2. Port-scan `:8000` and `:5173` — kill anything found
3. Kill cloudflare tunnel if pid file exists
4. If launchd plists exist: `launchctl unload` them
5. `--remove-mysql`: `docker rm -f doctor-ai-mysql`

### `bootstrap`

Auto-detects platform and installs everything appropriate.

**Always (macOS + Linux):**
1. Create `.venv` if missing
2. `pip install --upgrade pip`
3. `pip install -r requirements.txt`
4. If `npm` is available: `npm install` in `frontend/web`

**Linux only (VM/prod):**
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

Single file: `/Volumes/ORICO/Code/doctor-ai-agent/cli.py` (project root, next to `dev.sh`).

### Dependencies

Zero new dependencies. Uses only stdlib: `argparse`, `subprocess`, `signal`, `os`, `sys`, `platform`, `shutil`, `time`, `json`, `pathlib`.

### Process management

- Child processes tracked in a list; `atexit` + signal handler kills them all
- Pid files written to `logs/pids/` for `stop` command
- `subprocess.Popen` for long-running children (uvicorn, vite, cloudflared)
- `subprocess.run` for short commands (lsof, kill, docker, brew, apt-get, npm install)

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
FRONTEND_DIR = APP_DIR / "frontend" / "web"
VENV_PYTHON = APP_DIR / ".venv" / "bin" / "python"
VENV_UVICORN = APP_DIR / ".venv" / "bin" / "uvicorn"
PID_DIR = APP_DIR / "logs" / "pids"
LOG_DIR = APP_DIR / "logs"
RUNTIME_JSON = APP_DIR / "config" / "runtime.json"
DEFAULT_PORT = 8000
FRONTEND_PORT = 5173
```

### launchd (macOS `--background`)

Generate `.plist` files to `~/Library/LaunchAgents/` — same behavior as current `dev.sh`. Only available on macOS; error on Linux if `--background` is used.

### Deprecation of `dev.sh`

Keep `dev.sh` temporarily with a one-liner:
```bash
#!/usr/bin/env bash
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

- Testing (`./dev.sh test`) — stays in `scripts/test.sh`
- Data management (`./dev.sh data`) — stays in `scripts/`
- Chat CLI (`./dev.sh chat`) — stays in `scripts/chat.py`
- DB inspection (`./dev.sh inspect-db`) — stays in `scripts/db_inspect.py`

## Migration

1. Build `cli.py` with all three commands
2. Replace `dev.sh` with deprecation shim
3. Update systemd service to use `cli.py start --prod`
4. Update `AGENTS.md` / `ARCHITECTURE.md` references
