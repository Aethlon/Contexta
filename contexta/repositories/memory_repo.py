"""Memory repository with tenant-scoped data access.

Provides CRUD and query operations for MemoryRecord, always enforcing
organization_id isolation at the data access layer.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update

from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryState, MemoryType
from contexta.models.entity import EntityEdge
from contexta.repositories.base import TenantScopedRepository

# Import will resolve once task 1.3 completes the model definitions.
from contexta.models.memory import MemoryRecord


class MemoryRepository(TenantScopedRepository["MemoryRecord"]):
    """Tenant-scoped repository for MemoryRecord operations."""

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryRecord)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve memories for a specific user within the tenant."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def persist(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        session_id: uuid.UUID | None,
        memory: ExtractedMemory,
        confidence: float,
        importance: float,
        utility_score: float = 0.0,
        is_pinned: bool = False,
        valid_from: datetime | None = None,
        graph_edges: Sequence[EntityEdge] = (),
    ) -> MemoryRecord:
        """Persist a fully-scored memory and any graph edges.

        The database migration maintains ``search_vector`` via trigger from
        title, content, and tags, so keyword indexing is populated on insert.
        Pinned memories are stored with ``is_pinned=True`` for later decay
        exclusion.
        """
        record = MemoryRecord(
            user_id=user_id,
            organization_id=organization_id,
            memory_type=memory.memory_type.value,
            title=memory.title,
            content=memory.content,
            structured_data=memory.structured_data,
            source_type=memory.source_type.value,
            confidence=confidence,
            importance=importance,
            utility_score=utility_score,
            tags=memory.tags,
            session_id=session_id,
            memory_state=MemoryState.ACTIVE.value,
            is_pinned=is_pinned,
            is_archived=False,
            valid_from=valid_from or datetime.utcnow(),
            valid_to=None,
        )
        persisted = await self.create(record)

        for edge in graph_edges:
            self._validate_tenant_ownership(edge)
            self._session.add(edge)

        if graph_edges:
            await self._session.flush()

        return persisted

    async def get_by_type(
        self,
        user_id: uuid.UUID,
        memory_type: MemoryType,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve memories of a specific type for a user."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.memory_type == memory_type)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_state(
        self,
        user_id: uuid.UUID,
        state: MemoryState,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve memories in a specific lifecycle state."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.memory_state == state)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_session(
        self,
        session_id: uuid.UUID,
    ) -> Sequence[MemoryRecord]:
        """Retrieve all memories extracted from a specific session."""
        stmt = select(self._model).where(self._model.session_id == session_id)
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_current_truths(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve current (non-superseded) memories for a user."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.valid_to.is_(None))
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_unpinned_by_state(
        self,
        state: MemoryState,
        *,
        limit: int = 500,
    ) -> Sequence[MemoryRecord]:
        """Retrieve unpinned memories in a given state (for decay engine)."""
        stmt = (
            select(self._model)
            .where(self._model.memory_state == state)
            .where(self._model.is_pinned == False)  # noqa: E712
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update_state(
        self,
        record_id: uuid.UUID,
        new_state: MemoryState,
    ) -> int:
        """Transition a memory to a new lifecycle state."""
        return await self.update_by_id(record_id, {"memory_state": new_state})

    async def touch_accessed(
        self,
        record_id: uuid.UUID,
        accessed_at: datetime,
    ) -> int:
        """Update the last_accessed_at timestamp for a memory."""
        return await self.update_by_id(
            record_id, {"last_accessed_at": accessed_at}
        )

    async def supersede(
        self,
        old_id: uuid.UUID,
        valid_to: datetime,
    ) -> int:
        """Mark a memory as superseded by setting its valid_to timestamp."""
        return await self.update_by_id(old_id, {"valid_to": valid_to})
