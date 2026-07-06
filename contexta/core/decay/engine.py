"""Memory decay engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from contexta.core.types import MemoryState


class DecayEngine:
    """Apply memory lifecycle decay transitions."""

    def transition_for(self, memory, *, now: datetime | None = None) -> str:
        if memory.is_pinned:
            return memory.memory_state
        reference = now or datetime.now(timezone.utc)
        last_seen = memory.last_accessed_at or memory.updated_at or memory.created_at
        age = reference - last_seen
        if memory.memory_state == MemoryState.ACTIVE.value and age >= timedelta(days=30):
            return MemoryState.WARM.value
        if memory.memory_state == MemoryState.WARM.value and age >= timedelta(days=90):
            return MemoryState.COLD.value
        if memory.memory_state == MemoryState.COLD.value and age >= timedelta(days=180):
            return MemoryState.ARCHIVED.value
        return memory.memory_state

    def reactivate_on_access(self, memory) -> str:
        if memory.memory_state in {MemoryState.WARM.value, MemoryState.COLD.value}:
            return MemoryState.ACTIVE.value
        return memory.memory_state
