"""API Key repository with tenant-scoped data access.

Provides DB CRUD operations for ApiKeyRecord, always enforcing organization_id
isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.api_key import ApiKeyRecord
from contexta.repositories.base import TenantScopedRepository


@dataclass
class CreatedApiKey:
    """API key creation result returning the raw token once along with the record."""

    token: str
    record: ApiKeyRecord


class ApiKeyRepository(TenantScopedRepository[ApiKeyRecord]):
    """Tenant-scoped repository for ApiKeyRecord operations."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=ApiKeyRecord)

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a raw token using SHA-256."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def create_key(
        self,
        *,
        name: str,
        actor_id: uuid.UUID,
        scopes: list[str] | tuple[str, ...],
    ) -> CreatedApiKey:
        """Create a new API key for the tenant and persist its hash to the database."""
        token = f"mk_live_{secrets.token_urlsafe(32)}"
        token_hash = self.hash_token(token)
        prefix = token[:16]

        record = ApiKeyRecord(
            name=name.strip() or "Agent key",
            prefix=prefix,
            token_hash=token_hash,
            organization_id=self.tenant_id,
            actor_id=actor_id,
            scopes=list(scopes),
            created_at=datetime.now(timezone.utc),
        )
        persisted = await self.create(record)
        return CreatedApiKey(token=token, record=persisted)

    @classmethod
    async def find_by_token(
        cls,
        session: AsyncSession,
        raw_token: str,
    ) -> ApiKeyRecord | None:
        """Lookup an active, unrevoked API key by its raw token.

        This method does not enforce tenant scoping because the organization_id
        is not yet known.
        """
        token_hash = cls.hash_token(raw_token)
        stmt = select(ApiKeyRecord).where(
            ApiKeyRecord.token_hash == token_hash,
            ApiKeyRecord.revoked_at.is_(None),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(self) -> Sequence[ApiKeyRecord]:
        """List active, unrevoked API keys for the current tenant."""
        stmt = select(self._model).where(self._model.revoked_at.is_(None))
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def revoke(self, key_id: uuid.UUID) -> bool:
        """Revoke an API key by setting revoked_at timestamp."""
        stmt = (
            update(self._model)
            .where(self._model.id == key_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        stmt = self._scope_update(stmt)
        result = await self._session.execute(stmt)
        return result.rowcount > 0
