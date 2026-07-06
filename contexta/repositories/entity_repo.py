"""Entity repository with tenant-scoped data access.

Provides CRUD and query operations for Entity, EntityEdge, and
MemoryEntityLink models, always enforcing organization_id isolation.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from contexta.core.types import EntityType
from contexta.repositories.base import TenantScopedRepository

# Imports will resolve once task 1.3 completes the model definitions.
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink


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
    ) -> Sequence[EntityEdge]:
        """Retrieve all edges (incoming and outgoing) for an entity."""
        stmt = select(self._model).where(
            (self._model.source_entity_id == entity_id)
            | (self._model.target_entity_id == entity_id)
        )
        stmt = self._scope_select(stmt)
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
        # MemoryEntityLink may not have org_id; use base select without scope
        # if the model lacks organization_id. For now, assume it has it.
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_memories_for_entity(
        self,
        entity_id: uuid.UUID,
    ) -> Sequence[MemoryEntityLink]:
        """Retrieve all memory links for an entity."""
        stmt = select(self._model).where(self._model.entity_id == entity_id)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()
