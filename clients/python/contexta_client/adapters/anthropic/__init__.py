"""contexta adapter for Anthropic Claude SDK.

Package: contexta-anthropic

Provides contextaMemory for fetching context and observing conversation turns,
plus a contextaChat helper that manages an in-memory buffer and flushes on turn
boundaries.
"""

from __future__ import annotations

import logging

from contexta_client import Contexta, contextaError

logger = logging.getLogger(__name__)


class contextaMemory:
    """Anthropic-focused memory wrapper around the contexta base SDK.

    Usage:
        memory = contextaMemory(contexta_client, user_id, token_budget=2000)
        context = memory.context_for("session-uuid")
        memory.observe("session-uuid", [{"role": "user", "content": "Hello"}])
    """

    def __init__(
        self,
        client: Contexta,
        user_id: str,
        token_budget: int | None = None,
    ) -> None:
        self._client = client
        self._user_id = user_id
        self._token_budget = token_budget

    def context_for(self, session_id: str) -> list[dict]:
        """Fetch contexta context and return a list of system-formatted dicts."""
        try:
            context = self._client.context(
                user_id=self._user_id,
                session_id=session_id,
                token_budget=self._token_budget,
            )
        except contextaError:
            logger.warning("contexta context unavailable for session %s", session_id)
            return []

        blocks: list[dict] = []
        if context.user_profile:
            blocks.append({"role": "user", "content": f"Profile: {context.user_profile}"})
        for rule in context.rules:
            blocks.append({"role": "user", "content": f"Rule: {rule}"})
        for pref in context.preferences:
            blocks.append({"role": "user", "content": f"Preference: {pref}"})
        for goal in context.goals:
            blocks.append({"role": "user", "content": f"Goal: {goal}"})
        for mem in context.relevant_memories:
            blocks.append({"role": "assistant", "content": f"[Memory] {mem}"})
        return blocks

    def observe(self, session_id: str, messages: list[dict]) -> None:
        """Send conversation turns to contexta for extraction."""
        if not messages:
            return
        try:
            self._client.observe(
                user_id=self._user_id,
                session_id=session_id,
                messages=messages,
            )
        except contextaError:
            logger.exception("Failed to observe conversation for session %s", session_id)


class contextaChat:
    """In-memory chat buffer that flushes to contexta on turn boundaries.

    Usage:
        chat = contextaChat(contexta_client, user_id, session_id="session-uuid")
        chat.add("user", "Hello!")
        chat.add("assistant", "Hi there!")
        chat.flush()
    """

    def __init__(
        self,
        client: Contexta,
        user_id: str,
        session_id: str,
        memory: contextaMemory | None = None,
        auto_flush: bool = True,
    ) -> None:
        self._client = client
        self._user_id = user_id
        self._session_id = session_id
        self._memory = memory or contextaMemory(client, user_id)
        self._auto_flush = auto_flush
        self._buffer: list[dict] = []

    def add(self, role: str, content: str) -> None:
        self._buffer.append({"role": role, "content": content})

    def flush(self) -> None:
        if not self._buffer:
            return
        try:
            self._client.observe(
                user_id=self._user_id,
                session_id=self._session_id,
                messages=self._buffer,
            )
        except contextaError:
            logger.exception("Failed to flush chat buffer")
        self._buffer.clear()

    def get_context(self) -> list[dict]:
        return self._memory.context_for(self._session_id)

    def turn(self, role: str, content: str) -> None:
        """Add a message and flush on assistant turn boundaries."""
        self.add(role, content)
        if self._auto_flush and role == "assistant":
            self.flush()
