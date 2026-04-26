"""Root conftest — runs first when pytest collects.

Two responsibilities, both at module-load time so they happen BEFORE any
app code (notably ``src/db/engine.py``) reads the environment:

1. Make ``src/`` importable.
2. Pin the database to a test-only path so tests can never pollute the
   dev ``patients.db``. Override allowed via ``PYTEST_DATABASE_URL`` for
   contributors who need a different test DB (e.g. CI temp dir), but
   never to a protected dev path.

The protected paths are also enforced by ``src/db/engine.py`` as a
backstop in case someone bypasses this conftest entirely (e.g. by
running a script that imports the engine directly).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# ─── 1. Make src/ importable ──────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ─── 2. Pin a test-only DB before any app code reads the env ──────────────

# Paths the dev server uses. Tests must NEVER bind here. Add new dev DB
# locations to this set if the runtime config grows more options.
PROTECTED_DEV_DB_PATHS = frozenset(
    {
        str((_REPO_ROOT / "patients.db").resolve()),
        str((_REPO_ROOT / "data" / "patients.db").resolve()),
    }
)

_TEST_DB_DEFAULT = _REPO_ROOT / ".pytest-data" / "patients.test.db"
_TEST_DB_DEFAULT.parent.mkdir(parents=True, exist_ok=True)


def _resolve_sqlite_path(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("sqlite"):
        return None
    if not parsed.path:
        return None
    return str(Path(parsed.path).expanduser().resolve())


# Honor PYTEST_DATABASE_URL when provided, but reject protected paths.
_user_url = os.environ.get("PYTEST_DATABASE_URL", "").strip()
if _user_url:
    _resolved = _resolve_sqlite_path(_user_url)
    if _resolved and _resolved in PROTECTED_DEV_DB_PATHS:
        raise SystemExit(
            f"REFUSED: PYTEST_DATABASE_URL resolves to a protected dev DB path:\n"
            f"  {_resolved}\n"
            f"Tests must use a separate file (default: {_TEST_DB_DEFAULT}). "
            f"Unset PYTEST_DATABASE_URL or point it at a different file."
        )
    _chosen_url = _user_url
    _chosen_path = Path(_resolved) if _resolved else _TEST_DB_DEFAULT
else:
    _chosen_url = f"sqlite+aiosqlite:///{_TEST_DB_DEFAULT}"
    _chosen_path = _TEST_DB_DEFAULT

# Override env for the rest of the test run. ``ENVIRONMENT=test`` is
# what ``src/db/engine.py`` checks for the backstop guard, and what
# ``services/auth/request_auth.py`` honors for the dev fallback path.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = _chosen_url
os.environ["PATIENTS_DB_PATH"] = str(_chosen_path)
