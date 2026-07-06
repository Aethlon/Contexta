"""Memory version repository.

Provides database access to store historical memory versions when a memory
is superseded.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.version import MemoryVersion


class MemoryVersionRepository:
    """Repository managing memory version records.

    This repository is not tenant-scoped directly because the target table
    does not have an organization_id column, but its operations are securely
    gated by the parent memory record's tenant ownership validation in the
    TruthMaintenanceEngine.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, record: MemoryVersion) -> MemoryVersion:
        """Persist a memory version record to the database."""
        self._session.add(record)
        await self._session.flush()
        return record
