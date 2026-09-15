"""Memory repository with tenant-scoped data access.

Provides CRUD and query operations for MemoryRecord, always enforcing
organization_id isolation at the data access layer.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select

from contexta.core.crypto.vault import decrypt_content, encrypt_content
from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryState, MemoryType
from contexta.models.entity import EntityEdge
from contexta.models.memory import MemoryRecord
from contexta.repositories.base import TenantScopedRepository


class MemoryRepository(TenantScopedRepository["MemoryRecord"]):
    """Tenant-scoped repository for MemoryRecord operations."""

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryRecord)

    def _decrypt_record(self, record: MemoryRecord | None) -> MemoryRecord | None:
        if record is not None and record.content and record.content.startswith("enc:v1:"):
            record.content = decrypt_content(record.content, str(self._tenant_id))
        return record

    async def create(self, record: MemoryRecord) -> MemoryRecord:
        """Create a new memory record with on-the-fly authenticated encryption."""
        if record.content and not record.content.startswith("enc:v1:"):
            record.content = encrypt_content(record.content, str(self._tenant_id))
        created = await super().create(record)
        return self._decrypt_record(created)

    async def get_by_id(self, record_id: uuid.UUID) -> MemoryRecord | None:
        """Retrieve a single memory record by ID with on-the-fly decryption."""
        record = await super().get_by_id(record_id)
        return self._decrypt_record(record)

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
        records = result.scalars().all()
        for r in records:
            self._decrypt_record(r)
        return records

    async def get_by_vector_similarity(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve top candidate memories ordered by pgvector cosine distance directly in PostgreSQL."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.valid_to.is_(None))
            .where(self._model.is_archived.is_(False))
            .where(self._model.embedding.is_not(None))
            .order_by(self._model.embedding.cosine_distance(embedding))
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        records = result.scalars().all()
        for r in records:
            self._decrypt_record(r)
        return records

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
        """Persist a fully-scored memory and any graph edges."""
        record = MemoryRecord(
            user_id=user_id,
            organization_id=organization_id,
            memory_type=memory.memory_type.value if hasattr(memory.memory_type, "value") else str(memory.memory_type),
            title=memory.title,
            content=memory.content,
            structured_data=memory.structured_data,
            source_type=memory.source_type.value if hasattr(memory.source_type, "value") else str(memory.source_type),
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
            embedding=getattr(memory, "embedding", None),
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
        memory_type: MemoryType | str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve memories of a specific type for a user."""
        type_val = memory_type.value if hasattr(memory_type, "value") else str(memory_type)
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.memory_type == type_val)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_state(
        self,
        user_id: uuid.UUID,
        state: MemoryState | str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryRecord]:
        """Retrieve memories in a specific lifecycle state."""
        state_val = state.value if hasattr(state, "value") else str(state)
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.memory_state == state_val)
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
        records = result.scalars().all()
        for r in records:
            self._decrypt_record(r)
        return records

    async def get_unpinned_by_state(
        self,
        state: MemoryState | str,
        *,
        limit: int = 500,
    ) -> Sequence[MemoryRecord]:
        """Retrieve unpinned memories in a given state (for decay engine)."""
        state_val = state.value if hasattr(state, "value") else str(state)
        stmt = (
            select(self._model)
            .where(self._model.memory_state == state_val)
            .where(self._model.is_pinned == False)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def update_state(
        self,
        record_id: uuid.UUID,
        new_state: MemoryState | str,
    ) -> int:
        """Transition a memory to a new lifecycle state."""
        state_val = new_state.value if hasattr(new_state, "value") else str(new_state)
        return await self.update_by_id(record_id, {"memory_state": state_val})

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

    async def get_many_by_ids(
        self,
        record_ids: Sequence[uuid.UUID],
    ) -> Sequence[MemoryRecord]:
        """Concurrently retrieve multiple memory records by ID in a single query."""
        if not record_ids:
            return []
        stmt = select(self._model).where(self._model.id.in_(record_ids))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        records = result.scalars().all()
        for r in records:
            self._decrypt_record(r)
        return records

    async def apply_feedback(
        self,
        record_id: uuid.UUID,
        signal: str,
        user_correction: str | None = None,
        penalty: float = 0.5,
    ) -> MemoryRecord | None:
        """Adjust memory utility score and confidence based on explicit user/agent feedback."""
        memory = await self.get_by_id(record_id)
        if memory is None:
            return None

        now = datetime.utcnow()
        if signal.lower() in {"positive", "up", "thumbs_up"}:
            new_utility = min(1.0, (memory.utility_score or 0.0) + 0.25)
            new_conf = min(1.0, (memory.confidence or 0.5) + 0.1)
            await self.update_by_id(record_id, {
                "utility_score": new_utility,
                "confidence": new_conf,
                "last_accessed_at": now,
            })
            memory.utility_score = new_utility
            memory.confidence = new_conf
        else:
            new_utility = max(-1.0, (memory.utility_score or 0.0) - penalty)
            new_conf = max(0.1, (memory.confidence or 0.5) - 0.2)
            updates: dict[str, Any] = {
                "utility_score": new_utility,
                "confidence": new_conf,
                "last_accessed_at": now,
            }
            if user_correction or penalty >= 1.0 or new_utility <= -0.8:
                updates["valid_to"] = now
                updates["memory_state"] = MemoryState.ARCHIVED.value
                memory.memory_state = MemoryState.ARCHIVED.value
                memory.valid_to = now
            await self.update_by_id(record_id, updates)
            memory.utility_score = new_utility
            memory.confidence = new_conf

        return memory

    async def purge_all_for_org(self) -> dict[str, int]:
        """Cryptographically shreds and permanently purges all memories, graph nodes, and edges for this tenant."""
        from sqlalchemy import delete
        from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink

        # 1. Delete entity links
        sub_mem = select(MemoryRecord.id).where(MemoryRecord.organization_id == self._tenant_id)
        stmt_links = delete(MemoryEntityLink).where(MemoryEntityLink.memory_id.in_(sub_mem))
        res_links = await self._session.execute(stmt_links)

        # 2. Delete entity edges
        sub_ent = select(Entity.id).where(Entity.organization_id == self._tenant_id)
        stmt_edges = delete(EntityEdge).where(
            (EntityEdge.source_entity_id.in_(sub_ent)) | (EntityEdge.target_entity_id.in_(sub_ent))
        )
        res_edges = await self._session.execute(stmt_edges)

        # 3. Delete entities
        stmt_entities = delete(Entity).where(Entity.organization_id == self._tenant_id)
        res_entities = await self._session.execute(stmt_entities)

        # 4. Delete memories
        stmt_memories = delete(MemoryRecord).where(MemoryRecord.organization_id == self._tenant_id)
        res_memories = await self._session.execute(stmt_memories)

        await self._session.commit()

        return {
            "links_deleted": res_links.rowcount or 0,
            "edges_deleted": res_edges.rowcount or 0,
            "entities_deleted": res_entities.rowcount or 0,
            "memories_deleted": res_memories.rowcount or 0,
        }
