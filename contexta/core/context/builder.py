"""Context assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from contexta.core.context.planner import ContextItem, ContextPlanner
from contexta.core.schemas import ContextRequest
from contexta.models.memory import MemoryRecord


@dataclass
class BuiltContext:
    user_profile: dict[str, Any] = field(default_factory=dict)
    active_projects: list[dict[str, Any]] = field(default_factory=list)
    preferences: list[dict[str, Any]] = field(default_factory=list)
    goals: list[dict[str, Any]] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    relevant_memories: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    """Assemble structured context from retrieved memories."""

    def __init__(self, planner: ContextPlanner | None = None) -> None:
        self._planner = planner or ContextPlanner()
        self._cache: dict[str, BuiltContext] = {}

    def build(
        self,
        request: ContextRequest,
        memories: list[MemoryRecord],
        *,
        cache_key: str | None = None,
        newest_memory_timestamp: str | None = None,
    ) -> BuiltContext:
        if cache_key and cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached.metadata.get("newest_memory_timestamp") == newest_memory_timestamp:
                return cached

        valid_memories = [
            memory
            for memory in memories
            if not memory.is_archived and memory.valid_to is None
        ]
        valid_memories.sort(key=lambda memory: memory.importance, reverse=True)

        context = BuiltContext()
        for memory in valid_memories:
            item = self._memory_payload(memory)
            if memory.memory_type == "project":
                context.active_projects.append(item)
            elif memory.memory_type == "preference":
                context.preferences.append(item)
            elif memory.memory_type == "goal":
                context.goals.append(item)
            elif memory.memory_type in {"event", "episodic"}:
                context.recent_events.append(item)
            else:
                context.relevant_memories.append(item)

        if request.config.token_budget:
            allocation = self._planner.allocate(
                request.config.token_budget,
                custom_weights=request.config.custom_weights,
            )
            planner_items = [
                ContextItem(
                    category=self._category_for(memory),
                    token_count=max(1, len(memory.content.split())),
                    relevance=memory.importance,
                    payload=memory,
                )
                for memory in valid_memories
            ]
            _, allocation = self._planner.fill_budget(allocation, planner_items)
            context.metadata["token_usage"] = allocation.actual_usage

        context.metadata["newest_memory_timestamp"] = newest_memory_timestamp
        if cache_key:
            self._cache[cache_key] = context
        return context

    def _memory_payload(self, memory: MemoryRecord) -> dict[str, Any]:
        return {
            "id": str(memory.id),
            "type": memory.memory_type,
            "title": memory.title,
            "content": memory.content,
            "importance": memory.importance,
        }

    def _category_for(self, memory: MemoryRecord) -> str:
        return {
            "project": "projects",
            "goal": "goals",
            "preference": "preferences",
            "relationship": "relationships",
            "event": "episodic",
            "episodic": "episodic",
        }.get(memory.memory_type, "facts")
