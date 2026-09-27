"""contexta adapter for LangChain.

Package: contexta-langchain

Provides contextaChatHistory implementing BaseChatMessageHistory for use with
LCEL and RunnableWithMessageHistory, plus a legacy Memory compatibility layer.
"""

from __future__ import annotations

import logging
from typing import Any

from contexta_client import Contexta

logger = logging.getLogger(__name__)

try:
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        message_to_dict,
        messages_from_dict,
    )
except ImportError:
    BaseChatMessageHistory = object
    BaseMessage = None
    HumanMessage = None
    AIMessage = None
    SystemMessage = None
    message_to_dict = None
    messages_from_dict = None


class contextaChatHistory(BaseChatMessageHistory if BaseChatMessageHistory is not object else object):
    """LangChain chat message history backed by contexta's persistent store.

    Works as a drop-in with RunnableWithMessageHistory.

    Usage:
        history = contextaChatHistory(contexta_client, user_id, session_id="session-uuid")
        chain = RunnableWithMessageHistory(llm, lambda s: history)
    """

    def __init__(
        self,
        client: Contexta,
        user_id: str,
        session_id: str,
        token_budget: int | None = None,
    ) -> None:
        if BaseChatMessageHistory is object:
            raise ImportError(
                "langchain is required. Install with: pip install langchain>=0.3"
            )
        self._client = client
        self._user_id = user_id
        self._session_id = session_id
        self._token_budget = token_budget
        self._buffer: list[BaseMessage] = []

    @property
    def messages(self) -> list[BaseMessage]:
        context = self._client.context(
            user_id=self._user_id,
            session_id=self._session_id,
            token_budget=self._token_budget,
        )
        result: list[BaseMessage] = list(self._buffer)
        if context.user_profile:
            result.insert(
                0,
                SystemMessage(content=f"User: {context.user_profile}"),
            )
        for pref in context.preferences:
            result.insert(0, SystemMessage(content=f"Preference: {pref}"))
        for goal in context.goals:
            result.insert(0, SystemMessage(content=f"Goal: {goal}"))
        for mem in context.relevant_memories:
            result.insert(0, SystemMessage(content=f"[Memory] {mem}"))
        return result

    @messages.setter
    def messages(self, value: list[BaseMessage]) -> None:
        self._buffer = list(value)

    def add_message(self, message: BaseMessage) -> None:
        self._buffer.append(message)

    def add_user_message(self, message: str) -> None:
        self.add_message(HumanMessage(content=message))

    def add_ai_message(self, message: str) -> None:
        self.add_message(AIMessage(content=message))

    def clear(self) -> None:
        self._buffer.clear()

    def flush(self) -> None:
        if not self._buffer:
            return
        if message_to_dict is not None:
            raw = [
                {"role": self._infer_role(m), "content": m.content}
                for m in self._buffer
            ]
        else:
            raw = [{"role": "user", "content": m.content} for m in self._buffer]
        try:
            self._client.observe(
                user_id=self._user_id,
                session_id=self._session_id,
                messages=raw,
            )
        except Exception:
            logger.exception("Failed to flush observations to contexta")
        self._buffer.clear()

    def _infer_role(self, message: BaseMessage) -> str:
        if isinstance(message, HumanMessage):
            return "user"
        if isinstance(message, AIMessage):
            return "assistant"
        if isinstance(message, SystemMessage):
            return "system"
        return "user"

    def __len__(self) -> int:
        return len(self._buffer)

    def __bool__(self) -> bool:
        return bool(self._buffer)


class contextaMemoryLegacy:
    """Legacy Memory compatibility wrapper for use with older LangChain chains.

    Wraps contextaChatHistory in the BaseMemory interface (memory_key, buffer).
    """

    def __init__(
        self,
        client: Contexta,
        user_id: str,
        session_id: str,
        memory_key: str = "chat_history",
        token_budget: int | None = None,
    ) -> None:
        self._chat_history = contextaChatHistory(client, user_id, session_id, token_budget)
        self.memory_key = memory_key

    @property
    def buffer(self) -> list[BaseMessage]:
        return self._chat_history.messages

    @buffer.setter
    def buffer(self, value: list[BaseMessage]) -> None:
        self._chat_history.messages = value

    def load_memory_variables(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {self.memory_key: self.buffer}

    def save_context(self, inputs: dict[str, str], outputs: dict[str, str]) -> None:
        for value in inputs.values():
            self._chat_history.add_user_message(str(value))
        for value in outputs.values():
            self._chat_history.add_ai_message(str(value))

    def clear(self) -> None:
        self._chat_history.clear()
