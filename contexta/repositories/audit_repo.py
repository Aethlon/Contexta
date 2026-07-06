"""Audit log repository with tenant-scoped data access.

Provides CRUD and query operations for AuditLog records, always
enforcing organization_id isolation at the data access layer.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import select

from contexta.repositories.base import TenantScopedRepository

# Import will resolve once task 1.3 completes the model definitions.
from contexta.models.audit import AuditLog


class AuditRepository(TenantScopedRepository["AuditLog"]):
    """Tenant-scoped repository for AuditLog operations."""

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=AuditLog)

    async def get_by_actor(
        self,
        actor_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Retrieve audit entries for a specific actor."""
        stmt = (
            select(self._model)
            .where(self._model.actor_id == actor_id)
            .order_by(self._model.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def log(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID,
        operation_type: str,
        target_id: uuid.UUID | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        """Persist one significant operation audit entry."""
        record = AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            operation_type=operation_type,
            target_id=target_id,
            details=details or {},
        )
        return await self.create(record)

    async def get_by_target(
        self,
        target_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Retrieve audit entries for a specific target resource."""
        stmt = (
            select(self._model)
            .where(self._model.target_id == target_id)
            .order_by(self._model.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_operation(
        self,
        operation_type: str,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Retrieve audit entries for a specific operation type."""
        stmt = (
            select(self._model)
            .where(self._model.operation_type == operation_type)
            .order_by(self._model.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_in_range(
        self,
        start: datetime,
        end: datetime,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """Retrieve audit entries within a time range."""
        stmt = (
            select(self._model)
            .where(self._model.created_at >= start)
            .where(self._model.created_at <= end)
            .order_by(self._model.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()
