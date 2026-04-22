"""Guard against silent drift between production prompts and eval wrappers.

Before this test existed, `tests/prompts/wrappers/*.md` were hand-copies of
`src/agent/prompts/**/*.md`. Someone would edit the source prompt, forget to
mirror the change to the wrapper, and the eval harness (which reads the
wrapper) would keep running the stale copy. This test runs the sync script
in --check mode, failing if any wrapper diverges from what would be
generated from source today.

To resolve a drift failure:
    scripts/sync_eval_wrappers.py --diff       # inspect the drift
    scripts/sync_eval_wrappers.py --write      # regenerate wrappers
    pytest tests/test_eval_wrappers_in_sync.py # confirm green
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_eval_wrappers_match_source_prompts():
    script = ROOT / "scripts" / "sync_eval_wrappers.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        raise AssertionError(
            "Eval wrappers are out of sync with source prompts.\n"
            "Run: scripts/sync_eval_wrappers.py --write\n\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
