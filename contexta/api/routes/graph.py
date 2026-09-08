"""Entity graph visualization and inspection routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.models.entity import Entity, MemoryEntityLink
from contexta.models.memory import MemoryRecord
from contexta.repositories.entity_repo import EntityEdgeRepository, EntityRepository

router = APIRouter()


class GraphNode(BaseModel):
    id: str
    name: str
    entity_type: str
    summary: str | None = None
    memory_count: int = 0


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship_type: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@router.get("/traverse")
@router.get("/graph/traverse")
async def traverse_graph(
    source: str,
    request: Request,
    hops: int = 2,
    relationship_types: str | None = None,
    direction: str = "both",
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Multi-hop entity graph traversal starting from a root entity name or UUID."""
    org_id = uuid.UUID(str(getattr(request.state, "organization_id", "00000000-0000-0000-0000-000000000001")))
    entity_repo = EntityRepository(session, tenant_id=org_id)
    edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
    link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)

    # 1. Find root entity by ID or name
    root_entity: Entity | None = None
    try:
        source_uuid = uuid.UUID(source)
        root_entity = await entity_repo.get_by_id(source_uuid)
    except ValueError:
        pass

    if not root_entity:
        stmt = select(Entity).where(Entity.name.ilike(source.strip()))
        res = await session.execute(stmt)
        root_entity = res.scalar_one_or_none()

    if not root_entity:
        return {
            "mode": "graph",
            "source": source,
            "error": "Root entity not found",
            "hops": hops,
            "nodes": [],
            "edges": [],
            "linked_memories": [],
        }

    # 2. Multi-hop traversal
    max_hops = min(3, max(1, hops))
    visited: set[uuid.UUID] = {root_entity.id}
    frontier: set[uuid.UUID] = {root_entity.id}
    all_nodes: dict[uuid.UUID, Entity] = {root_entity.id: root_entity}
    all_edges: list[dict[str, str]] = []
    rel_filter = set(r.strip() for r in relationship_types.split(",")) if relationship_types else None

    for _ in range(max_hops):
        if not frontier:
            break
        next_frontier: set[uuid.UUID] = set()
        for curr_id in frontier:
            neighbors = await edge_repo.get_neighbors(curr_id)
            for edge in neighbors:
                if rel_filter and edge.relationship_type not in rel_filter:
                    continue
                all_edges.append({
                    "source": str(edge.source_entity_id),
                    "target": str(edge.target_entity_id),
                    "relationship_type": edge.relationship_type,
                })
                for neighbor_id in (edge.source_entity_id, edge.target_entity_id):
                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        next_frontier.add(neighbor_id)
        frontier = next_frontier

    # Load missing node records
    missing_ids = [nid for nid in visited if nid not in all_nodes]
    if missing_ids:
        stmt = select(Entity).where(Entity.id.in_(missing_ids))
        res = await session.execute(stmt)
        for ent in res.scalars().all():
            all_nodes[ent.id] = ent

    # 3. Find linked memories
    all_entity_ids = list(all_nodes.keys())
    linked_memories: list[dict] = []
    if all_entity_ids:
        stmt = (
            select(MemoryRecord)
            .join(MemoryEntityLink, MemoryRecord.id == MemoryEntityLink.memory_id)
            .where(MemoryEntityLink.entity_id.in_(all_entity_ids))
            .distinct()
        )
        res = await session.execute(stmt)
        for mem in res.scalars().all():
            linked_memories.append({
                "id": str(mem.id),
                "title": mem.title,
                "content": mem.content,
                "memory_type": mem.memory_type,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
            })

    return {
        "mode": "graph",
        "root_entity": {
            "id": str(root_entity.id),
            "name": root_entity.name,
            "entity_type": root_entity.entity_type,
        },
        "hops": max_hops,
        "nodes": [
            {"id": str(e.id), "name": e.name, "entity_type": e.entity_type, "summary": e.summary}
            for e in all_nodes.values()
            if e is not None
        ],
        "edges": all_edges,
        "linked_memories": linked_memories,
    }


@router.get("/graph/{user_id}", response_model=GraphResponse)
async def get_entity_graph(
    user_id: uuid.UUID,
    request: Request,
    max_depth: int = 2,
    session: AsyncSession = Depends(get_db_session),
) -> GraphResponse:
    """Retrieve the entity graph for a user, including nodes and edges."""
    org_id = uuid.UUID(str(request.state.organization_id))

    entity_repo = EntityRepository(session, tenant_id=org_id)
    edge_repo = EntityEdgeRepository(session, tenant_id=org_id)

    entities = await entity_repo.get_by_user(user_id, limit=200)
    entity_ids = {e.id for e in entities}

    all_nodes: dict[uuid.UUID, Entity] = {e.id: e for e in entities}
    all_edges: set[tuple[uuid.UUID, uuid.UUID, str]] = set()
    visited: set[uuid.UUID] = set()
    frontier: set[uuid.UUID] = entity_ids

    for _ in range(max_depth):
        if not frontier:
            break
        next_frontier: set[uuid.UUID] = set()
        for eid in frontier:
            if eid in visited:
                continue
            visited.add(eid)
            neighbors = await edge_repo.get_neighbors(eid)
            for edge in neighbors:
                all_edges.add((edge.source_entity_id, edge.target_entity_id, edge.relationship_type))
                if edge.source_entity_id not in all_nodes:
                    all_nodes[edge.source_entity_id] = None
                    next_frontier.add(edge.source_entity_id)
                if edge.target_entity_id not in all_nodes:
                    all_nodes[edge.target_entity_id] = None
                    next_frontier.add(edge.target_entity_id)
        frontier = next_frontier - visited

    missing_ids = {eid for eid, ent in all_nodes.items() if ent is None}
    if missing_ids:
        stmt = select(Entity).where(Entity.id.in_(missing_ids))
        result = await session.execute(stmt)
        for ent in result.scalars().all():
            all_nodes[ent.id] = ent

    # Count memories per entity
    memory_counts: dict[uuid.UUID, int] = {}
    if all_nodes:
        stmt = (
            select(MemoryEntityLink.entity_id)
            .where(MemoryEntityLink.entity_id.in_(list(all_nodes.keys())))
        )
        result = await session.execute(stmt)
        for row in result:
            eid = row[0]
            memory_counts[eid] = memory_counts.get(eid, 0) + 1

    nodes = [
        GraphNode(
            id=str(ent.id),
            name=ent.name,
            entity_type=ent.entity_type,
            summary=ent.summary,
            memory_count=memory_counts.get(ent.id, 0),
        )
        for ent in all_nodes.values()
        if ent is not None
    ]

    edges = [
        GraphEdge(source=str(src), target=str(tgt), relationship_type=rel)
        for src, tgt, rel in all_edges
    ]

    return GraphResponse(nodes=nodes, edges=edges)


class EntityMemoriesResponse(BaseModel):
    entity_id: str
    entity_name: str
    memories: list[dict]


@router.get("/graph/{user_id}/entity/{entity_id}/memories")
async def get_entity_memories(
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> EntityMemoriesResponse:
    """Get all memories linked to a specific entity."""
    org_id = uuid.UUID(str(request.state.organization_id))

    entity_repo = EntityRepository(session, tenant_id=org_id)
    entity = await entity_repo.get_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

    # Get memory links for this entity
    from contexta.repositories.entity_repo import MemoryEntityLinkRepository
    link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
    links = await link_repo.get_memories_for_entity(entity_id)

    memories = []
    for link in links:
        stmt = select(MemoryRecord).where(MemoryRecord.id == link.memory_id)
        result = await session.execute(stmt)
        memory = result.scalar_one_or_none()
        if memory:
            memories.append({
                "id": str(memory.id),
                "title": memory.title,
                "memory_type": memory.memory_type,
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
            })

    return EntityMemoriesResponse(
        entity_id=str(entity.id),
        entity_name=entity.name,
        memories=memories,
    )
