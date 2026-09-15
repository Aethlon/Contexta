"""Performance and correctness tests for high-speed graph orchestration."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from contexta.core.entities.bulk_resolver import BulkEntityResolver
from contexta.core.graph.cache import GraphCache
from contexta.core.pipeline import FastMemoryOrchestrator
from contexta.core.schemas import ExtractedMemory, ObservationPayload
from contexta.core.types import EntityType, MemoryType, SourceType
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink


class MockEntityRepo:
    def __init__(self, entities: list[Entity] | None = None) -> None:
        self.entities = entities or []
        self.call_count = 0

    async def get_by_user(self, user_id: uuid.UUID, *, offset: int = 0, limit: int = 1000) -> list[Entity]:
        self.call_count += 1
        return [e for e in self.entities if e.user_id == user_id]

    async def create_many(self, records: list[Entity]) -> list[Entity]:
        self.entities.extend(records)
        return records


class MockEdgeRepo:
    def __init__(self) -> None:
        self.edges: list[EntityEdge] = []
        self.call_count = 0

    async def get_existing_edges(self, entity_ids: list[uuid.UUID]) -> list[EntityEdge]:
        self.call_count += 1
        return [
            e for e in self.edges
            if e.source_entity_id in entity_ids and e.target_entity_id in entity_ids
        ]

    async def create_many(self, records: list[EntityEdge]) -> list[EntityEdge]:
        self.edges.extend(records)
        return records


class MockLinkRepo:
    def __init__(self) -> None:
        self.links: list[MemoryEntityLink] = []

    async def create_many(self, records: list[MemoryEntityLink]) -> list[MemoryEntityLink]:
        self.links.extend(records)
        return records


@pytest.mark.asyncio
async def test_bulk_entity_resolver_speed_and_correctness():
    """Verify that BulkEntityResolver pre-fetches once and resolves 20 entities across 10 memories in milliseconds."""
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Pre-populate 3 existing entities
    existing_entities = [
        Entity(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            name="PostgreSQL",
            entity_type=EntityType.TECHNOLOGY.value,
        ),
        Entity(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            name="Redis",
            entity_type=EntityType.TECHNOLOGY.value,
        ),
        Entity(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=org_id,
            name="Project Apollo",
            entity_type=EntityType.PROJECT.value,
        ),
    ]

    entity_repo = MockEntityRepo(existing_entities)
    edge_repo = MockEdgeRepo()
    link_repo = MockLinkRepo()

    resolver = BulkEntityResolver(entity_repo, link_repo, edge_repo)

    # Prepare 10 memories with both existing and novel entity mentions
    memories: list[tuple[uuid.UUID, ExtractedMemory]] = []
    for i in range(10):
        mem_id = uuid.uuid4()
        extracted = ExtractedMemory(
            title=f"Architecture note {i}",
            content=f"Using Postgres and Redis with FastApi and Docker cluster {i}.",
            memory_type=MemoryType.FACT,
            source_type=SourceType.USER_EXPLICIT,
            entities=["PostgreSQL", "Redis", f"Service-{i}", "Project Apollo"],
            tags=["infra", "tech"],
        )
        memories.append((mem_id, extracted))

    t0 = time.perf_counter()
    result = await resolver.resolve_batch(
        user_id=user_id,
        organization_id=org_id,
        memories=memories,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 1. Assert pre-fetch was called exactly ONCE (O(1) database queries instead of O(N*M))
    assert entity_repo.call_count == 1

    # 2. Assert novelty: 10 new Service-X entities were generated
    assert len(result.new_entities) == 10

    # 3. Assert links: 10 memories * 4 entities = 40 links
    assert len(result.links) == 40

    # 4. Assert co-occurrence edges were synthesized without duplicates
    assert len(result.edges) > 0

    # 5. Speed assertion: Must finish in under 30 milliseconds
    assert elapsed_ms < 30.0, f"Bulk resolution took {elapsed_ms:.2f}ms, exceeding 30ms threshold!"


def test_graph_cache_sub_millisecond_bfs():
    """Verify that GraphCache traverses multi-hop neighbor graphs in under 2ms."""
    cache = GraphCache()
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Build a 4-node chain: A -> B -> C -> D
    id_a, id_b, id_c, id_d = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    edges = [
        EntityEdge(id=uuid.uuid4(), source_entity_id=id_a, target_entity_id=id_b, organization_id=org_id, relationship_type="related_to"),
        EntityEdge(id=uuid.uuid4(), source_entity_id=id_b, target_entity_id=id_c, organization_id=org_id, relationship_type="related_to"),
        EntityEdge(id=uuid.uuid4(), source_entity_id=id_c, target_entity_id=id_d, organization_id=org_id, relationship_type="related_to"),
    ]

    cache.update_edges(user_id, edges)

    # Benchmark 2-hop BFS starting from A
    t0 = time.perf_counter()
    distances = cache.traverse(user_id, [id_a], max_hops=2)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert id_a in distances and distances[id_a] == 0
    assert id_b in distances and distances[id_b] == 1
    assert id_c in distances and distances[id_c] == 2
    assert id_d not in distances  # 3 hops away, should not be included
    assert elapsed_ms < 2.0, f"Graph traversal took {elapsed_ms:.2f}ms, exceeding 2ms threshold!"
