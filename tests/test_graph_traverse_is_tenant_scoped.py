"""Tenant isolation for the entity-graph routes.

`/v1/graph/traverse` and its siblings hand a caller the shape of a whole
knowledge graph, so these assert isolation rather than the happy path: no node,
edge, link or memory belonging to another organization may appear in a
response, and no row of another organization may be loaded in order to decide
what to return.

Two of the assertions deliberately seed rows the schema permits but the
invariant forbids: an `EntityEdge` and a `MemoryEntityLink` stamped with
organization A while pointing at organization B's entity and memory. Nothing
in the database enforces that the three `organization_id` columns agree, so
those rows are representable, and they are what a query that reloads
"the nodes and memories I just saw referenced" walks straight out of the
tenant on. The primary leak -- the unscoped entity-name lookup -- needs no
inconsistent data to fire.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.api.app import app
from contexta.db import AsyncSessionFactory, get_db_session
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink
from contexta.models.memory import MemoryRecord

# Distinctive substrings seeded into organization B's rows. Asserting the whole
# serialized body contains none of them catches a leak even if the leaked value
# is copied into a field the id-based assertions do not cover.
CANARY_ORGANIZATION_B = "ORG-B-SECRET"


def _db_available() -> bool:
    """True when the configured Postgres is actually reachable.

    Isolation cannot be asserted against a mocked session, so these tests need
    the real database and skip rather than pretend when it is absent.
    """

    async def probe() -> bool:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return True

    try:
        return asyncio.run(probe())
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(),
    reason="needs the Contexta Postgres to assert real tenant isolation",
)


@dataclass
class _SeededGraph:
    organization_a: uuid.UUID
    user_a: uuid.UUID
    organization_b: uuid.UUID
    user_b: uuid.UUID
    shared_name: str
    b_only_name: str
    entity_a: uuid.UUID
    neighbour_a: uuid.UUID
    shared_entity_b: uuid.UUID
    b_only_entity_b: uuid.UUID
    hidden_entity_b: uuid.UUID
    memory_a: uuid.UUID
    shared_memory_b: uuid.UUID
    b_only_memory_b: uuid.UUID
    hidden_memory_b: uuid.UUID
    organization_b_edge: tuple[uuid.UUID, uuid.UUID]
    organizations: tuple[uuid.UUID, ...] = field(default=())

    @property
    def organization_b_ids(self) -> set[str]:
        return {
            str(value)
            for value in (
                self.shared_entity_b,
                self.b_only_entity_b,
                self.hidden_entity_b,
                self.shared_memory_b,
                self.b_only_memory_b,
                self.hidden_memory_b,
            )
        }


def _identity(organization_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, str]:
    """The header pair the auth middleware accepts for a legacy-tenant request.

    Organization and actor must travel together: one alone is refused with a
    401 before the route runs.
    """
    return {"x-organization-id": str(organization_id), "x-user-id": str(user_id)}


async def _seed(session: AsyncSession) -> _SeededGraph:
    token = uuid.uuid4().hex[:10]
    organization_a, user_a = uuid.uuid4(), uuid.uuid4()
    organization_b, user_b = uuid.uuid4(), uuid.uuid4()
    shared_name = f"Leaky Widget {token}"
    b_only_name = f"Orphan Node {token}"

    def entity(organization_id: uuid.UUID, user_id: uuid.UUID, name: str, summary: str) -> Entity:
        return Entity(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            entity_type="product",
            name=name,
            summary=summary,
        )

    def memory(organization_id: uuid.UUID, user_id: uuid.UUID, body: str) -> MemoryRecord:
        return MemoryRecord(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            memory_type="fact",
            title=body,
            content=body,
            source_type="user_explicit",
        )

    entity_a = entity(organization_a, user_a, shared_name, "organization a root")
    neighbour_a = entity(organization_a, user_a, f"Colleague {token}", "organization a neighbour")
    shared_entity_b = entity(
        organization_b, user_b, shared_name, f"{CANARY_ORGANIZATION_B} shared summary"
    )
    b_only_entity_b = entity(
        organization_b, user_b, b_only_name, f"{CANARY_ORGANIZATION_B} only summary"
    )
    hidden_entity_b = entity(
        organization_b, user_b, f"Hidden {token}", f"{CANARY_ORGANIZATION_B} hidden summary"
    )

    memory_a = memory(organization_a, user_a, "ORGANIZATION-A root memory")
    shared_memory_b = memory(organization_b, user_b, f"{CANARY_ORGANIZATION_B} shared memory")
    b_only_memory_b = memory(organization_b, user_b, f"{CANARY_ORGANIZATION_B} only memory")
    hidden_memory_b = memory(organization_b, user_b, f"{CANARY_ORGANIZATION_B} hidden memory")

    session.add_all(
        [
            entity_a,
            neighbour_a,
            shared_entity_b,
            b_only_entity_b,
            hidden_entity_b,
            memory_a,
            shared_memory_b,
            b_only_memory_b,
            hidden_memory_b,
        ]
    )
    # Flush first: the models declare no ORM relationships, so the unit of work
    # has no dependency graph to order these inserts by and would write the link
    # rows ahead of the rows they point at.
    await session.flush()
    session.add_all(
        [
            MemoryEntityLink(
                memory_id=memory_a.id, entity_id=entity_a.id, organization_id=organization_a
            ),
            MemoryEntityLink(
                memory_id=shared_memory_b.id,
                entity_id=shared_entity_b.id,
                organization_id=organization_b,
            ),
            MemoryEntityLink(
                memory_id=b_only_memory_b.id,
                entity_id=b_only_entity_b.id,
                organization_id=organization_b,
            ),
            MemoryEntityLink(
                memory_id=hidden_memory_b.id,
                entity_id=hidden_entity_b.id,
                organization_id=organization_b,
            ),
            # Organization A's own link row, pointing at organization B's memory.
            MemoryEntityLink(
                memory_id=hidden_memory_b.id,
                entity_id=entity_a.id,
                organization_id=organization_a,
            ),
        ]
    )
    session.add_all(
        [
            EntityEdge(
                id=uuid.uuid4(),
                source_entity_id=entity_a.id,
                target_entity_id=neighbour_a.id,
                relationship_type="works_on",
                organization_id=organization_a,
            ),
            # Organization A's own edge row, pointing at organization B's entity,
            # so organization A's tenant-scoped edge scan reaches a foreign node.
            EntityEdge(
                id=uuid.uuid4(),
                source_entity_id=entity_a.id,
                target_entity_id=hidden_entity_b.id,
                relationship_type="related_to",
                organization_id=organization_a,
            ),
        ]
    )
    await session.commit()

    organization_b_edge = EntityEdge(
        id=uuid.uuid4(),
        source_entity_id=shared_entity_b.id,
        target_entity_id=b_only_entity_b.id,
        relationship_type="works_on",
        organization_id=organization_b,
    )
    session.add(organization_b_edge)
    await session.commit()

    return _SeededGraph(
        organization_a=organization_a,
        user_a=user_a,
        organization_b=organization_b,
        user_b=user_b,
        shared_name=shared_name,
        b_only_name=b_only_name,
        entity_a=entity_a.id,
        neighbour_a=neighbour_a.id,
        shared_entity_b=shared_entity_b.id,
        b_only_entity_b=b_only_entity_b.id,
        hidden_entity_b=hidden_entity_b.id,
        memory_a=memory_a.id,
        shared_memory_b=shared_memory_b.id,
        b_only_memory_b=b_only_memory_b.id,
        hidden_memory_b=hidden_memory_b.id,
        organization_b_edge=(str(shared_entity_b.id), str(b_only_entity_b.id)),
        organizations=(organization_a, organization_b),
    )


async def _wipe(session: AsyncSession, graph: _SeededGraph) -> None:
    organizations = list(graph.organizations)
    for statement in (
        delete(MemoryEntityLink).where(
            MemoryEntityLink.organization_id.in_(organizations)
        ),
        delete(EntityEdge).where(EntityEdge.organization_id.in_(organizations)),
        delete(Entity).where(Entity.organization_id.in_(organizations)),
        delete(MemoryRecord).where(MemoryRecord.organization_id.in_(organizations)),
    ):
        await session.execute(statement)
    await session.commit()


@pytest.fixture
async def seeded_graph() -> AsyncIterator[_SeededGraph]:
    async with AsyncSessionFactory() as session:
        graph = await _seed(session)
    try:
        yield graph
    finally:
        async with AsyncSessionFactory() as session:
            await _wipe(session, graph)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An ASGI client whose routes get a real session, so isolation is real."""

    async def _session() -> AsyncIterator[AsyncSession]:
        async with AsyncSessionFactory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db_session] = _session
    # raise_app_exceptions=False so a pre-fix failure surfaces as the 500 the
    # caller would actually have received, not as an exception in the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def _assert_organization_b_absent(body: object, graph: _SeededGraph) -> None:
    """No organization B entity, memory or edge may reach the caller.

    An edge carries no `organization_id` in the response, so an organization B
    edge is recognised by its endpoint pair. An organization A edge that points
    at an organization B entity id is organization A's own row: the caller's
    graph is entitled to say "these two ids are related" even where one of them
    resolves to nothing the caller may read.
    """
    rendered = json.dumps(body, default=str)
    assert CANARY_ORGANIZATION_B not in rendered, (
        f"organization B content leaked into the response: {rendered}"
    )
    forbidden = graph.organization_b_ids
    root = body.get("root_entity")
    if root:
        assert root["id"] not in forbidden, f"organization B entity leaked as the root: {root}"
    for node in body.get("nodes", []):
        assert node["id"] not in forbidden, f"organization B entity leaked as a node: {node}"
    for memory in [*body.get("linked_memories", []), *body.get("memories", [])]:
        assert memory["id"] not in forbidden, f"organization B memory leaked: {memory}"
    emitted = {(edge["source"], edge["target"]) for edge in body.get("edges", [])}
    assert graph.organization_b_edge not in emitted, (
        f"organization B edge leaked into the response: {emitted}"
    )


@requires_db
async def test_traverse_with_a_name_shared_by_two_organizations_serves_only_the_caller(
    client: AsyncClient, seeded_graph: _SeededGraph
) -> None:
    """The caller asked for a name organization B also uses; only A's row may come back."""
    response = await client.get(
        "/v1/graph/traverse",
        headers=_identity(seeded_graph.organization_a, seeded_graph.user_a),
        params={"source": seeded_graph.shared_name},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["root_entity"]["id"] == str(seeded_graph.entity_a)
    assert {node["id"] for node in body["nodes"]} >= {
        str(seeded_graph.entity_a),
        str(seeded_graph.neighbour_a),
    }
    assert {memory["id"] for memory in body["linked_memories"]} == {str(seeded_graph.memory_a)}
    _assert_organization_b_absent(body, seeded_graph)


@requires_db
async def test_traverse_cannot_reach_an_entity_that_exists_only_in_another_organization(
    client: AsyncClient, seeded_graph: _SeededGraph
) -> None:
    """A name that only organization B has must read as absent, not as found."""
    response = await client.get(
        "/v1/graph/traverse",
        headers=_identity(seeded_graph.organization_a, seeded_graph.user_a),
        params={"source": seeded_graph.b_only_name},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("error") == "Root entity not found"
    assert body["nodes"] == [] and body["edges"] == [] and body["linked_memories"] == []
    _assert_organization_b_absent(body, seeded_graph)


@requires_db
async def test_traverse_does_not_reload_nodes_or_memories_it_reached_by_reference(
    client: AsyncClient, seeded_graph: _SeededGraph
) -> None:
    """An organization A edge that points at B's entity must not drag B's row in."""
    response = await client.get(
        "/v1/graph/traverse",
        headers=_identity(seeded_graph.organization_a, seeded_graph.user_a),
        params={"source": seeded_graph.shared_name, "hops": 3},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    node_ids = {node["id"] for node in body["nodes"]}
    memory_ids = {memory["id"] for memory in body["linked_memories"]}
    assert str(seeded_graph.hidden_entity_b) not in node_ids
    assert str(seeded_graph.hidden_memory_b) not in memory_ids
    # Both edges are organization A's own rows and stay; the referenced entity
    # simply stops resolving, which is the whole point of the scoped reload.
    assert {(edge["source"], edge["target"]) for edge in body["edges"]} == {
        (str(seeded_graph.entity_a), str(seeded_graph.neighbour_a)),
        (str(seeded_graph.entity_a), str(seeded_graph.hidden_entity_b)),
    }
    _assert_organization_b_absent(body, seeded_graph)


@requires_db
async def test_entity_graph_for_the_actor_never_returns_another_organization(
    client: AsyncClient, seeded_graph: _SeededGraph
) -> None:
    """`/v1/entities/graph/{user_id}` is the per-user view and must stay per-user."""
    response = await client.get(
        f"/v1/entities/graph/{seeded_graph.user_a}",
        headers=_identity(seeded_graph.organization_a, seeded_graph.user_a),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert {node["id"] for node in body["nodes"]} == {
        str(seeded_graph.entity_a),
        str(seeded_graph.neighbour_a),
    }
    assert {(edge["source"], edge["target"]) for edge in body["edges"]} == {
        (str(seeded_graph.entity_a), str(seeded_graph.neighbour_a)),
        (str(seeded_graph.entity_a), str(seeded_graph.hidden_entity_b)),
    }
    _assert_organization_b_absent(body, seeded_graph)
    for node in body["nodes"]:
        if node["id"] == str(seeded_graph.entity_a):
            assert node["memory_count"] == 2
        else:
            assert node["memory_count"] == 0


@requires_db
async def test_entity_graph_rejects_a_user_id_that_is_not_the_authenticated_actor(
    client: AsyncClient, seeded_graph: _SeededGraph
) -> None:
    """The path user_id is caller-supplied, so it may only ever restate the actor."""
    response = await client.get(
        f"/v1/entities/graph/{seeded_graph.user_b}",
        headers=_identity(seeded_graph.organization_a, seeded_graph.user_a),
    )

    assert response.status_code == 403, response.text
    _assert_organization_b_absent(response.json(), seeded_graph)


@requires_db
async def test_entity_memories_never_return_a_memory_from_another_organization(
    client: AsyncClient, seeded_graph: _SeededGraph
) -> None:
    """An organization A link row pointing at B's memory must not resolve it."""
    response = await client.get(
        f"/v1/entities/graph/{seeded_graph.user_a}"
        f"/entity/{seeded_graph.entity_a}/memories",
        headers=_identity(seeded_graph.organization_a, seeded_graph.user_a),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entity_id"] == str(seeded_graph.entity_a)
    assert {memory["id"] for memory in body["memories"]} == {str(seeded_graph.memory_a)}
    _assert_organization_b_absent(body, seeded_graph)


@requires_db
async def test_entity_memories_reject_a_user_id_that_is_not_the_authenticated_actor(
    client: AsyncClient, seeded_graph: _SeededGraph
) -> None:
    response = await client.get(
        f"/v1/entities/graph/{seeded_graph.user_b}"
        f"/entity/{seeded_graph.entity_a}/memories",
        headers=_identity(seeded_graph.organization_a, seeded_graph.user_a),
    )

    assert response.status_code == 403, response.text
    _assert_organization_b_absent(response.json(), seeded_graph)
