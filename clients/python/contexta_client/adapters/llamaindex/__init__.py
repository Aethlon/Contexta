"""contexta adapter for LlamaIndex.

Package: contexta-llamaindex

Provides contextaChatMemory which conforms to LlamaIndex's BaseMemory protocol,
acting as a drop-in replacement for ChatMemoryBuffer.
"""

from __future__ import annotations

import logging
from typing import Any

from contexta_client import Contexta

logger = logging.getLogger(__name__)

try:
    from llama_index.core.base.llms.types import ChatMessage, MessageRole
    from llama_index.core.memory import BaseMemory
except ImportError:
    BaseMemory = object
    ChatMessage = None
    MessageRole = None


class contextaChatMemory(BaseMemory if BaseMemory is not object else object):
    """LlamaIndex memory backed by contexta's persistent store.

    - get_all() fetches context from contexta and returns as ChatMessage list.
    - put(message) appends to an observation buffer, flushed on turn boundaries.
    - Honors token_budget for context assembly.

    Usage:
        memory = contextaChatMemory(contexta_client, user_id, session_id="...", token_budget=2000)
        chat_engine = index.as_chat_engine(chat_mode="context", memory=memory)
    """

    def __init__(
        self,
        client: Contexta,
        user_id: str,
        session_id: str,
        token_budget: int | None = None,
        **kwargs: Any,
    ) -> None:
        if BaseMemory is object:
            raise ImportError(
                "llama-index-core is required. Install with: pip install llama-index-core"
            )
        super().__init__(**kwargs)
        self._client = client
        self._user_id = user_id
        self._session_id = session_id
        self._token_budget = token_budget
        self._buffer: list[ChatMessage] = []

    def get_all(self) -> list[ChatMessage]:
        context = self._client.context(
            user_id=self._user_id,
            session_id=self._session_id,
            token_budget=self._token_budget,
        )
        messages: list[ChatMessage] = []
        if context.user_profile:
            messages.append(
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=f"User: {context.user_profile}",
                )
            )
        for pref in context.preferences:
            messages.append(
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=f"Preference: {pref}",
                )
            )
        for goal in context.goals:
            messages.append(
                ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=f"Goal: {goal}",
                )
            )
        for mem in context.relevant_memories:
            messages.append(
                ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=f"[Memory] {mem}",
                )
            )
        return messages

    def put(self, message: ChatMessage) -> None:
        self._buffer.append(message)

    def flush(self) -> None:
        if not self._buffer:
            return
        raw = [
            {"role": m.role.value if hasattr(m.role, "value") else str(m.role), "content": m.content}
            for m in self._buffer
        ]
        try:
            self._client.observe(
                user_id=self._user_id,
                session_id=self._session_id,
                messages=raw,
            )
        except Exception:
            logger.exception("Failed to flush observations to contexta")
        self._buffer.clear()

    def reset(self) -> None:
        self._buffer.clear()

    def set(self, messages: list[ChatMessage]) -> None:
        self._buffer = list(messages)
