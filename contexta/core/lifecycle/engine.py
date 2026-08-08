"""Memory lifecycle operations."""

from __future__ import annotations

import uuid
from typing import Protocol


class LifecycleRepository(Protocol):
    async def update_by_id(self, record_id: uuid.UUID, values: dict) -> int:
        ...

    async def delete_by_id(self, record_id: uuid.UUID) -> int:
        ...


class MemoryLifecycleEngine:
    """Pin, archive, restore, and delete tenant-scoped memories."""

    def __init__(self, repository: LifecycleRepository) -> None:
        self._repository = repository

    async def pin(self, memory_id: uuid.UUID) -> int:
        return await self._repository.update_by_id(memory_id, {"is_pinned": True})

    async def unpin(self, memory_id: uuid.UUID) -> int:
        return await self._repository.update_by_id(memory_id, {"is_pinned": False})

    async def archive(self, memory_id: uuid.UUID) -> int:
        return await self._repository.update_by_id(memory_id, {"is_archived": True})

    async def restore(self, memory_id: uuid.UUID) -> int:
        return await self._repository.update_by_id(memory_id, {"is_archived": False})

    async def delete(self, memory_id: uuid.UUID) -> int:
        return await self._repository.delete_by_id(memory_id)
