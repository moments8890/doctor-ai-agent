"""Prompt loader — reads prompts from ``prompts/*.md`` files.

Each prompt lives in its own Markdown file.  The file stem is the key:
``get_prompt("structuring")`` reads ``prompts/structuring.md``.

Files are read once and cached in memory for the process lifetime.
Call ``invalidate()`` to clear the cache (e.g. after hot-reloading files).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "agent" / "prompts"
_cache: dict[str, str] = {}


async def get_prompt(key: str, fallback: str = "") -> str:
    """Return prompt text for *key* from ``prompts/{key}.md``.

    Falls back to *fallback* if the file does not exist (should not happen
    in a correctly deployed system).
    """
    if key in _cache:
        return _cache[key]

    path = _PROMPTS_DIR / f"{key}.md"
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        _cache[key] = text
        return text

    if fallback is not None:
        _cache[key] = fallback
        return fallback

    raise FileNotFoundError(f"Prompt file not found: {path}")


def get_prompt_sync(key: str, fallback: str = "") -> str:
    """Synchronous variant for use outside async contexts."""
    if key in _cache:
        return _cache[key]

    path = _PROMPTS_DIR / f"{key}.md"
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        _cache[key] = text
        return text

    if fallback is not None:
        _cache[key] = fallback
        return fallback

    raise FileNotFoundError(f"Prompt file not found: {path}")


def invalidate(key: Optional[str] = None) -> None:
    """Clear cached prompt(s).  Pass *key* to clear one, or omit to clear all."""
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)
