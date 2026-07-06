"""Entity resolution and graph linking."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Protocol, Sequence

from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.types import EntityType, MemoryType, RelationType
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink


class EntityRepositoryProtocol(Protocol):
    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Entity]:
        ...

    async def create(self, record: Entity) -> Entity:
        ...

    async def update_by_id(self, record_id: uuid.UUID, values: dict[str, Any]) -> int:
        ...


class LinkRepositoryProtocol(Protocol):
    async def create(self, record: MemoryEntityLink) -> MemoryEntityLink:
        ...


class EdgeRepositoryProtocol(Protocol):
    async def create(self, record: EntityEdge) -> EntityEdge:
        ...


class EntitySimilarityProvider(Protocol):
    async def similarity(self, left: str, right: str) -> float:
        ...


@dataclass(frozen=True)
class ResolvedEntity:
    """Entity resolution output for one entity mention."""

    entity: Entity
    confidence: float
    created: bool


class NameSimilarityProvider:
    """Deterministic local similarity provider."""

    async def similarity(self, left: str, right: str) -> float:
        return SequenceMatcher(None, left.lower(), right.lower()).ratio()


class EntityResolver:
    """Resolve extracted entity mentions into graph nodes and links."""

    MATCH_THRESHOLD = 0.8

    _MEMORY_TYPE_TO_ENTITY_TYPE = {
        MemoryType.PROJECT: EntityType.PROJECT,
        MemoryType.PREFERENCE: EntityType.PREFERENCE,
        MemoryType.GOAL: EntityType.GOAL,
        MemoryType.SKILL: EntityType.SKILL,
        MemoryType.RELATIONSHIP: EntityType.PERSON,
    }

    def __init__(
        self,
        entity_repository: EntityRepositoryProtocol,
        link_repository: LinkRepositoryProtocol,
        edge_repository: EdgeRepositoryProtocol | None = None,
        similarity_provider: EntitySimilarityProvider | None = None,
    ) -> None:
        self._entities = entity_repository
        self._links = link_repository
        self._edges = edge_repository
        self._similarity = similarity_provider or NameSimilarityProvider()

    async def resolve_memory_entities(
        self,
        *,
        payload: ObservationPayload,
        memory_id: uuid.UUID,
        memory: ExtractedMemory,
        observed_at: datetime | None = None,
    ) -> list[ResolvedEntity]:
        """Resolve all entity mentions on a memory and link them to the memory."""
        timestamp = observed_at or datetime.now(timezone.utc)
        resolved: list[ResolvedEntity] = []

        for reference in memory.entities:
            name = reference.strip()
            if not name:
                continue

            entity_type = self._infer_entity_type(name, memory.memory_type)
            result = await self.resolve_entity(
                payload=payload,
                name=name,
                entity_type=entity_type,
                observed_at=timestamp,
            )
            await self._links.create(
                MemoryEntityLink(
                    memory_id=memory_id,
                    entity_id=result.entity.id,
                    organization_id=payload.organization_id,
                )
            )
            resolved.append(result)

        return resolved

    async def resolve_entity(
        self,
        *,
        payload: ObservationPayload,
        name: str,
        entity_type: EntityType,
        observed_at: datetime | None = None,
    ) -> ResolvedEntity:
        """Resolve one entity mention using semantic/name similarity."""
        timestamp = observed_at or datetime.now(timezone.utc)
        candidates = [
            entity
            for entity in await self._entities.get_by_user(payload.user_id, limit=500)
            if entity.entity_type == entity_type.value
        ]
        match, confidence = await self._best_match(name, candidates)

        if match is not None and confidence > self.MATCH_THRESHOLD:
            await self._entities.update_by_id(match.id, {"last_updated": timestamp})
            match.last_updated = timestamp
            return ResolvedEntity(entity=match, confidence=confidence, created=False)

        entity = Entity(
            organization_id=payload.organization_id,
            user_id=payload.user_id,
            entity_type=entity_type.value,
            name=name,
            summary=None,
            status="active",
            aggregated_attributes={},
            last_updated=timestamp,
        )
        entity = await self._entities.create(entity)
        return ResolvedEntity(entity=entity, confidence=confidence, created=True)

    async def create_edge(
        self,
        *,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        organization_id: uuid.UUID,
        relationship_type: RelationType,
    ) -> EntityEdge:
        """Create a typed entity edge."""
        if self._edges is None:
            raise ValueError("Edge repository is required to create entity edges.")

        return await self._edges.create(
            EntityEdge(
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship_type=relationship_type.value,
                organization_id=organization_id,
            )
        )

    async def _best_match(
        self,
        name: str,
        candidates: Sequence[Entity],
    ) -> tuple[Entity | None, float]:
        best_entity: Entity | None = None
        best_confidence = 0.0

        for candidate in candidates:
            name_similarity = SequenceMatcher(
                None,
                name.lower(),
                candidate.name.lower(),
            ).ratio()
            semantic_similarity = await self._similarity.similarity(
                name,
                " ".join(
                    part
                    for part in [candidate.name, candidate.summary or ""]
                    if part
                ),
            )
            confidence = max(name_similarity, semantic_similarity)
            if confidence > best_confidence:
                best_confidence = confidence
                best_entity = candidate

        return best_entity, best_confidence

    def _infer_entity_type(
        self,
        name: str,
        memory_type: MemoryType,
    ) -> EntityType:
        lowered = name.lower()
        if any(token in lowered for token in ("python", "redis", "postgres", "fastapi")):
            return EntityType.TECHNOLOGY
        if any(token in lowered for token in ("inc", "llc", "corp", "company")):
            return EntityType.COMPANY
        return self._MEMORY_TYPE_TO_ENTITY_TYPE.get(memory_type, EntityType.TOPIC)
