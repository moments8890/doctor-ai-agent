"""Apply runtime config: push key/value pairs into os.environ."""
from __future__ import annotations

import os
from typing import Dict


async def apply_runtime_config(config: Dict[str, str]) -> None:
    """Save config to os.environ. Takes full effect on next restart."""
    for key, value in config.items():
        os.environ[key] = value
