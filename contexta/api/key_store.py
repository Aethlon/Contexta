"""Development API-key registry for the contexta control plane.

DEPRECATED: This module is deprecated. Use ApiKeyRepository and the routes
in api_keys.py instead of this facade.
"""

from __future__ import annotations

import uuid
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.api_key import ApiKeyRecord
from contexta.repositories.api_key_repo import ApiKeyRepository, CreatedApiKey


async def create_api_key(
    *,
    name: str,
    organization_id: uuid.UUID,
    actor_id: uuid.UUID,
    scopes: list[str] | tuple[str, ...],
    session: AsyncSession,
) -> CreatedApiKey:
    """Create a new API key and store only its hash.

    DEPRECATED: Use ApiKeyRepository(session, organization_id).create_key(...) instead.
    """
    repo = ApiKeyRepository(session, organization_id)
    return await repo.create_key(name=name, actor_id=actor_id, scopes=scopes)


async def list_api_keys(
    *,
    organization_id: uuid.UUID,
    session: AsyncSession,
) -> Sequence[ApiKeyRecord]:
    """List API-key metadata for one tenant.

    DEPRECATED: Use ApiKeyRepository(session, organization_id).list_by_org() instead.
    """
    repo = ApiKeyRepository(session, organization_id)
    return await repo.list_by_org()


async def find_api_key(
    token: str,
    session: AsyncSession,
) -> ApiKeyRecord | None:
    """Find an API key by bearer token.

    DEPRECATED: Use ApiKeyRepository.find_by_token(session, token) instead.
    """
    return await ApiKeyRepository.find_by_token(session, token)
