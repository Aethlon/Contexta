"""contexta adapter for OpenAI Assistants API.

Package: contexta-openai
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from contexta_client import contexta, contextaError

logger = logging.getLogger(__name__)


class _MemoryInjector:
    """Fetches contexta context and formats it as a system message."""

    def __init__(self, client: contexta, token_budget: int | None = None) -> None:
        self._client = client
        self._token_budget = token_budget

    def build_system_message(self, session_id: str) -> dict:
        try:
            context = self._client.context(
                session_id=session_id,
                token_budget=self._token_budget,
            )
        except contextaError:
            logger.warning("contexta context fetch failed for session %s", session_id)
            return {"role": "system", "content": ""}

        sections = []
        if context.user_profile:
            sections.append(f"User Profile: {context.user_profile.name}")
        if context.preferences:
            prefs = "; ".join(f"{p.category}={p.value}" for p in context.preferences)
            sections.append(f"Preferences: {prefs}")
        if context.goals:
            goals = "; ".join(g.description for g in context.goals)
            sections.append(f"Goals: {goals}")
        if context.active_projects:
            projects = "; ".join(p.name for p in context.active_projects)
            sections.append(f"Active Projects: {projects}")
        for mem in context.relevant_memories:
            sections.append(f"[Memory] {mem.title}: {mem.content}")

        content = "\n".join(sections) if sections else ""
        return {"role": "system", "content": content}


class contextaMemory:
    """Hooks contexta context retrieval and observation into an OpenAI Assistant run.

    Usage:
        memory = contextaMemory(contexta_client, token_budget=2000)
        runner = contextaAssistantRunner(client=openai_client, memory=memory)
        result = runner.run_with_session(
            assistant_id="asst_...",
            session_id="session-uuid",
            user_message="Hello!",
        )
    """

    def __init__(
        self,
        client: contexta,
        token_budget: int | None = None,
        auto_batch_size: int = 10,
    ) -> None:
        self._client = client
        self._token_budget = token_budget
        self._auto_batch_size = auto_batch_size
        self._injector = _MemoryInjector(client, token_budget)

    def context_for_session(self, session_id: str) -> dict:
        return self._injector.build_system_message(session_id)

    def observe_messages(
        self,
        session_id: str,
        messages: List[dict],
    ) -> None:
        if not messages:
            return
        try:
            self._client.observe(session_id=session_id, messages=messages)
        except contextaError:
            logger.exception("Failed to observe messages for session %s", session_id)

    def _extract_thread_messages(
        self,
        thread_messages: List[dict],
    ) -> List[dict]:
        extracted = []
        for msg in thread_messages:
            role = msg.get("role", "")
            content_blocks = msg.get("content", [])
            text_parts = []
            for block in content_blocks:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            if text_parts:
                extracted.append({"role": role, "content": " ".join(text_parts)})
        return extracted

    def observe_thread(
        self,
        session_id: str,
        thread_messages: List[dict],
    ) -> None:
        obs_messages = self._extract_thread_messages(thread_messages)
        self.observe_messages(session_id, obs_messages)


class contextaAssistantRunner:
    """Drop-in runner that injects contexta context before each user turn
    and observes thread content after each run completes.

    Usage:
        runner = contextaAssistantRunner(openai_client, memory)
        response = runner.run_with_session(
            assistant_id="asst_...",
            session_id="session-uuid",
            user_message="What do you know about me?",
        )
    """

    def __init__(
        self,
        openai_client: Any,
        memory: contextaMemory,
        auto_observe: bool = True,
    ) -> None:
        self._openai = openai_client
        self._memory = memory
        self._auto_observe = auto_observe
        self._session_thread_map: Dict[str, str] = {}

    def _get_or_create_thread(self, session_id: str) -> str:
        if session_id in self._session_thread_map:
            return self._session_thread_map[session_id]
        thread = self._openai.beta.threads.create()
        self._session_thread_map[session_id] = thread.id
        return thread.id

    def run_with_session(
        self,
        assistant_id: str,
        session_id: str,
        user_message: str,
        thread_id: str | None = None,
        **run_kwargs: Any,
    ) -> Any:
        if not thread_id:
            thread_id = self._get_or_create_thread(session_id)

        context_msg = self._memory.context_for_session(session_id)
        if context_msg.get("content"):
            self._openai.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=f"[contexta Context]\n{context_msg['content']}",
            )

        self._openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
        )

        run = self._openai.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id,
            **run_kwargs,
        )

        if self._auto_observe:
            messages = self._openai.beta.threads.messages.list(thread_id=thread_id)
            raw = [{"role": m.role, "content": self._flatten_content(m.content)} for m in messages.data]
            self._memory.observe_messages(session_id, raw)

        return run

    def _flatten_content(self, content_blocks: List[Any]) -> str:
        texts = []
        for block in content_blocks:
            if hasattr(block, "text") and block.text:
                texts.append(block.text.value if hasattr(block.text, "value") else str(block.text))
            elif isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts) if texts else ""
