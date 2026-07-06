"""Session repository with tenant-scoped data access.

Provides CRUD and query operations for Session records, always
enforcing organization_id isolation at the data access layer.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from contexta.repositories.base import TenantScopedRepository

# Import will resolve once task 1.3 completes the model definitions.
from contexta.models.session import Session


class SessionRepository(TenantScopedRepository["Session"]):
    """Tenant-scoped repository for Session operations."""

    def __init__(
        self,
        session,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=Session)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Session]:
        """Retrieve sessions for a specific user within the tenant."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .order_by(self._model.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_active_sessions(
        self,
        user_id: uuid.UUID,
    ) -> Sequence[Session]:
        """Retrieve sessions that have not ended for a user."""
        stmt = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .where(self._model.ended_at.is_(None))
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()
