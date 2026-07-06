"""Truth maintenance and contradiction resolution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Protocol, Sequence

from contexta.core.types import MemoryType, RelationType
from contexta.models.audit import AuditLog
from contexta.models.entity import EntityEdge
from contexta.models.memory import MemoryRecord
from contexta.models.version import MemoryVersion


class MemoryTruthRepository(Protocol):
    async def get_current_truths(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[object]:
        ...

    async def supersede(self, old_id: uuid.UUID, valid_to: datetime) -> int:
        ...


class VersionRepositoryProtocol(Protocol):
    async def create(self, record: MemoryVersion) -> MemoryVersion:
        ...


class EdgeRepositoryProtocol(Protocol):
    async def create(self, record: EntityEdge) -> EntityEdge:
        ...


class AuditRepositoryProtocol(Protocol):
    async def create(self, record: AuditLog) -> AuditLog:
        ...


class ContradictionDetector(Protocol):
    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        ...


@dataclass(frozen=True)
class Supersession:
    """A completed supersession event."""

    old_memory_id: uuid.UUID
    new_memory_id: uuid.UUID
    valid_to: datetime


class SimpleContradictionDetector:
    """Conservative deterministic contradiction detector.

    It only flags likely contradictions when titles are highly similar and
    content differs. LLM-based contradiction detection can replace this later.
    """

    async def contradicts(self, new_memory: MemoryRecord, existing_memory: object) -> bool:
        title_similarity = SequenceMatcher(
            None,
            new_memory.title.lower(),
            str(getattr(existing_memory, "title", "")).lower(),
        ).ratio()
        return (
            title_similarity >= 0.8
            and new_memory.content.strip()
            != str(getattr(existing_memory, "content", "")).strip()
        )


class TruthMaintenanceEngine:
    """Maintain current truth and preserve superseded historical memories."""

    def __init__(
        self,
        memory_repository: MemoryTruthRepository,
        version_repository: VersionRepositoryProtocol,
        *,
        edge_repository: EdgeRepositoryProtocol | None = None,
        audit_repository: AuditRepositoryProtocol | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ) -> None:
        self._memories = memory_repository
        self._versions = version_repository
        self._edges = edge_repository
        self._audit = audit_repository
        self._detector = contradiction_detector or SimpleContradictionDetector()

    async def apply(
        self,
        new_memory: MemoryRecord,
        *,
        entity_ids: Sequence[uuid.UUID] = (),
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> list[Supersession]:
        """Supersede contradicted current memories for the same user and type."""
        timestamp = now or datetime.now(timezone.utc)
        supersessions: list[Supersession] = []

        for existing in await self._candidate_memories(new_memory):
            if not await self._detector.contradicts(new_memory, existing):
                continue

            await self._versions.create(
                MemoryVersion(
                    memory_id=existing.id,
                    superseded_by_id=new_memory.id,
                    content=existing.content,
                    structured_data=getattr(existing, "structured_data", None),
                    importance=getattr(existing, "importance", 0.0),
                    valid_from=existing.valid_from,
                    valid_to=timestamp,
                )
            )
            await self._memories.supersede(existing.id, timestamp)
            await self._create_supersession_edges(
                organization_id=new_memory.organization_id,
                entity_ids=entity_ids,
            )
            await self._log_supersession(
                organization_id=new_memory.organization_id,
                actor_id=actor_id or new_memory.user_id,
                old_memory=existing,
                new_memory=new_memory,
            )
            supersessions.append(
                Supersession(
                    old_memory_id=existing.id,
                    new_memory_id=new_memory.id,
                    valid_to=timestamp,
                )
            )

        return supersessions

    async def _candidate_memories(self, new_memory: MemoryRecord) -> list[object]:
        current_truths = await self._memories.get_current_truths(new_memory.user_id)
        return [
            memory
            for memory in current_truths
            if memory.id != new_memory.id
            and getattr(memory, "valid_to", None) is None
            and self._memory_type_value(getattr(memory, "memory_type", ""))
            == self._memory_type_value(new_memory.memory_type)
        ]

    def _memory_type_value(self, memory_type: str | MemoryType) -> str:
        if isinstance(memory_type, MemoryType):
            return memory_type.value
        return str(memory_type)

    async def _create_supersession_edges(
        self,
        *,
        organization_id: uuid.UUID,
        entity_ids: Sequence[uuid.UUID],
    ) -> None:
        if self._edges is None:
            return
        for entity_id in entity_ids:
            await self._edges.create(
                EntityEdge(
                    source_entity_id=entity_id,
                    target_entity_id=entity_id,
                    relationship_type=RelationType.SUPERSEDED_BY.value,
                    organization_id=organization_id,
                )
            )

    async def _log_supersession(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        old_memory: object,
        new_memory: MemoryRecord,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.create(
            AuditLog(
                organization_id=organization_id,
                actor_id=actor_id,
                operation_type="memory_superseded",
                target_id=old_memory.id,
                details={
                    "old_memory_id": str(old_memory.id),
                    "new_memory_id": str(new_memory.id),
                    "old_content": old_memory.content,
                    "new_content": new_memory.content,
                },
            )
        )
