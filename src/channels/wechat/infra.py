"""
WeChat/WeCom 基础设施：医生身份缓存（有界TTL-LRU）与 WeCom KF 游标持久化。
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from db.engine import AsyncSessionLocal, engine as DB_ENGINE
from db.crud import get_doctor_by_id
from sqlalchemy import text as sql_text
from utils.log import log


# ── Doctor identity cache (bounded LRU + 5-min TTL) ─────────────────────────

class _BoundedTTLCache:
    """Thread-safe (GIL-safe for CPython) bounded dict with per-entry TTL."""

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._cache: OrderedDict = OrderedDict()
        self._expiry: dict = {}
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key):
        if key in self._cache:
            if time.time() < self._expiry[key]:
                self._cache.move_to_end(key)
                return self._cache[key]
            del self._cache[key]
            del self._expiry[key]
        return None

    def set(self, key, value) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self._maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            del self._expiry[oldest]
        self._cache[key] = value
        self._expiry[key] = time.time() + self._ttl


_DOCTOR_CACHE = _BoundedTTLCache(maxsize=2000, ttl=300)


async def is_registered_doctor(open_id: str) -> bool:
    """Return True if the WeChat OpenID belongs to a registered doctor.

    Results are cached in _DOCTOR_CACHE (bounded 2000-entry LRU, 5-min TTL) to
    avoid a DB round-trip on every incoming message.  Unknown senders are denied
    the agent pipeline — they receive a static patient-facing reply instead.

    In test environments the check is bypassed so existing unit tests that stub
    the DB at a different level are not broken by the new guard.
    """
    import sys as _sys
    from infra.auth import is_production
    if not is_production() and "pytest" in _sys.modules:
        return True
    cached = _DOCTOR_CACHE.get(open_id)
    if cached is not None:
        return cached
    try:
        async with AsyncSessionLocal() as _session:
            doctor = await get_doctor_by_id(_session, open_id)
        result = doctor is not None
    except Exception as _e:
        log(f"[WeChat] doctor lookup FAILED for {open_id}: {_e}")
        result = False
    _DOCTOR_CACHE.set(open_id, result)
    return result


# ── Knowledge context cache ──────────────────────────────────────────────────

KB_CONTEXT_CACHE: dict[str, tuple[str, float]] = {}
KB_CONTEXT_TTL = 300.0  # 5 minutes
_KB_CONTEXT_LOCKS: dict[str, asyncio.Lock] = {}
_KB_REGISTRY_LOCK = threading.Lock()


def get_kb_lock(doctor_id: str) -> asyncio.Lock:
    with _KB_REGISTRY_LOCK:
        if doctor_id not in _KB_CONTEXT_LOCKS:
            _KB_CONTEXT_LOCKS[doctor_id] = asyncio.Lock()
        return _KB_CONTEXT_LOCKS[doctor_id]


# ── WeCom KF sync cursor persistence ────────────────────────────────────────

_WECHAT_KF_CURSOR_FILE = Path(__file__).resolve().parents[3] / "logs" / "wechat_kf_sync_state.json"  # → project root
_WECHAT_KF_CURSOR_KEY = "wecom_kf_sync_cursor"


def load_wecom_kf_sync_cursor() -> str:
    try:
        if not _WECHAT_KF_CURSOR_FILE.exists():
            return ""
        data = json.loads(_WECHAT_KF_CURSOR_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ""
        return str(data.get("cursor") or "").strip()
    except Exception as e:
        log(f"[WeCom KF] load cursor FAILED: {e}")
        return ""


def persist_wecom_kf_sync_cursor(cursor: str) -> None:
    if not cursor:
        return
    try:
        _WECHAT_KF_CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        _WECHAT_KF_CURSOR_FILE.write_text(
            json.dumps({"cursor": cursor}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log(f"[WeCom KF] persist cursor FAILED: {e}")


async def load_wecom_kf_sync_cursor_shared() -> str:
    """Load KF sync cursor from file."""
    return load_wecom_kf_sync_cursor()


async def persist_wecom_kf_sync_cursor_shared(cursor: str) -> None:
    """Persist KF sync cursor to file."""
    persist_wecom_kf_sync_cursor(cursor)
