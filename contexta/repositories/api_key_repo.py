"""API Key repository with tenant-scoped data access.

Provides DB CRUD operations for ApiKeyRecord, always enforcing organization_id
isolation.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.api_key import ApiKeyRecord
from contexta.repositories.base import TenantScopedRepository


@dataclass
class CreatedApiKey:
    """API key creation result returning the raw token once along with the record."""

    token: str
    record: ApiKeyRecord


async def _publish_to_redis(
    *,
    token_hash: str,
    key_id: uuid.UUID,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    scopes: list[str] | tuple[str, ...],
) -> None:
    """Best-effort publish of API-key hash to Redis for Go gateway verification.

    Gateway reads `apikey:<sha256>` hash with fields
    key_id/tenant_id/actor_id/scopes/tier (see services/gateway/internal/auth/verifier.go).
    Failures are swallowed: Postgres remains source of truth.
    """
    try:
        import redis.asyncio as aioredis

        from contexta.config.settings import get_settings

        client = aioredis.from_url(get_settings().redis_url)
        try:
            await client.hset(
                f"apikey:{token_hash}",
                mapping={
                    "key_id": str(key_id),
                    "tenant_id": str(tenant_id),
                    "actor_id": str(actor_id),
                    "scopes": " ".join(scopes),
                    "tier": "standard",
                },
            )
        finally:
            await client.close()
    except Exception:  # noqa: BLE001 - Redis is a cache, never fail key creation
        pass


async def _invalidate_in_redis(*, token_hash: str) -> None:
    """Best-effort removal of API-key hash from Redis on revoke."""
    try:
        import redis.asyncio as aioredis

        from contexta.config.settings import get_settings

        client = aioredis.from_url(get_settings().redis_url)
        try:
            await client.delete(f"apikey:{token_hash}")
        finally:
            await client.close()
    except Exception:  # noqa: BLE001 - Postgres remains source of truth
        pass


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
            created_at=datetime.utcnow(),
        )
        persisted = await self.create(record)
        await _publish_to_redis(
            token_hash=token_hash,
            key_id=persisted.id,
            tenant_id=self.tenant_id,
            actor_id=actor_id,
            scopes=list(scopes),
        )
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
        # Look up token hash first so Redis cache can be invalidated.
        existing = await self._session.get(ApiKeyRecord, key_id)
        stmt = (
            update(self._model)
            .where(self._model.id == key_id)
            .values(revoked_at=datetime.utcnow())
        )
        stmt = self._scope_update(stmt)
        result = await self._session.execute(stmt)
        if result.rowcount > 0 and existing is not None:
            await _invalidate_in_redis(token_hash=existing.token_hash)
        return result.rowcount > 0
