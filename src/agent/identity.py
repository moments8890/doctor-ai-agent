from __future__ import annotations

from contextvars import ContextVar

_current_identity: ContextVar[str] = ContextVar("current_identity")


def set_current_identity(identity: str) -> None:
    _current_identity.set(identity)


def get_current_identity() -> str:
    return _current_identity.get()
