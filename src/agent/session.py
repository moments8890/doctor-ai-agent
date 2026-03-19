"""Agent-per-session model with in-memory conversation history."""
from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import AIMessage, HumanMessage

from agent.setup import get_agent

MAX_HISTORY = 100  # keep last 100 turns (200 messages)


class SessionAgent:
    """Persistent agent instance per doctor/patient session."""

    def __init__(self, identity: str, role: str) -> None:
        self.identity = identity
        self.role = role
        self.agent = get_agent(role)
        self.history: List = []

    async def handle(self, text: str) -> str:
        # Append human message BEFORE invoke so tools that scan
        # history (e.g. _create_pending_record) can see the current turn.
        self.history.append(HumanMessage(content=text))

        result = await self.agent.ainvoke(
            {"messages": self.history},
            config={"recursion_limit": 25},  # ~10 tool-calling iterations
        )
        # LangGraph returns {"messages": [...all messages...]}
        reply_messages = result.get("messages", [])
        reply = ""
        if reply_messages:
            last = reply_messages[-1]
            reply = last.content if hasattr(last, "content") else str(last)

        # Only append AI reply (human already added above)
        self.history.append(AIMessage(content=reply))
        self._trim_history()
        return reply

    def _add_turn(self, text: str, reply: str) -> None:
        """Add a turn from fast-path (human message may already be in history)."""
        if not self.history or not isinstance(self.history[-1], HumanMessage) \
           or self.history[-1].content != text:
            self.history.append(HumanMessage(content=text))
        self.history.append(AIMessage(content=reply))
        self._trim_history()

    def _trim_history(self) -> None:
        if len(self.history) > MAX_HISTORY * 2:
            self.history = self.history[-(MAX_HISTORY * 2):]


_agents: Dict[str, SessionAgent] = {}


async def _bootstrap_history(identity: str) -> List:
    """Load recent archived turns from DB to bootstrap agent history on restart."""
    try:
        from agent.archive import get_recent_turns
        turns = await get_recent_turns(identity)
        messages: List = []
        for turn in turns:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        return messages
    except Exception:
        return []


def clear_session(identity: str) -> bool:
    """Clear agent session + history. Returns True if session existed."""
    return _agents.pop(identity, None) is not None


def clear_all_sessions() -> int:
    """Clear all agent sessions. Returns count cleared."""
    count = len(_agents)
    _agents.clear()
    return count


async def get_or_create_agent(identity: str, role: str) -> SessionAgent:
    if identity not in _agents:
        agent = SessionAgent(identity, role)
        agent.history = await _bootstrap_history(identity)
        _agents[identity] = agent
    return _agents[identity]


def get_agent_history(identity: str) -> List:
    """Access agent history for tools that need conversation context."""
    agent = _agents.get(identity)
    return agent.history if agent else []
