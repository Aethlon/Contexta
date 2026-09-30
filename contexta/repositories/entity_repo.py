"""Entity repository with tenant-scoped data access.

Provides CRUD and query operations for Entity, EntityEdge, and
MemoryEntityLink models, always enforcing organization_id isolation.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Integer,
    bindparam,
    cast,
    func,
    literal,
    literal_column,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from contexta.core.errors import AuthorizationError
from contexta.core.types import EntityType

# Imports will resolve once task 1.3 completes the model definitions.
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink
from contexta.models.memory import MemoryRecord
from contexta.repositories.base import TenantScopedRepository

# Minimum pg_trgm similarity for two entity names to be considered the same
# entity. pg_trgm and difflib.SequenceMatcher are unrelated scales, so this is
# not comparable to the resolver's old 0.85. Measured against the production
# corpus, 0.6 keeps the useful variant pairs (Kubernetes/Kubernets 0.615,
# Redis/Reddis 0.625, PostgreSQL/Postgre SQL 0.643, PostgreSQL/Postgres 0.667,
# "Priya Sharma"/"Priya Sharm" 0.786) while rejecting the conversational-noise
# band below it ("glad"/"phew glad" 0.500, Project Apollo/Apollo 0.467,
# PostgreSQL/Docker 0.444, "yep"/"yep caroline" 0.308). It deliberately sits
# above the pg_trgm.similarity_threshold default of 0.3 so the `name % :name`
# prefilter that drives ix_entity_name_trgm stays a superset of this cut-off
# and can never drop a row this threshold would have accepted.
TRGM_MATCH_THRESHOLD = 0.6

# Graph expansion reads at most this many edges per hop. The traversal engine
# already truncated to 20 in Python; capping in SQL keeps the full edge set of
# a hub entity from crossing the wire.
DEFAULT_NEIGHBOR_LIMIT = 20

# Defaults for `EntityEdgeRepository.walk_entity_graph`. `max_depth` matches
# the engine's `graph_depth` ceiling; `max_nodes` is the hard frontier cap the
# previous Python BFS lacked entirely.
DEFAULT_GRAPH_MAX_DEPTH = 2
DEFAULT_GRAPH_MAX_NODES = 200

# Single-query multi-hop expansion of `entity_edge`.
#
# Shape, and why each piece is here:
#   * `UNION` (not `UNION ALL`) deduplicates on (entity_id, depth), which is
#     what makes the recursion finite: the working set can hold at most
#     (distinct entities x max_depth + 1) rows however dense the graph is.
#   * `path` carries the nodes already on the current route so a node is never
#     re-added below itself. `ck_entity_edge_no_self_loop` means the immediate
#     self-hop cannot occur, but A-B-C-A would.
#   * The `LATERAL` is the per-node neighbour cap. It is what makes this
#     cheaper than the Python BFS it replaces, which had to fetch a node's
#     entire edge set and *then* slice `neighbors[:20]`. Each of its two
#     branches is a plain index scan: forward on `ix_entity_edge_scoped
#     (organization_id, source_entity_id, target_entity_id)`, reverse on
#     `ix_entity_edge_scoped_rev (organization_id, target_entity_id,
#     source_entity_id)`.
#   * Tenant scope is re-asserted in the anchor and in both branches of every
#     expansion, so a hop cannot leave the organization.
#   * `created_at DESC, edge_id DESC` inside the cap mirrors `get_neighbors`'s
#     recency preference and is a total order, so an unchanged graph always
#     yields the same frontier.
#   * The outer `ORDER BY depth, entity_id LIMIT :max_nodes` is the hard node
#     cap: expansion stops mattering once the frontier is this large, and the
#     caller can no longer be surprised by an unbounded result set.
_WALK_ENTITY_GRAPH_SQL = text(
    """
    WITH RECURSIVE walk(entity_id, depth, path) AS (
        SELECT s.id, 0, ARRAY[s.id]
        FROM entity s
        WHERE s.organization_id = :organization_id
          AND s.id = ANY(:seed_entity_ids)
      UNION
        SELECT hop.entity_id, walk.depth + 1, walk.path || hop.entity_id
        FROM walk
        CROSS JOIN LATERAL (
            SELECT neighbour AS entity_id
            FROM (
                SELECT e.target_entity_id AS neighbour, e.created_at, e.id AS edge_id
                FROM entity_edge e
                WHERE e.organization_id = :organization_id
                  AND e.source_entity_id = walk.entity_id
                  AND NOT e.target_entity_id = ANY(walk.path)
              UNION ALL
                SELECT e.source_entity_id, e.created_at, e.id
                FROM entity_edge e
                WHERE e.organization_id = :organization_id
                  AND e.target_entity_id = walk.entity_id
                  AND NOT e.source_entity_id = ANY(walk.path)
            ) candidates
            ORDER BY candidates.created_at DESC, candidates.edge_id DESC
            LIMIT :max_neighbors_per_node
        ) hop
        WHERE walk.depth < :max_depth
    )
    SELECT entity_id, min(depth) AS depth
    FROM walk
    GROUP BY entity_id
    ORDER BY min(depth), entity_id
    LIMIT :max_nodes
    """
).bindparams(
    # Types are declared explicitly because `text()` binds are untyped by
    # default and the asyncpg driver needs them to pick a codec for the uuid
    # seed array.
    bindparam("organization_id", type_=UUID(as_uuid=True)),
    bindparam("seed_entity_ids", type_=ARRAY(UUID(as_uuid=True))),
    bindparam("max_depth", type_=Integer),
    bindparam("max_nodes", type_=Integer),
    bindparam("max_neighbors_per_node", type_=Integer),
)


def _merge_attributes(
    base: Any,
    attributes: dict[str, Any] | None,
    mention_increment: int,
) -> Any:
    """Build the JSONB document an upsert should store for one entity.

    Shallow-merge ``attributes`` over ``base`` (incoming keys win), then add
    ``mention_increment`` to the resulting ``mention_count``, creating the key
    only when there is an increment to record. The increment goes last so a
    stale count carried in ``attributes`` cannot overwrite the arithmetic, and
    the ordering is identical for the insert and the update branch of an upsert
    -- the only difference between them is the base document.
    """
    merged = base
    if attributes:
        merged = merged.op("||", return_type=JSONB)(literal(dict(attributes), JSONB))
    if mention_increment:
        merged = merged.op("||", return_type=JSONB)(
            func.jsonb_build_object(
                "mention_count",
                func.coalesce(
                    cast(merged.op("->>")("mention_count"), Integer), 0
                )
                + mention_increment,
            )
        )
    return merged


class EntityRepository(TenantScopedRepository["Entity"]):
    """Tenant-scoped repository for Entity operations."""

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=Entity)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Entity]:
        """Retrieve entities for a specific user within the tenant."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_type(
        self,
        user_id: uuid.UUID,
        entity_type: EntityType,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Entity]:
        """Retrieve entities of a specific type for a user."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.entity_type == entity_type)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_name(
        self,
        user_id: uuid.UUID,
        name: str,
    ) -> Entity | None:
        """Find an entity by name for a user within the tenant."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.name == name)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_user(
        self,
        record_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Entity | None:
        """Retrieve one entity by id, scoped to the tenant and to the user."""
        stmt = (
            select(self._model)
            .where(self._model.id == record_id)
            .where(self._model.user_id == user_id)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many_by_ids(
        self,
        entity_ids: Sequence[uuid.UUID],
        *,
        user_id: uuid.UUID | None = None,
    ) -> Sequence[Entity]:
        """Retrieve entities by id, scoped to the tenant.

        The ids a graph walk collects come from edge rows, and an edge's
        `organization_id` is a denormalized copy that the foreign key to
        `entity.id` does not enforce, so an id arriving from a walk is not
        evidence of ownership. Re-reading the rows under the caller's own scope
        is what turns a reference into a node.
        """
        if not entity_ids:
            return []
        stmt = select(self._model).where(self._model.id.in_(entity_ids))
        if user_id is not None:
            stmt = stmt.where(self._model.user_id == user_id)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_name_ilike(self, user_id: uuid.UUID, pattern: str) -> Entity | None:
        """Find one entity whose name matches an SQL LIKE pattern, scoped to tenant and user."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.name.ilike(pattern))
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_name_fragment(
        self,
        name: str,
        *,
        limit: int = 5,
    ) -> Sequence[Entity]:
        """Find the tenant's entities whose name contains `name`, case-insensitively.

        Tenant-wide rather than per-user: this backs the "the caller's scope may
        not match the mention" fallback, so a name that is only attached to
        another user in this organization is still a legitimate hit.
        """
        stmt = (
            select(self._model)
            .where(self._model.name.ilike(f"%{name}%"))
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_names(
        self,
        user_id: uuid.UUID,
        names: Sequence[str],
    ) -> Sequence[Entity]:
        """Find entities by names (case-insensitive) for a user within the tenant."""
        if not names:
            return []
        from sqlalchemy import func
        lower_names = [n.lower() for n in names]
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(func.lower(self._model.name).in_(lower_names))
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_similar_names(
        self,
        user_id: uuid.UUID,
        name: str,
        *,
        threshold: float = TRGM_MATCH_THRESHOLD,
        limit: int = 5,
    ) -> Sequence[Entity]:
        """Find entities whose name is trigram-similar to ``name``, best match first.

        Scoped to the tenant and to the user, so resolution can never merge a
        mention into another user's entity. ``limit`` is the whole candidate
        pool the caller has to disambiguate between, so it is deliberately tiny.
        """
        if not name:
            return []
        score = func.similarity(self._model.name, name).label("name_similarity")
        stmt = (
            select(self._model, score)
            .where(self._model.user_id == user_id)
            # `name % :name` is the only similarity predicate ix_entity_name_trgm
            # can serve; the explicit threshold below then trims the rows the
            # GUC-default prefilter let through.
            .where(self._model.name.op("%", is_comparison=True)(name))
            .where(score > threshold)
            .order_by(score.desc(), self._model.id)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        rows = (await self._session.execute(stmt)).all()
        return [row[0] for row in rows]

    async def upsert_by_name(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        entity_type: str | EntityType,
        attributes: dict[str, Any] | None = None,
        mention_increment: int = 1,
    ) -> tuple[Entity, bool]:
        """Create-or-fetch one entity by case-insensitive name, in a single statement.

        Returns ``(entity, created)``, where ``created`` is False when the row
        already existed and the call only rolled its mention/attribute state
        forward. The ON CONFLICT target is the functional unique index
        ``uq_entity_identity (organization_id, user_id, lower(name))``, so the
        loser of a concurrent race re-reads the winner's row instead of
        inserting a second copy -- the read-then-write loop in
        ``BulkEntityResolver._seed_exact_matches`` cannot close that window,
        because the pre-resolution query and the caller's own INSERT are
        separate statements in separate sessions.

        ``attributes`` is shallow-merged over the stored JSONB, incoming keys
        winning. ``mention_increment`` is applied *after* that merge and adds to
        whatever ``mention_count`` the merged document holds (0 when absent) --
        identically on the insert and the update branch, so every call counts
        one mention whether or not the row already existed. Pass
        ``mention_increment=0`` to store ``attributes`` verbatim, or 0 with no
        ``attributes`` to test for existence without mutating.

        Note that the returned Entity is whatever ``RETURNING`` produced. If
        this session already has that entity loaded, SQLAlchemy's identity map
        will hand back the previously loaded instance rather than the refreshed
        row, so do not read merged attributes off the result after an earlier
        read in the same session.

        Tenant scoping is taken from the repository, never from the argument:
        ``organization_id`` is only accepted if it matches the authenticated
        tenant, and the INSERT and the conflict target both use
        ``self._tenant_id``. A caller cannot widen its own scope by passing a
        different organization.
        """
        if organization_id != self._tenant_id:
            raise AuthorizationError(
                "Access denied: upsert target belongs to a different organization."
            )
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Entity name must not be empty.")

        type_value = (
            entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        )
        now = datetime.now(UTC).replace(tzinfo=None)

        empty_document = literal({}, JSONB)
        # Insert branch: there is no stored row, so the base document is empty.
        # Update branch: the stored JSONB, or `{}` when the column is NULL.
        inserted_attributes = _merge_attributes(empty_document, attributes, mention_increment)
        updated_attributes = _merge_attributes(
            func.coalesce(
                cast(self._model.aggregated_attributes, JSONB), empty_document
            ),
            attributes,
            mention_increment,
        )

        stmt = (
            postgresql_insert(self._model)
            .values(
                id=uuid.uuid4(),
                organization_id=self._tenant_id,
                user_id=user_id,
                entity_type=type_value,
                name=clean_name,
                summary=None,
                status="active",
                aggregated_attributes=inserted_attributes,
                last_updated=now,
                created_at=now,
            )
            .on_conflict_do_update(
                # Matches the functional unique index on
                # (organization_id, user_id, lower(name)). PostgreSQL infers the
                # index from the expression list, which is why the conflict
                # target has to carry lower(name) rather than the raw column.
                index_elements=[
                    self._model.organization_id,
                    self._model.user_id,
                    func.lower(self._model.name),
                ],
                set_={
                    "aggregated_attributes": updated_attributes,
                    "last_updated": now,
                },
            )
            # `xmax = 0` is PostgreSQL's "this tuple was inserted, not updated"
            # test, and it is the only way to learn which branch of an upsert
            # fired. `pg_insert` cannot use `xmax = 0` as a conflict target
            # (it is not unique), so it is only ever read here in RETURNING.
            .returning(self._model, literal_column("xmax = 0").label("created"))
        )
        row = (await self._session.execute(stmt)).one()
        return row[0], bool(row[1])


class EntityEdgeRepository(TenantScopedRepository["EntityEdge"]):
    """Tenant-scoped repository for EntityEdge (relationship) operations."""

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=EntityEdge)

    async def get_edges_from(
        self,
        source_entity_id: uuid.UUID,
    ) -> Sequence[EntityEdge]:
        """Retrieve all outgoing edges from an entity."""
        stmt = select(self._model).where(
            self._model.source_entity_id == source_entity_id
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_edges_to(
        self,
        target_entity_id: uuid.UUID,
    ) -> Sequence[EntityEdge]:
        """Retrieve all incoming edges to an entity."""
        stmt = select(self._model).where(
            self._model.target_entity_id == target_entity_id
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_neighbors(
        self,
        entity_id: uuid.UUID,
        *,
        limit: int = DEFAULT_NEIGHBOR_LIMIT,
    ) -> Sequence[EntityEdge]:
        """Retrieve the most recent edges (incoming and outgoing) for an entity.

        ``ix_entity_edge_scoped`` and ``ix_entity_edge_scoped_rev`` serve the two
        sides of the OR. The row set is ordered and capped in SQL so a hub
        entity never transfers its whole edge set, and the ``id`` tie-break
        keeps repeated reads of an unchanged graph in the same order.
        """
        stmt = (
            select(self._model)
            .where(
                (self._model.source_entity_id == entity_id)
                | (self._model.target_entity_id == entity_id)
            )
            .order_by(self._model.created_at.desc(), self._model.id.desc())
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def bulk_get_neighbors(
        self,
        entity_ids: Sequence[uuid.UUID],
    ) -> Sequence[EntityEdge]:
        """Retrieve all edges connected to any entity in entity_ids in a single query."""
        if not entity_ids:
            return []
        stmt = select(self._model).where(
            (self._model.source_entity_id.in_(entity_ids))
            | (self._model.target_entity_id.in_(entity_ids))
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def walk_entity_graph(
        self,
        *,
        seed_entity_ids: Sequence[uuid.UUID],
        max_depth: int = DEFAULT_GRAPH_MAX_DEPTH,
        max_nodes: int = DEFAULT_GRAPH_MAX_NODES,
        max_neighbors_per_node: int = DEFAULT_NEIGHBOR_LIMIT,
    ) -> dict[uuid.UUID, int]:
        """Expand `seed_entity_ids` up to ``max_depth`` hops in ONE round trip.

        Returns ``{entity_id: hop_distance}`` for the seeds themselves
        (distance 0) and everything reachable within the cap, ordered by
        ``(distance, entity_id)``. Callers turn that into a depth-decayed
        weight per entity, so the hop distance is part of the return value
        rather than something to recompute.

        Replaces a per-node BFS that issued one `get_neighbors` query per
        visited node, per hop, and had no node cap at all. Two properties make
        this cheaper rather than merely tidier:

        * **The neighbour cap is applied inside the recursive step.** The old
          loop fetched a node's full edge set and only then took
          `neighbors[:20]`, so a hub paid for every edge it had. Here each hop
          stops after ``max_neighbors_per_node`` rows, and the two directions
          come from the two composite indexes added in revision 015.
        * **``max_nodes`` is a hard cap** on the frontier. The old walk grew
          with the graph and a dense component could pull an unbounded number
          of entities into a single retrieval.

        ``max_nodes`` bounds the result and, with ``max_depth`` and the
        per-node cap, the work: the recursive term deduplicates on
        ``(entity_id, depth)``, so the working set is at most
        (distinct entities x ``max_depth`` + 1) rows. The frontier is the
        cheapest ``max_nodes`` at the shallowest distances, so truncation
        always drops the deepest, least-connected candidates.

        Deterministic: ordering is by ``(distance, entity_id)`` on the way out
        and by ``(created_at DESC, edge_id DESC)`` inside the per-node cap, both
        total orders, so an unchanged graph always returns the same frontier.
        """
        seeds = list(dict.fromkeys(seed_entity_ids))
        if not seeds or max_depth < 0 or max_nodes <= 0:
            return {}
        if max_neighbors_per_node <= 0:
            raise ValueError("max_neighbors_per_node must be positive.")

        result = await self._session.execute(
            _WALK_ENTITY_GRAPH_SQL,
            {
                "organization_id": self._tenant_id,
                "seed_entity_ids": seeds,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "max_neighbors_per_node": max_neighbors_per_node,
            },
        )
        return {row[0]: row[1] for row in result.all()}

    async def get_existing_edges(
        self,
        entity_ids: Sequence[uuid.UUID],
        *,
        limit: int = 1000,
    ) -> Sequence[EntityEdge]:
        """Retrieve existing edges between any pair in the provided entity_ids.

        Both id lists are independently bounded, so this cross product is
        O(len(entity_ids)^2) and only affordable for the small id sets that
        callers pass. ``limit`` caps the rows returned.
        """
        if len(entity_ids) < 2:
            return []
        stmt = (
            select(self._model)
            .where(
                (self._model.source_entity_id.in_(entity_ids))
                & (self._model.target_entity_id.in_(entity_ids))
            )
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def insert_many_ignore_conflicts(
        self,
        edges: Sequence[EntityEdge],
    ) -> Sequence[EntityEdge]:
        """Insert edges, skipping ones the database already holds.

        Backstop for `uq_entity_edge_identity`: a concurrent writer that inserts
        the same (organization, source, target, relationship) between the
        resolver's in-memory check and this INSERT loses the race harmlessly
        instead of aborting the whole ingestion with an IntegrityError.

        Self-loops are dropped rather than inserted. `ON CONFLICT` only covers
        the unique index, so a self-loop would still trip
        `ck_entity_edge_no_self_loop` and fail the flush.
        """
        if not edges:
            return []
        for edge in edges:
            self._validate_tenant_ownership(edge)
        insertable = [
            {
                "id": edge.id,
                "source_entity_id": edge.source_entity_id,
                "target_entity_id": edge.target_entity_id,
                "relationship_type": edge.relationship_type,
                "organization_id": edge.organization_id,
            }
            for edge in edges
            if edge.source_entity_id != edge.target_entity_id
        ]
        if not insertable:
            return []
        stmt = (
            postgresql_insert(self._model)
            .values(insertable)
            .on_conflict_do_nothing(
                index_elements=[
                    self._model.organization_id,
                    self._model.source_entity_id,
                    self._model.target_entity_id,
                    self._model.relationship_type,
                ],
            )
            .returning(self._model)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()


class MemoryEntityLinkRepository(TenantScopedRepository["MemoryEntityLink"]):
    """Tenant-scoped repository for memory-entity link operations.

    Note: MemoryEntityLink is a junction table and may not have an
    organization_id column directly. Tenant scoping is enforced via
    joins to the parent Memory/Entity tables. For simplicity, this
    repository assumes the link table includes organization_id.
    """

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(
            session=session, tenant_id=tenant_id, model=MemoryEntityLink
        )

    async def get_entities_for_memory(
        self,
        memory_id: uuid.UUID,
    ) -> Sequence[MemoryEntityLink]:
        """Retrieve all entity links for a memory."""
        stmt = select(self._model).where(self._model.memory_id == memory_id)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def bulk_get_entities_for_memories(
        self,
        memory_ids: Sequence[uuid.UUID],
    ) -> Sequence[MemoryEntityLink]:
        """Retrieve all entity links for multiple memories in a single query."""
        if not memory_ids:
            return []
        stmt = select(self._model).where(self._model.memory_id.in_(memory_ids))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_memories_for_entity(
        self,
        entity_id: uuid.UUID,
        *,
        limit: int = 200,
    ) -> Sequence[MemoryEntityLink]:
        """Retrieve a bounded set of the most recent memory links for an entity.

        Served by `ix_mem_entity_link_entity (entity_id, memory_id)`, which
        exists because `entity_id` is the trailing column of the
        `(memory_id, entity_id)` primary key and cannot lead it.

        The cap makes the caller's `len(links)` an approximation: a hub entity
        with more than `limit` links reports `limit`, not its true degree. In
        the production corpus 0.33% of entities exceed 200 links, so the
        inverse-degree weight stays exact for the overwhelming majority.
        """
        stmt = (
            select(self._model)
            .where(self._model.entity_id == entity_id)
            .order_by(self._model.created_at.desc(), self._model.memory_id.desc())
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def bulk_get_memories_for_entities(
        self,
        entity_ids: Sequence[uuid.UUID],
    ) -> Sequence[MemoryEntityLink]:
        """Retrieve all memory links for multiple entities in a single query."""
        if not entity_ids:
            return []
        stmt = select(self._model).where(self._model.entity_id.in_(entity_ids))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def bulk_current_memory_ids_by_entity(
        self,
        entity_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Current memory ids per entity, for a whole frontier, in one query.

        `bulk_get_memories_for_entities` counts superseded links, because the
        links themselves carry no validity: currency lives on
        `memory_record.valid_to`, on the far side of the junction. A graph walk
        that weights an entity by how many memories mention it cannot afford to
        resolve those ids one at a time -- that is a hydrated `MemoryRecord` per
        id, 1024 dimensions and all -- so it either hydrates them in a budgeted
        loop or over-counts every entity a fact has since been corrected away
        from. This joins to the memory table once, filters `valid_to IS NULL`, and
        returns the ids alone.

        Both sides are tenant-scoped: the link's `organization_id` is a
        denormalised copy the foreign keys do not enforce, and the memory row it
        points at is the row whose validity is being trusted here.

        Entities with no current link are absent from the mapping rather than
        mapped to an empty list, matching `count_memories_per_entity`, so callers
        must read it with a zero default.
        """
        if not entity_ids:
            return {}
        stmt = (
            select(self._model.entity_id, self._model.memory_id)
            .join(MemoryRecord, self._model.memory_id == MemoryRecord.id)
            .where(self._model.entity_id.in_(entity_ids))
            .where(MemoryRecord.valid_to.is_(None))
            .where(MemoryRecord.organization_id == self._tenant_id)
            .order_by(self._model.entity_id, self._model.memory_id)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        grouped: dict[uuid.UUID, list[uuid.UUID]] = {}
        for entity_id, memory_id in result:
            grouped.setdefault(entity_id, []).append(memory_id)
        return grouped

    async def count_memories_per_entity(
        self,
        entity_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Count each entity's memory links in one pass, scoped to the tenant.

        Entities with no links are absent from the mapping rather than mapped to
        zero, so callers must read it with a zero default.
        """
        if not entity_ids:
            return {}
        stmt = (
            select(self._model.entity_id, func.count(self._model.memory_id))
            .where(self._model.entity_id.in_(entity_ids))
            .group_by(self._model.entity_id)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result}

