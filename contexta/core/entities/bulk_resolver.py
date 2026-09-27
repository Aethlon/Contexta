"""High-speed bulk entity resolution and graph synthesis.

Resolves entity mentions across an entire batch of extracted memories in a
single pass and returns bulk-insertable graph records for the caller to
persist in its own transaction.

Matching is delegated to the repository: one indexed exact lookup for the
mentions actually present in the batch, then at most one bounded pg_trgm
query per unresolved mention. Nothing here scans the user's whole entity set,
so cost tracks the size of the batch rather than the size of the graph.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from contexta.core.schemas import ExtractedMemory
from contexta.core.types import EXCLUDED_ENTITY_WORDS, EntityType, MemoryType
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink
from contexta.repositories.entity_repo import TRGM_MATCH_THRESHOLD

# Minimum trigram similarity for two names to resolve to the same entity.
#
# This is a different scale from the difflib.SequenceMatcher.ratio() it
# replaces, so the old 0.85 cut-off does NOT carry over: trigrams score far
# lower for the same pair (0.85 on difflib is stricter than 0.9 on trigrams).
# The repository already measured its own cut-off against the production
# corpus, so this aliases that value instead of re-tuning it. It stays a
# module-level name so the resolver has exactly one knob.
TRGM_NAME_MATCH_THRESHOLD: float = TRGM_MATCH_THRESHOLD

# Word-boundary tokenisation for entity typing. Matching on raw substrings
# classified "Organization", "Organic" and "Org Chart" as COMPANY because they
# all contain "org".
_WORD_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_DIGIT_GROUP_RE = re.compile(r"\d+")

_TECHNOLOGY_TOKENS = frozenset({"python", "redis", "postgres", "fastapi", "docker", "k8s"})
_COMPANY_TOKENS = frozenset({"inc", "llc", "corp", "company", "org", "labs"})


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

    MATCH_THRESHOLD: float = TRGM_NAME_MATCH_THRESHOLD

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

        # 2. Seed the exact-match index with ONE query bounded by this batch's
        # mentions, rather than paging the user's whole entity set into memory.
        # The dict stays warm for the rest of the batch: new entities are added
        # as they are created, so a mention repeated across N memories costs
        # zero further queries.
        entity_by_name: dict[str, Entity] = await self._seed_exact_matches(
            user_id=user_id,
            mentions=all_mentions,
        )

        # Trigram lookups are memoised per batch for the same reason: the same
        # misspelling usually recurs across every memory in the batch.
        fuzzy_by_name: dict[str, Entity | None] = {}

        # Entities created in this batch already carry their final attributes in
        # memory, so they are excluded from the update set: the caller INSERTs
        # them and a separate UPDATE for the same row would be a wasted write.
        new_entity_ids: set[uuid.UUID] = set()

        # Per-entity update staging. The caller turns each entry into its own
        # UPDATE carrying a read-modify-write snapshot of the aggregated
        # attributes JSONB, so one entry per entity (not one per mention) is
        # what keeps concurrent ingestion from losing increments.
        staged_updates: dict[uuid.UUID, dict[str, Any]] = {}

        # In-batch edge dedup, keyed to mirror uq_entity_edge_identity exactly
        # so the in-memory check and the database backstop cannot disagree.
        known_edges: set[tuple[uuid.UUID, uuid.UUID, str]] = set()

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

                # Trigram fallback if not an exact match. One bounded, indexed
                # query, replaced by the memo on every later mention.
                if matched_ent is None and name_lower not in fuzzy_by_name:
                    fuzzy_by_name[name_lower] = await self._fuzzy_match(
                        user_id=user_id,
                        name=name,
                    )
                if matched_ent is None:
                    matched_ent = fuzzy_by_name.get(name_lower)

                if matched_ent is not None:
                    # Record the matched spelling so later mentions of the same
                    # variant resolve exactly instead of via another trigram hit.
                    entity_by_name[name_lower] = matched_ent

                    # Increment mention count in memory
                    attrs = dict(matched_ent.aggregated_attributes or {})
                    attrs["mention_count"] = attrs.get("mention_count", 1) + 1
                    matched_ent.aggregated_attributes = attrs
                    matched_ent.last_updated = timestamp
                    if matched_ent.id not in new_entity_ids:
                        staged_updates[matched_ent.id] = {
                            "last_updated": timestamp,
                            "aggregated_attributes": attrs,
                        }
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
                    new_entity_ids.add(entity.id)
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
                    # ck_entity_edge_no_self_loop rejects self-loops, and
                    # ON CONFLICT does not cover a check constraint, so they are
                    # dropped here rather than handed to the insert.
                    if src.id == tgt.id:
                        continue
                    identity = (src.id, tgt.id, rel_type)
                    if identity in known_edges:
                        continue
                    known_edges.add(identity)
                    result.edges.append(
                        EntityEdge(
                            id=uuid.uuid4(),
                            source_entity_id=src.id,
                            target_entity_id=tgt.id,
                            relationship_type=rel_type,
                            organization_id=organization_id,
                        )
                    )

        result.updated_entities.extend(staged_updates.items())
        return result

    async def persist_edges(
        self,
        edges: Sequence[EntityEdge],
    ) -> Sequence[EntityEdge]:
        """Write synthesized edges conflict-tolerantly.

        This is the write path that keeps a racing ingestion harmless: two
        batches that both synthesize the same relationship resolve to the same
        (organization, source, target, relationship_type) identity, and
        `ON CONFLICT DO NOTHING` lets the loser drop its row instead of
        aborting the whole ingestion with an IntegrityError.
        """
        if self._edges is None:
            raise ValueError("Edge repository is required to persist entity edges.")
        return await self._edges.insert_many_ignore_conflicts(edges)

    async def _seed_exact_matches(
        self,
        *,
        user_id: uuid.UUID,
        mentions: set[str],
    ) -> dict[str, Entity]:
        """Build the case-insensitive name index for the mentions in this batch.

        `get_by_names` is the production path: one tenant- and user-scoped query
        whose cost is bounded by the batch. The `get_by_user` fallback only
        serves repositories that do not implement it (duck-typed test doubles);
        it is a bounded scan, so it must never be the primary strategy.
        """
        if not mentions:
            return {}

        getter = getattr(self._entities, "get_by_names", None)
        if getter is not None:
            rows = await getter(user_id, list(mentions))
        else:
            rows = await self._entities.get_by_user(user_id)

        index: dict[str, Entity] = {}
        for ent in rows:
            # setdefault: `ix_entity_identity` is deliberately not unique, so a
            # pre-existing duplicate must not be silently reshuffled per batch.
            index.setdefault(ent.name.lower(), ent)
        return index

    async def _fuzzy_match(self, *, user_id: uuid.UUID, name: str) -> Entity | None:
        """Resolve one mention against the tenant's entities via pg_trgm.

        `find_similar_names` returns candidates best-first and already filtered
        by the similarity threshold, so the first candidate that survives the
        digit-group guard is the best acceptable match.
        """
        finder = getattr(self._entities, "find_similar_names", None)
        if finder is None:
            return None

        name_digits = _DIGIT_GROUP_RE.findall(name.lower())
        for candidate in await finder(user_id, name, threshold=self.MATCH_THRESHOLD):
            # If numbers/indices differ, they are distinct entities (e.g.
            # Service-1 vs Service-2). Trigrams score those two as nearly
            # identical, so this guard is what keeps them apart.
            if _DIGIT_GROUP_RE.findall(candidate.name.lower()) != name_digits:
                continue
            return candidate
        return None

    def _infer_entity_type(self, name: str, memory_type: MemoryType) -> EntityType:
        """Classify a name, matching lexicon entries on word boundaries only.

        A company marker is only honoured as the final word, the way legal
        suffixes actually appear ("Acme Inc", "Northwind Labs"). That keeps
        "Organization" and "Organic" from reading as companies on the "org"
        substring, and "Org Chart" from reading as one on a leading "org".
        """
        words = [word for word in _WORD_SPLIT_RE.split(name.lower()) if word]
        if any(word in _TECHNOLOGY_TOKENS for word in words):
            return EntityType.TECHNOLOGY
        if words and words[-1] in _COMPANY_TOKENS:
            return EntityType.COMPANY
        return self._MEMORY_TYPE_TO_ENTITY_TYPE.get(memory_type, EntityType.TOPIC)
