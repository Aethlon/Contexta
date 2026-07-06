"""Reflection engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class ReflectionEngine:
    """Periodic maintenance for duplicates, dormant goals, and summaries."""

    def mark_dormant_goal(self, memory, *, now: datetime | None = None):
        reference = now or datetime.now(timezone.utc)
        last_seen = memory.last_accessed_at or memory.updated_at or memory.created_at
        if memory.memory_type == "goal" and reference - last_seen >= timedelta(days=180):
            memory.memory_state = "cold"
            memory.importance = max(0.0, memory.importance - 0.3)
        return memory

    def merge_duplicate_facts(self, memories: list) -> list:
        seen: set[str] = set()
        merged = []
        for memory in memories:
            key = memory.content.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(memory)
        return merged
