"""Entity state and aggregate attribute management."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from contexta.core.errors import ValidationError
from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryType
from contexta.models.entity import Entity


class EntityStateRepository(Protocol):
    async def get_by_id(self, record_id: uuid.UUID) -> Entity | None:
        ...

    async def update_by_id(self, record_id: uuid.UUID, values: dict[str, Any]) -> int:
        ...


class EntityStateManager:
    """Maintain entity status, summaries, and aggregate attributes."""

    INACTIVITY_DAYS = 90
    VALID_TRANSITIONS = {
        "active": {"inactive"},
        "inactive": {"active", "archived"},
        "archived": set(),
    }

    def __init__(self, repository: EntityStateRepository) -> None:
        self._repository = repository

    async def update_on_memory_link(
        self,
        entity_id: uuid.UUID,
        memory: ExtractedMemory,
        *,
        observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Refresh entity summary and aggregate attributes from a linked memory."""
        entity = await self._get_entity(entity_id)
        timestamp = observed_at or datetime.utcnow()
        attributes = self._aggregate_attributes(
            entity.aggregated_attributes or {},
            memory,
        )
        values = {
            "summary": self._summarize(entity.summary, memory),
            "last_updated": timestamp,
            "aggregated_attributes": attributes,
        }
        if entity.status == "inactive":
            values["status"] = "active"

        await self._repository.update_by_id(entity_id, values)
        return values

    async def transition(
        self,
        entity_id: uuid.UUID,
        new_status: str,
    ) -> dict[str, Any]:
        """Apply a valid entity status transition."""
        entity = await self._get_entity(entity_id)
        current_status = entity.status
        if new_status not in self.VALID_TRANSITIONS.get(current_status, set()):
            raise ValidationError(
                f"Invalid entity status transition: {current_status} -> {new_status}",
                fields=["status"],
            )

        values = {
            "status": new_status,
            "last_updated": datetime.utcnow(),
        }
        await self._repository.update_by_id(entity_id, values)
        return values

    async def transition_inactive_if_stale(
        self,
        entity_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Transition active entities to inactive after 90 days without updates."""
        entity = await self._get_entity(entity_id)
        if entity.status != "active":
            return False

        reference_time = now or datetime.utcnow()
        if entity.last_updated > reference_time - timedelta(days=self.INACTIVITY_DAYS):
            return False

        await self._repository.update_by_id(
            entity_id,
            {"status": "inactive", "last_updated": reference_time},
        )
        return True

    async def _get_entity(self, entity_id: uuid.UUID) -> Entity:
        entity = await self._repository.get_by_id(entity_id)
        if entity is None:
            raise ValidationError("Entity not found.", fields=["entity_id"])
        return entity

    def _summarize(
        self,
        current_summary: str | None,
        memory: ExtractedMemory,
    ) -> str:
        content = memory.content.strip()
        if not current_summary:
            return content[:500]
        if content and content not in current_summary:
            return f"{current_summary}\n{content}"[:500]
        return current_summary

    def _aggregate_attributes(
        self,
        current: dict[str, Any],
        memory: ExtractedMemory,
    ) -> dict[str, Any]:
        attributes = dict(current)
        if memory.memory_type == MemoryType.FACT:
            key = "facts"
        elif memory.memory_type == MemoryType.PREFERENCE:
            key = "preferences"
        elif memory.memory_type == MemoryType.RELATIONSHIP:
            key = "relationships"
        else:
            key = "observations"

        values = list(attributes.get(key, []))
        if memory.content not in values:
            values.append(memory.content)
        attributes[key] = values

        if memory.structured_data:
            structured = dict(attributes.get("structured_data", {}))
            structured.update(memory.structured_data)
            attributes["structured_data"] = structured

        return attributes
