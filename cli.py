#!/usr/bin/env python3
"""cli.py -- Unified entry point for doctor-ai-agent (dev + production).

Usage:
    ./cli.py start [--prod] [--provider P] [--host H] [--port N] ...
    ./cli.py stop  [--remove-mysql]
    ./cli.py bootstrap [--vm]
    ./cli.py -h
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR / "src"
FRONTEND_DIR = APP_DIR / "frontend" / "web"
VENV_DIR = APP_DIR / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
VENV_UVICORN = VENV_DIR / "bin" / "uvicorn"
PID_DIR = APP_DIR / "logs" / "pids"
LOG_DIR = APP_DIR / "logs"
RUNTIME_JSON = APP_DIR / "config" / "runtime.json"
RUNTIME_SAMPLE = APP_DIR / "config" / "runtime.json.sample"

DEFAULT_PORT = 8000
FRONTEND_PORT = 5173

LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
PLIST_UV = LAUNCH_AGENTS_DIR / "com.aiagent.uvicorn.plist"
PLIST_FE = LAUNCH_AGENTS_DIR / "com.aiagent.frontend.plist"
LOG_UV = Path.home() / "Library" / "Logs" / "ai-agent-uvicorn.log"
LOG_FE = Path.home() / "Library" / "Logs" / "ai-agent-frontend.log"
FRONTEND_LOG = LOG_DIR / "frontend.log"

IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
IS_TTY = sys.stdout.isatty()

PROVIDERS = [
    "ollama", "deepseek", "groq", "cerebras", "sambanova",
    "siliconflow", "openrouter", "tencent_lkeap", "openai",
]

PROVIDER_KEY_MAP = {
    "deepseek": "DEEPSEEK_API_KEY",
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "sambanova": "SAMBANOVA_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "tencent_lkeap": "TENCENT_LKEAP_API_KEY",
    "openai": "OPENAI_API_KEY",
}

MYSQL_DEFAULTS = {
    "container": "doctor-ai-mysql",
    "root_password": "DrAI_Root_2026!x9",
    "database": "doctor_ai",
    "user": "doctor_ai",
    "password": "DrAI_App_2026!x9",
}

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"


def _c(color: str, msg: str) -> str:
    if not IS_TTY:
        return msg
    return f"{color}{msg}{NC}"


def ok(msg: str) -> None:
    print(_c(GREEN, f"  \u2713 {msg}"))


def warn(msg: str) -> None:
    print(_c(YELLOW, f"  \u26a0 {msg}"))


def fail(msg: str) -> None:
    print(_c(RED, f"  \u2717 {msg}"))


def info(msg: str) -> None:
    print(f"  \u2192 {msg}")


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

_children: List[subprocess.Popen] = []


def _kill_children() -> None:
    for proc in _children:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


atexit.register(_kill_children)


def _signal_handler(sig: int, frame: object) -> None:
    _kill_children()
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def _spawn(cmd: List[str], env: Optional[dict] = None,
           cwd: Optional[Path] = None, log_file: Optional[Path] = None,
           pid_label: Optional[str] = None) -> subprocess.Popen:
    """Spawn a long-running subprocess and track it."""
    kwargs: dict = {"env": env or os.environ.copy()}
    if cwd:
        kwargs["cwd"] = str(cwd)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = open(log_file, "a")
        kwargs["stdout"] = fh
        kwargs["stderr"] = fh
    proc = subprocess.Popen(cmd, **kwargs)
    _children.append(proc)
    if pid_label:
        PID_DIR.mkdir(parents=True, exist_ok=True)
        (PID_DIR / f"{pid_label}.pid").write_text(str(proc.pid))
    return proc


def _detach_spawn(cmd: List[str], env: Optional[dict] = None,
                  cwd: Optional[Path] = None, log_file: Optional[Path] = None,
                  pid_label: Optional[str] = None) -> subprocess.Popen:
    """Spawn a subprocess that survives the parent exiting (nohup/setsid style).

    Uses start_new_session=True so SIGHUP to the terminal's process group
    doesn't reach the child. Stdin is detached from /dev/null; stdout and
    stderr go to the log file (or /dev/null if not given). The child is
    NOT added to _children, so atexit/_kill_children leaves it alone.
    """
    kwargs: dict = {
        "env": env or os.environ.copy(),
        "start_new_session": True,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if cwd:
        kwargs["cwd"] = str(cwd)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = open(log_file, "a")
        kwargs["stdout"] = fh
        kwargs["stderr"] = fh
    else:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    proc = subprocess.Popen(cmd, **kwargs)
    if pid_label:
        PID_DIR.mkdir(parents=True, exist_ok=True)
        (PID_DIR / f"{pid_label}.pid").write_text(str(proc.pid))
    return proc


def _kill_port(port: int) -> None:
    """Kill any process listening on the given port."""
    if IS_MACOS:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True,
        )
        pids = result.stdout.strip()
    else:
        # Linux: use ss + extract pid
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True,
        )
        pids_found = re.findall(r"pid=(\d+)", result.stdout)
        pids = "\n".join(pids_found)

    if pids:
        for pid in pids.strip().split("\n"):
            pid = pid.strip()
            if pid:
                subprocess.run(["kill", "-9", pid],
                               capture_output=True)


def _kill_pid_file(label: str) -> bool:
    """Kill process from a pid file. Returns True if a live process was killed.

    Tries the process group first (handles detach-spawned children that set
    their own session), falls back to the individual pid if the group kill
    fails. Silently cleans up stale pid files where the process is gone.
    """
    pid_file = PID_DIR / f"{label}.pid"
    if not pid_file.exists():
        return False
    raw = pid_file.read_text().strip()
    pid_file.unlink(missing_ok=True)
    if not raw:
        return False
    try:
        pid = int(raw)
    except ValueError:
        return False

    killed = False
    try:
        os.killpg(pid, signal.SIGTERM)
        killed = True
    except ProcessLookupError:
        pass  # group doesn't exist (or pid was never a group leader)
    except PermissionError:
        pass  # fall through to individual kill

    if not killed:
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except ProcessLookupError:
            pass
    return killed


def _wait_http(url: str, label: str, timeout: int = 20) -> bool:
    """Poll an HTTP endpoint until it responds 200."""
    info(f"Waiting for {label}...")
    for i in range(timeout):
        try:
            result = subprocess.run(
                ["curl", "-sf", url],
                capture_output=True, timeout=3,
            )
            if result.returncode == 0:
                ok(f"{label} healthy: {url}")
                return True
        except subprocess.TimeoutExpired:
            pass
        if i == timeout - 1:
            fail(f"{label} did not start within {timeout}s")
            return False
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# runtime.json helpers
# ---------------------------------------------------------------------------

def _load_runtime() -> dict:
    """Load runtime.json, return the parsed dict."""
    if not RUNTIME_JSON.exists():
        return {}
    with open(RUNTIME_JSON) as f:
        return json.load(f)


def _save_runtime(cfg: dict) -> None:
    """Save runtime.json."""
    RUNTIME_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_JSON, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _runtime_get(cfg: dict, key: str) -> str:
    """Read a value from the nested runtime.json structure."""
    for cat in cfg.get("categories", {}).values():
        settings = cat.get("settings", {})
        if key in settings:
            return str(settings[key].get("value", ""))
    return ""


def _runtime_set(cfg: dict, key: str, value: object) -> None:
    """Write a value into the nested runtime.json structure."""
    for cat in cfg.get("categories", {}).values():
        settings = cat.get("settings", {})
        if key in settings:
            settings[key]["value"] = value
            return


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

def _check_ollama(cfg: dict) -> None:
    """Check Ollama endpoint and model availability (dev mode)."""
    base_url = _runtime_get(cfg, "OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    model = _runtime_get(cfg, "OLLAMA_MODEL") or "qwen3.5:9b"
    # Derive host from URL
    host_match = re.search(r"https?://([^/:]+)", base_url)
    host = host_match.group(1) if host_match else "localhost"
    is_local = host in ("localhost", "127.0.0.1")
    tags_url = re.sub(r"/v1/?$", "", base_url) + "/api/tags"

    if is_local:
        info(f"OLLAMA_BASE_URL points to local host ({base_url})")
        # Check if ollama is running
        result = subprocess.run(
            ["pgrep", "-x", "ollama"], capture_output=True,
        )
        if result.returncode != 0:
            if IS_MACOS and shutil.which("brew"):
                warn("Ollama not running locally -- starting via brew services...")
                subprocess.run(["brew", "services", "start", "ollama"],
                               capture_output=True)
                time.sleep(3)
            elif IS_MACOS:
                warn("Ollama not running and brew not found -- please start Ollama manually")
            else:
                warn("Ollama not running -- please start it manually")
    else:
        info(f"Using LAN Ollama endpoint: {base_url}")

    # Check endpoint reachability
    result = subprocess.run(
        ["curl", "-sf", tags_url], capture_output=True, text=True,
    )
    if result.returncode == 0:
        ok(f"Ollama endpoint reachable: {tags_url}")
        # Check model availability
        model_base = model.split(":")[0]
        if model_base in result.stdout:
            ok(f"Model '{model}' available on configured endpoint")
        elif is_local:
            warn(f"Model '{model}' not found locally -- pulling (this may take a while)...")
            subprocess.run(["ollama", "pull", model])
            ok(f"Model '{model}' pulled")
        else:
            warn(f"Model '{model}' not listed on LAN endpoint; skipping local pull")
    else:
        warn(f"Ollama endpoint not reachable: {tags_url} (LLM features will be unavailable)")


# ---------------------------------------------------------------------------
# Cloudflare tunnel
# ---------------------------------------------------------------------------

def _start_tunnel(port: int) -> Optional[subprocess.Popen]:
    """Start a cloudflared quick tunnel."""
    if not shutil.which("cloudflared"):
        warn("cloudflared not found -- skipping tunnel")
        return None
    tunnel_log = LOG_DIR / "tunnel.log"
    proc = _spawn(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
        log_file=tunnel_log,
        pid_label="tunnel",
    )
    # Wait for URL to appear in log
    url = ""
    for _ in range(30):
        time.sleep(1)
        if tunnel_log.exists():
            content = tunnel_log.read_text()
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
            if match:
                url = match.group(0)
                break
    if url:
        info(f"Tunnel     : {url}")
        info(f"WeCom URL  : {url}/wechat")
    else:
        info(f"Tunnel     : started (URL not yet available -- check {tunnel_log})")
    return proc


# ---------------------------------------------------------------------------
# launchd helpers (macOS only)
# ---------------------------------------------------------------------------

def _sweep_legacy_launchd_agents() -> None:
    """Unload + remove any legacy com.aiagent.* plists this script ever wrote.

    Older versions of cli.py used launchd for --background. launchd agents run
    under TCC sandboxing that can't reach /Volumes/ORICO where this repo lives,
    so they crash-loop on every login. Clean them up when the user opts into
    background mode so they stop contributing noise.
    """
    for plist_path in (PLIST_UV, PLIST_FE):
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)],
                           capture_output=True)
            plist_path.unlink(missing_ok=True)


def _write_uvicorn_plist(port: int) -> None:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.aiagent.uvicorn</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "{SRC_DIR}" &amp;&amp; exec "{VENV_UVICORN}" main:app --host 127.0.0.1 --port {port}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{LOG_UV}</string>
  <key>StandardErrorPath</key>
  <string>{LOG_UV}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>{SRC_DIR}</string>
    <key>ENVIRONMENT</key>
    <string>development</string>
  </dict>
</dict>
</plist>"""
    PLIST_UV.write_text(plist)


def _write_frontend_plist(npm_bin: str, port: int, *, use_v2: bool = False) -> None:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.aiagent.frontend</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "{FRONTEND_DIR}" &amp;&amp; {"VITE_USE_V2=true " if use_v2 else ""}exec "{npm_bin}" run dev -- --host 127.0.0.1 --port {port}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{LOG_FE}</string>
  <key>StandardErrorPath</key>
  <string>{LOG_FE}</string>
</dict>
</plist>"""
    PLIST_FE.write_text(plist)


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------

def _mysql_container_name() -> str:
    return os.environ.get("MYSQL_CONTAINER", MYSQL_DEFAULTS["container"])


def _wait_mysql(timeout: int = 80) -> bool:
    """Wait for MySQL Docker container to be healthy."""
    container = _mysql_container_name()
    info(f"Waiting for MySQL container '{container}'...")
    for i in range(0, timeout, 2):
        result = subprocess.run(
            ["docker", "inspect", "-f",
             "{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}",
             container],
            capture_output=True, text=True,
        )
        status = result.stdout.strip()
        if status in ("healthy", "running"):
            ok(f"MySQL container '{container}' is {status}")
            return True
        if i + 2 >= timeout:
            fail(f"MySQL container failed to become healthy within {timeout}s")
            return False
        time.sleep(2)
    return False


def _start_mysql_container() -> None:
    """Start MySQL container if not running, or create it."""
    container = _mysql_container_name()
    root_pw = os.environ.get("MYSQL_ROOT_PASSWORD", MYSQL_DEFAULTS["root_password"])
    database = os.environ.get("MYSQL_DATABASE", MYSQL_DEFAULTS["database"])
    user = os.environ.get("MYSQL_USER", MYSQL_DEFAULTS["user"])
    password = os.environ.get("MYSQL_PASSWORD", MYSQL_DEFAULTS["password"])

    # Check if container already exists
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True,
    )
    if container in result.stdout.strip().split("\n"):
        subprocess.run(["docker", "start", container], capture_output=True)
        ok(f"MySQL container '{container}' started")
        return

    info(f"Creating MySQL container '{container}'...")
    subprocess.run([
        "docker", "run", "-d",
        "--name", container,
        "--restart", "unless-stopped",
        "-e", f"MYSQL_ROOT_PASSWORD={root_pw}",
        "-e", f"MYSQL_DATABASE={database}",
        "-e", f"MYSQL_USER={user}",
        "-e", f"MYSQL_PASSWORD={password}",
        "-p", "127.0.0.1:3306:3306",
        "-v", "doctor_ai_mysql_data:/var/lib/mysql",
        "mysql:8.0",
        "--default-authentication-plugin=mysql_native_password",
        "--character-set-server=utf8mb4",
        "--collation-server=utf8mb4_unicode_ci",
    ], check=True)
    ok(f"MySQL container '{container}' created")


# ---------------------------------------------------------------------------
# Validate runtime.json (prod mode)
# ---------------------------------------------------------------------------

def _validate_runtime_prod(cfg: dict) -> bool:
    """Validate runtime.json has required keys for production."""
    errors = []
    db_url = _runtime_get(cfg, "DATABASE_URL")
    if not db_url:
        errors.append("DATABASE_URL is empty -- set it in config/runtime.json")

    # Check at least one LLM provider key is set
    has_key = False
    for env_key in PROVIDER_KEY_MAP.values():
        val = _runtime_get(cfg, env_key)
        if val:
            has_key = True
            break
    if not has_key:
        errors.append("No LLM provider API key is set in config/runtime.json")

    for e in errors:
        fail(e)
    return len(errors) == 0


# ---------------------------------------------------------------------------
# Command: start
# ---------------------------------------------------------------------------

def cmd_start(args: argparse.Namespace) -> None:
    is_prod = args.prod
    provider = args.provider
    host = args.host or ("0.0.0.0" if is_prod else "127.0.0.1")
    port = args.port or DEFAULT_PORT
    workers = args.workers or 1
    do_reload = args.reload
    no_frontend = args.no_frontend
    background = args.background
    tunnel = args.tunnel
    menu = args.menu
    use_v2 = args.v2

    mode_label = "production" if is_prod else "development"
    env_name = "production" if is_prod else "development"
    reload_label = " (--reload)" if do_reload else " (no auto-reload)"

    print()
    print("=" * 54)
    print(f"  Doctor AI Agent -- {mode_label} startup")
    if not is_prod:
        if background:
            print("  Mode: background (detached via setsid)")
        else:
            print(f"  Mode: foreground{reload_label}")
    else:
        print(f"  Mode: production (workers={workers})")
    print("=" * 54)
    print()

    # --- Pre-flight checks ---
    print("[1/4] Checking Python environment...")
    if not VENV_UVICORN.exists():
        fail(f"Missing {VENV_UVICORN}. Run: ./cli.py bootstrap")
        sys.exit(1)
    ok(f"uvicorn binary: {VENV_UVICORN}")

    # --- Provider validation ---
    cfg = _load_runtime()
    if provider and provider != "ollama":
        env_key = PROVIDER_KEY_MAP.get(provider)
        if env_key:
            # Check env var first, then runtime.json
            key_val = os.environ.get(env_key) or _runtime_get(cfg, env_key)
            if not key_val:
                fail(f"{env_key} not set. Add it to config/runtime.json or export it.")
                sys.exit(1)
        ok(f"Provider: {provider}")
    elif provider == "ollama" or not provider:
        provider = provider or "ollama"

    # --- Frontend check ---
    npm_bin = shutil.which("npm")
    want_frontend = not no_frontend
    if want_frontend:
        if not FRONTEND_DIR.exists():
            warn(f"Frontend directory missing: {FRONTEND_DIR}; skipping")
            want_frontend = False
        elif not npm_bin:
            warn("npm not found; skipping frontend")
            want_frontend = False
        else:
            ok(f"npm: {npm_bin}")

    # --- Runtime config ---
    print()
    print("[2/4] Checking configuration...")

    if is_prod:
        if not RUNTIME_JSON.exists():
            fail(f"Missing {RUNTIME_JSON}. Copy from {RUNTIME_SAMPLE} and configure.")
            sys.exit(1)
        if not _validate_runtime_prod(cfg):
            sys.exit(1)
        ok("runtime.json validated")

        # Patch provider into runtime.json if specified
        if provider:
            _runtime_set(cfg, "ROUTING_LLM", provider)
            _runtime_set(cfg, "STRUCTURING_LLM", provider)
            _runtime_set(cfg, "CONVERSATION_LLM", provider)
            _save_runtime(cfg)
            info(f"Patched runtime.json: ROUTING/STRUCTURING/CONVERSATION_LLM={provider}")

        # MySQL health check
        print()
        print("[3/4] Checking MySQL...")
        if shutil.which("docker"):
            container = _mysql_container_name()
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Names}}"],
                capture_output=True, text=True,
            )
            if container in result.stdout.strip().split("\n"):
                subprocess.run(["docker", "start", container], capture_output=True)
                if not _wait_mysql():
                    sys.exit(1)
            else:
                warn(f"MySQL container '{container}' not found -- skipping health check")
        else:
            info("docker not found -- skipping MySQL health check")
    else:
        # Dev mode: Ollama check
        print()
        print("[3/4] Checking LLM endpoint...")
        if provider == "ollama":
            _check_ollama(cfg)
        else:
            info(f"Using cloud provider: {provider}")

    # --- Kill stray processes ---
    print()
    print("[4/4] Starting services...")
    _kill_port(port)
    if want_frontend:
        _kill_port(FRONTEND_PORT)

    # --- Build environment ---
    env = os.environ.copy()
    pythonpath = str(SRC_DIR)
    if env.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}:{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath
    env["ENVIRONMENT"] = env_name
    if provider:
        env["ROUTING_LLM"] = provider
        env["STRUCTURING_LLM"] = provider
        env["CONVERSATION_LLM"] = provider

    # --- Background mode: nohup/setsid-style detach on every platform ---
    #
    # Previously this used macOS launchd, but launchd agents don't have the
    # user shell's file-access permissions (TCC). Anything under /Volumes/
    # fails with Operation not permitted on pyvenv.cfg. The detach path works
    # everywhere because the setsid child inherits the spawning shell's
    # permissions. launchd KeepAlive is not valuable enough to justify the
    # platform surface area; if we want auto-restart later, we'd use a real
    # supervisor (systemd on Linux, or a tiny watchdog here).
    if background:
        # Sweep any stale launchd agents from earlier versions of this script
        # so they stop crash-looping on every login.
        if IS_MACOS:
            _sweep_legacy_launchd_agents()

        uv_log = LOG_DIR / "uvicorn.log"
        uv_cmd = [
            str(VENV_UVICORN), "main:app",
            "--host", host,
            "--port", str(port),
        ]
        if do_reload:
            uv_cmd.append("--reload")
        if workers > 1:
            uv_cmd.extend(["--workers", str(workers)])
        info(f"Detaching uvicorn on :{port} (log: {uv_log})")
        _detach_spawn(uv_cmd, env=env, cwd=SRC_DIR,
                      log_file=uv_log, pid_label="backend")
        _wait_http(f"http://127.0.0.1:{port}/", "uvicorn", timeout=20)

        if want_frontend:
            node_modules = FRONTEND_DIR / "node_modules"
            if not node_modules.exists():
                info("Installing frontend deps...")
                subprocess.run([npm_bin, "install"], cwd=str(FRONTEND_DIR),
                               env=env, check=True)
            fe_env = env.copy()
            if use_v2:
                fe_env["VITE_USE_V2"] = "true"
            if not do_reload:
                fe_env["VITE_NO_HMR"] = "1"
            info(f"Detaching frontend on :{FRONTEND_PORT} (log: {FRONTEND_LOG})")
            _detach_spawn(
                [npm_bin, "run", "dev", "--",
                 "--host", host, "--port", str(FRONTEND_PORT)],
                env=fe_env, cwd=FRONTEND_DIR,
                log_file=FRONTEND_LOG, pid_label="frontend",
            )
            _wait_http(f"http://127.0.0.1:{FRONTEND_PORT}/", "frontend", timeout=35)

        if tunnel:
            tunnel_log = LOG_DIR / "tunnel.log"
            if shutil.which("cloudflared"):
                info(f"Detaching cloudflared tunnel (log: {tunnel_log})")
                _detach_spawn(
                    ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
                    log_file=tunnel_log, pid_label="tunnel",
                )
            else:
                warn("cloudflared not found -- skipping tunnel")
        if menu:
            _do_menu(port)

        print()
        print("=" * 54)
        ok("Running in background -- safe to close terminal / disconnect SSH")
        print("=" * 54)
        _print_urls(host, port, want_frontend, background=True)
        return

    # --- Foreground mode ---
    fe_env = env.copy()
    if use_v2:
        fe_env["VITE_USE_V2"] = "true"
        info("Frontend: antd-mobile v2 UI enabled")
    if want_frontend:
        node_modules = FRONTEND_DIR / "node_modules"
        if not node_modules.exists():
            info("Installing frontend deps...")
            subprocess.run([npm_bin, "install"], cwd=str(FRONTEND_DIR),
                           env=env, check=True)
        if not do_reload:
            fe_env["VITE_NO_HMR"] = "1"
        fe_host = host
        info(f"Starting frontend on :{FRONTEND_PORT}...")
        _spawn(
            [npm_bin, "run", "dev", "--", "--host", fe_host, "--port", str(FRONTEND_PORT)],
            env=fe_env,
            cwd=FRONTEND_DIR,
            log_file=FRONTEND_LOG,
            pid_label="frontend",
        )
        _wait_http(f"http://127.0.0.1:{FRONTEND_PORT}/", "frontend", timeout=35)

    if tunnel:
        _start_tunnel(port)
    if menu:
        _do_menu(port)

    print()
    print("=" * 54)
    ok(f"Starting uvicorn -- Ctrl+C to stop")
    print("=" * 54)
    _print_urls(host, port, want_frontend)

    # Build uvicorn command
    uv_cmd = [
        str(VENV_UVICORN), "main:app",
        "--host", host,
        "--port", str(port),
    ]
    if do_reload:
        uv_cmd.append("--reload")
    if workers > 1:
        uv_cmd.extend(["--workers", str(workers)])

    # exec into uvicorn (replaces this process)
    os.chdir(str(SRC_DIR))
    os.execve(str(VENV_UVICORN), uv_cmd, env)


def _do_menu(port: int) -> None:
    """POST to /wechat/menu once the server is up."""
    url = f"http://127.0.0.1:{port}/"
    if _wait_http(url, "server (for menu)", timeout=20):
        result = subprocess.run(
            ["curl", "-sf", "-X", "POST", f"http://127.0.0.1:{port}/wechat/menu"],
            capture_output=True, text=True,
        )
        if '"ok"' in result.stdout:
            ok("WeChat menu created")
        else:
            warn(f"Menu response: {result.stdout.strip()}")


def _print_urls(host: str, port: int, want_frontend: bool,
                background: bool = False) -> None:
    """Print local URLs grouped to mirror the prod subdomain layout.

    Each prod subdomain has a local equivalent so devs can find pages
    without having to reverse-engineer the nginx vhost configs.
    See deploy/tencent/nginx/*.conf for the prod side.
    """
    fe = f"http://127.0.0.1:{FRONTEND_PORT}"
    api = f"http://127.0.0.1:{port}"
    print()
    print("  Subdomains (prod ↔ local)")
    if want_frontend:
        print(f"    app.*    →  {fe}/                       (doctor + patient app)")
        print(f"    admin.*  →  {fe}/admin                  (admin dashboard)")
        print(f"    wiki.*   →  {fe}/wiki/wiki.html         (public wiki)")
        print(f"    docs.*   →  {fe}/wiki/docs.html         (public docs)")
    print(f"    api.*    →  {api}                       (FastAPI backend)")
    print()
    print("  Backend tools")
    print(f"    WeChat       : {api}/wechat")
    print(f"    Debug        : {api}/debug")
    print(f"    API Docs     : {api}/docs   (FastAPI Swagger)")
    print()
    if want_frontend:
        print(f"  FE log     : tail -f {FRONTEND_LOG}")
    if background:
        print(f"  API log    : tail -f {LOG_DIR / 'uvicorn.log'}")
        print(f"  Stop       : ./cli.py stop")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Command: stop
# ---------------------------------------------------------------------------

def cmd_stop(args: argparse.Namespace) -> None:
    print()
    info("Stopping services...")

    # launchd (macOS)
    if IS_MACOS:
        if PLIST_UV.exists():
            r = subprocess.run(["launchctl", "unload", str(PLIST_UV)],
                               capture_output=True)
            if r.returncode == 0:
                ok("uvicorn launchd service stopped")
            else:
                info("uvicorn launchd service was not running")
        if PLIST_FE.exists():
            r = subprocess.run(["launchctl", "unload", str(PLIST_FE)],
                               capture_output=True)
            if r.returncode == 0:
                ok("frontend launchd service stopped")
            else:
                info("frontend launchd service was not running")

    # Pid files
    _kill_pid_file("backend")
    _kill_pid_file("frontend")
    _kill_pid_file("tunnel")
    _kill_pid_file("caffeinate")

    # Port cleanup
    _kill_port(DEFAULT_PORT)
    _kill_port(FRONTEND_PORT)

    # caffeinate (macOS)
    if IS_MACOS:
        subprocess.run(["pkill", "-f", "caffeinate.*cli"],
                       capture_output=True)

    # MySQL
    if args.remove_mysql:
        container = _mysql_container_name()
        if shutil.which("docker"):
            subprocess.run(["docker", "rm", "-f", container],
                           capture_output=True)
            ok(f"MySQL container '{container}' removed")
        else:
            warn("docker not found -- cannot remove MySQL container")

    ok("All services stopped.")
    print()


# ---------------------------------------------------------------------------
# Command: bootstrap
# ---------------------------------------------------------------------------

def cmd_bootstrap(args: argparse.Namespace) -> None:
    is_vm = args.vm

    print()
    print("=" * 54)
    print("  Doctor AI Agent -- bootstrap")
    print("=" * 54)
    print()

    # --- VM: system packages ---
    if is_vm:
        if not IS_LINUX:
            warn("--vm is intended for Linux hosts; skipping system package install on this platform")
        elif shutil.which("apt-get"):
            info("Installing system packages...")
            sudo = ["sudo"] if shutil.which("sudo") else []
            subprocess.run(
                [*sudo, "apt-get", "update"],
                check=True,
            )
            subprocess.run(
                [*sudo, "apt-get", "install", "-y",
                 "ca-certificates", "curl", "git",
                 "python3", "python3-venv", "python3-pip",
                 "ffmpeg", "nodejs", "npm"],
                check=True,
            )
            ok("System packages installed")

            # Docker
            if not shutil.which("docker"):
                info("Installing Docker...")
                subprocess.run(
                    "curl -fsSL https://get.docker.com | sh",
                    shell=True, check=True,
                )
                ok("Docker installed")

            # Add user to docker group
            user = os.environ.get("USER", "ubuntu")
            subprocess.run(
                [*sudo, "usermod", "-aG", "docker", user],
                capture_output=True,
            )
        else:
            fail("Unsupported package manager. Install python3-venv/python3-pip/git/curl/ffmpeg manually.")
            sys.exit(1)

    # --- Python venv ---
    print()
    info("Setting up Python environment...")
    if not VENV_DIR.exists():
        info("Creating virtual environment...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            check=True,
        )
        ok("Virtual environment created")
    else:
        ok(f"Virtual environment exists: {VENV_DIR}")

    python = str(VENV_PYTHON)
    subprocess.run([python, "-m", "pip", "install", "--upgrade", "pip"],
                   capture_output=True, check=True)
    ok("pip upgraded")

    info("Installing Python dependencies...")
    subprocess.run(
        [python, "-m", "pip", "install", "-r", str(APP_DIR / "requirements.txt")],
        check=True,
    )
    ok("Python dependencies installed")

    # --- Frontend ---
    npm_bin = shutil.which("npm")
    if npm_bin and FRONTEND_DIR.exists():
        print()
        info("Installing frontend dependencies...")
        subprocess.run([npm_bin, "install"], cwd=str(FRONTEND_DIR), check=True)
        ok("Frontend dependencies installed")
    elif not npm_bin:
        info("npm not found -- skipping frontend deps")
    elif not FRONTEND_DIR.exists():
        info(f"Frontend directory not found ({FRONTEND_DIR}) -- skipping")

    # --- VM: MySQL container ---
    if is_vm and shutil.which("docker"):
        print()
        info("Setting up MySQL container...")
        _start_mysql_container()

    print()
    ok("Bootstrap complete!")
    print()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Doctor AI Agent -- unified entry point (dev + production)",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- start ---
    p_start = sub.add_parser("start", help="Start backend and frontend services")
    p_start.add_argument("--prod", action="store_true",
                         help="Production mode (0.0.0.0, preflight checks, MySQL health)")
    p_start.add_argument("--provider", choices=PROVIDERS, default=None,
                         help="LLM provider (sets ROUTING/STRUCTURING/CONVERSATION_LLM)")
    p_start.add_argument("--host", default=None,
                         help="Bind address (default: 127.0.0.1 dev, 0.0.0.0 prod)")
    p_start.add_argument("--port", type=int, default=None,
                         help=f"Backend port (default: {DEFAULT_PORT})")
    p_start.add_argument("--workers", type=int, default=None,
                         help="Uvicorn worker count (default: 1)")
    p_start.add_argument("--reload", action="store_true",
                         help="Enable auto-reload on file change")
    p_start.add_argument("--no-frontend", action="store_true",
                         help="Skip Vite frontend dev server")
    p_start.add_argument("--background", action="store_true",
                         help="Detach from terminal (setsid + redirected stdio). "
                              "Safe to close terminal or disconnect SSH.")
    p_start.add_argument("--v2", action="store_true",
                         help="Use antd-mobile v2 frontend (VITE_USE_V2=true)")
    p_start.add_argument("--tunnel", action="store_true",
                         help="Start Cloudflare quick tunnel")
    p_start.add_argument("--menu", action="store_true",
                         help="Create/update WeChat menu after startup")

    # --- stop ---
    p_stop = sub.add_parser("stop", help="Stop all running services")
    p_stop.add_argument("--remove-mysql", action="store_true",
                        help="Also remove MySQL Docker container")

    # --- bootstrap ---
    p_boot = sub.add_parser("bootstrap", help="Install project dependencies")
    p_boot.add_argument("--vm", action="store_true",
                        help="VM/production mode: also install system packages, Docker, MySQL")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "bootstrap":
        cmd_bootstrap(args)


if __name__ == "__main__":
    main()
