"""High-speed bulk entity resolution and graph synthesis.

Resolves entity mentions across an entire batch of extracted memories
in a single in-memory pass, pre-fetching user entities once to eliminate
N+1 query bottlenecks and generating bulk-insertable graph records.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any

from contexta.core.schemas import ExtractedMemory
from contexta.core.types import EXCLUDED_ENTITY_WORDS, EntityType, MemoryType, RelationType
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink


@dataclass
class BulkResolutionResult:
    """Artifacts produced by high-speed batch entity resolution."""

    new_entities: list[Entity] = field(default_factory=list)
    updated_entities: list[tuple[uuid.UUID, dict[str, Any]]] = field(default_factory=list)
    links: list[MemoryEntityLink] = field(default_factory=list)
    edges: list[EntityEdge] = field(default_factory=list)
    memory_to_entities: dict[uuid.UUID, list[Entity]] = field(default_factory=dict)


class BulkEntityResolver:
    """In-memory bulk entity resolver and graph edge synthesizer."""

    MATCH_THRESHOLD = 0.85

    _MEMORY_TYPE_TO_ENTITY_TYPE = {
        MemoryType.PROJECT: EntityType.PROJECT,
        MemoryType.PREFERENCE: EntityType.PREFERENCE,
        MemoryType.GOAL: EntityType.GOAL,
        MemoryType.SKILL: EntityType.SKILL,
        MemoryType.RELATIONSHIP: EntityType.PERSON,
    }

    def __init__(
        self,
        entity_repository: Any,
        link_repository: Any | None = None,
        edge_repository: Any | None = None,
    ) -> None:
        self._entities = entity_repository
        self._links = link_repository
        self._edges = edge_repository

    async def resolve_batch(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        memories: Sequence[tuple[uuid.UUID, ExtractedMemory]],
        observed_at: datetime | None = None,
    ) -> BulkResolutionResult:
        """Resolve entity mentions across multiple memories in a single pass.

        Parameters
        ----------
        user_id : uuid.UUID
            Authenticated user ID.
        organization_id : uuid.UUID
            Authenticated organization ID.
        memories : Sequence[tuple[uuid.UUID, ExtractedMemory]]
            List of (memory_record_id, extracted_memory) tuples.
        observed_at : datetime | None
            Observation timestamp.
        """
        timestamp = observed_at or datetime.now(UTC).replace(tzinfo=None)
        result = BulkResolutionResult()

        # 1. Collect all distinct entity mentions across all memories
        all_mentions: set[str] = set()
        for _, mem in memories:
            for ref in mem.entities:
                cleaned = ref.strip()
                if cleaned and len(cleaned) >= 2 and cleaned.lower() not in EXCLUDED_ENTITY_WORDS:
                    all_mentions.add(cleaned)

        if not all_mentions:
            return result

        # 2. Pre-fetch existing entities for user in ONE single database query
        existing_entities: Sequence[Entity] = []
        if hasattr(self._entities, "get_by_user"):
            existing_entities = await self._entities.get_by_user(user_id, limit=1000)

        # Build in-memory fast lookup indexes
        entity_by_name: dict[str, Entity] = {}
        for ent in existing_entities:
            entity_by_name[ent.name.lower()] = ent

        # Track existing edges to prevent duplicates
        known_edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
        existing_entity_ids = [e.id for e in existing_entities]
        if self._edges is not None and hasattr(self._edges, "get_existing_edges") and len(existing_entity_ids) >= 2:
            existing_edges = await self._edges.get_existing_edges(existing_entity_ids)
            for edge in existing_edges:
                s, t = edge.source_entity_id, edge.target_entity_id
                known_edges.add((s, t))
                known_edges.add((t, s))

        # 3. Resolve all mentions in-memory
        for mem_id, mem in memories:
            resolved_for_mem: list[Entity] = []
            seen_for_mem: set[uuid.UUID] = set()

            for ref in mem.entities:
                name = ref.strip()
                if not name or len(name) < 2 or name.lower() in EXCLUDED_ENTITY_WORDS:
                    continue

                name_lower = name.lower()
                matched_ent: Entity | None = entity_by_name.get(name_lower)

                # Fuzzy match fallback if not in exact map
                if matched_ent is None:
                    matched_ent = self._fuzzy_match(name, list(entity_by_name.values()))

                if matched_ent is not None:
                    # Increment mention count in memory
                    attrs = dict(matched_ent.aggregated_attributes or {})
                    attrs["mention_count"] = attrs.get("mention_count", 1) + 1
                    matched_ent.aggregated_attributes = attrs
                    matched_ent.last_updated = timestamp
                    result.updated_entities.append((
                        matched_ent.id,
                        {"last_updated": timestamp, "aggregated_attributes": attrs},
                    ))
                    entity = matched_ent
                else:
                    # Create new entity record
                    ent_type = self._infer_entity_type(name, mem.memory_type)
                    type_str = ent_type.value if hasattr(ent_type, "value") else str(ent_type)
                    entity = Entity(
                        id=uuid.uuid4(),
                        organization_id=organization_id,
                        user_id=user_id,
                        entity_type=type_str,
                        name=name,
                        summary=None,
                        status="active",
                        aggregated_attributes={"mention_count": 1},
                        last_updated=timestamp,
                    )
                    entity_by_name[name_lower] = entity
                    result.new_entities.append(entity)

                if entity.id not in seen_for_mem:
                    seen_for_mem.add(entity.id)
                    resolved_for_mem.append(entity)

                    # Create memory-entity link
                    result.links.append(
                        MemoryEntityLink(
                            memory_id=mem_id,
                            entity_id=entity.id,
                            organization_id=organization_id,
                        )
                    )

            result.memory_to_entities[mem_id] = resolved_for_mem

            # 4. Synthesize typed entity edges within memory.
            # Uses grammar-based relation extraction (typed: uses/depends_on/
            # prefers/works_on/...) with RELATED_TO fallback for co-occurring
            # pairs, instead of a RELATED_TO-only clique.
            if len(resolved_for_mem) > 1 and self._edges is not None:
                from contexta.core.entities.relation_extractor import (
                    extract_semantic_relations,
                )

                mem_text = f"{mem.title}\n{mem.content}"
                for src, rel_type, tgt in extract_semantic_relations(mem_text, resolved_for_mem):
                    if src.id == tgt.id:
                        continue
                    pair = (src.id, tgt.id)
                    rev_pair = (tgt.id, src.id)
                    if pair not in known_edges and rev_pair not in known_edges:
                        known_edges.add(pair)
                        known_edges.add(rev_pair)
                        result.edges.append(
                            EntityEdge(
                                id=uuid.uuid4(),
                                source_entity_id=src.id,
                                target_entity_id=tgt.id,
                                relationship_type=rel_type,
                                organization_id=organization_id,
                            )
                        )

        return result

    def _fuzzy_match(self, name: str, candidates: list[Entity]) -> Entity | None:
        name_lower = name.lower()
        import re
        name_digits = re.findall(r"\d+", name_lower)

        best_candidate: Entity | None = None
        best_ratio = 0.0

        for candidate in candidates:
            cand_name = candidate.name.lower()
            cand_digits = re.findall(r"\d+", cand_name)
            # If numbers/indices differ, they are distinct entities (e.g. Service-1 vs Service-2)
            if name_digits != cand_digits:
                continue

            ratio = SequenceMatcher(None, name_lower, cand_name).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_candidate = candidate

        if best_ratio >= self.MATCH_THRESHOLD:
            return best_candidate
        return None

    def _infer_entity_type(self, name: str, memory_type: MemoryType) -> EntityType:
        lowered = name.lower()
        if any(token in lowered for token in ("python", "redis", "postgres", "fastapi", "docker", "k8s")):
            return EntityType.TECHNOLOGY
        if any(token in lowered for token in ("inc", "llc", "corp", "company", "org", "labs")):
            return EntityType.COMPANY
        return self._MEMORY_TYPE_TO_ENTITY_TYPE.get(memory_type, EntityType.TOPIC)
