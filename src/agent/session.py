"""Session management — plain dict history, no LangChain."""
from __future__ import annotations

from typing import Dict, List

MAX_HISTORY_TURNS = 50  # keep last 50 turns (100 messages)

# In-memory session store: identity → list of {role, content} dicts
_sessions: Dict[str, List[Dict[str, str]]] = {}


def get_session_history(identity: str) -> List[Dict[str, str]]:
    """Return chat history for the given identity."""
    return list(_sessions.get(identity, []))


def append_to_history(identity: str, user_text: str, assistant_reply: str) -> None:
    """Append a turn (user + assistant) to session history."""
    if identity not in _sessions:
        _sessions[identity] = []
    history = _sessions[identity]
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": assistant_reply})
    # Trim to max
    max_messages = MAX_HISTORY_TURNS * 2
    if len(history) > max_messages:
        _sessions[identity] = history[-max_messages:]


def clear_session(identity: str) -> None:
    """Clear session history (new conversation)."""
    _sessions.pop(identity, None)
