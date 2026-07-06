"""contexta adapter for Anthropic Claude SDK.

Package: contexta-anthropic

Provides contextaMemory for fetching context and observing conversation turns,
plus a contextaChat helper that manages an in-memory buffer and flushes on turn
boundaries.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from contexta_client import contexta, contextaError

logger = logging.getLogger(__name__)


class contextaMemory:
    """Anthropic-focused memory wrapper around the contexta base SDK.

    Usage:
        memory = contextaMemory(contexta_client, token_budget=2000)
        context = memory.context_for("session-uuid")
        memory.observe("session-uuid", [{"role": "user", "content": "Hello"}])
    """

    def __init__(
        self,
        client: contexta,
        token_budget: int | None = None,
    ) -> None:
        self._client = client
        self._token_budget = token_budget

    def context_for(self, session_id: str) -> List[dict]:
        """Fetch contexta context and return a list of system-formatted dicts."""
        try:
            context = self._client.context(
                session_id=session_id,
                token_budget=self._token_budget,
            )
        except contextaError:
            logger.warning("contexta context unavailable for session %s", session_id)
            return []

        blocks: List[dict] = []
        if context.user_profile and context.user_profile.name:
            blocks.append({"role": "user", "content": f"User: {context.user_profile.name}"})
        for pref in context.preferences:
            blocks.append({"role": "user", "content": f"Preference: {pref.category}={pref.value}"})
        for goal in context.goals:
            blocks.append({"role": "user", "content": f"Goal: {goal.description}"})
        for mem in context.relevant_memories:
            blocks.append({"role": "assistant", "content": f"[Memory] {mem.title}: {mem.content}"})
        return blocks

    def observe(self, session_id: str, messages: List[dict]) -> None:
        """Send conversation turns to contexta for extraction."""
        if not messages:
            return
        try:
            self._client.observe(session_id=session_id, messages=messages)
        except contextaError:
            logger.exception("Failed to observe conversation for session %s", session_id)


class contextaChat:
    """In-memory chat buffer that flushes to contexta on turn boundaries.

    Usage:
        chat = contextaChat(contexta_client, session_id="session-uuid")
        chat.add("user", "Hello!")
        chat.add("assistant", "Hi there!")
        chat.flush()
    """

    def __init__(
        self,
        client: contexta,
        session_id: str,
        memory: contextaMemory | None = None,
        auto_flush: bool = True,
    ) -> None:
        self._client = client
        self._session_id = session_id
        self._memory = memory or contextaMemory(client)
        self._auto_flush = auto_flush
        self._buffer: List[dict] = []

    def add(self, role: str, content: str) -> None:
        self._buffer.append({"role": role, "content": content})

    def flush(self) -> None:
        if not self._buffer:
            return
        try:
            self._client.observe(session_id=self._session_id, messages=self._buffer)
        except contextaError:
            logger.exception("Failed to flush chat buffer")
        self._buffer.clear()

    def get_context(self) -> List[dict]:
        return self._memory.context_for(self._session_id)

    def turn(self, role: str, content: str) -> None:
        """Add a message and flush on assistant turn boundaries."""
        self.add(role, content)
        if self._auto_flush and role == "assistant":
            self.flush()
