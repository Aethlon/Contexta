from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.artifact import ArtifactRecord
from contexta.repositories.base import TenantScopedRepository


class ArtifactRepository(TenantScopedRepository[ArtifactRecord]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=ArtifactRecord)

    async def list_artifacts(
        self,
        *,
        user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ArtifactRecord]:
        stmt = select(self._model).order_by(
            desc(self._model.created_at), desc(self._model.id)
        )
        if user_id is not None:
            stmt = stmt.where(self._model.user_id == user_id)
        stmt = self._scope_select(stmt).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_by_org(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ArtifactRecord]:
        return await self.list_artifacts(offset=offset, limit=limit)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ArtifactRecord]:
        return await self.list_artifacts(
            user_id=user_id, offset=offset, limit=limit
        )

    async def get_by_content_hash(
        self,
        content_hash: str,
    ) -> Sequence[ArtifactRecord]:
        stmt = (
            select(self._model)
            .where(self._model.content_hash == content_hash)
            .order_by(desc(self._model.created_at), desc(self._model.id))
        )
        stmt = self._scope_select(stmt)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def create_artifact(
        self,
        *,
        user_id: uuid.UUID,
        filename: str,
        mime_type: str,
        size_bytes: int,
        content_hash: str,
        storage_backend: str,
        storage_key: str,
        storage_etag: str | None,
        original_reference: str,
        metadata: Mapping[str, Any] | None,
        extracted_text: str | None,
        extraction_method: str | None,
        extraction_status: str,
        extraction_error: str | None,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            user_id=user_id,
            organization_id=self.tenant_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
            storage_backend=storage_backend,
            storage_key=storage_key,
            storage_etag=storage_etag,
            original_reference=original_reference,
            metadata_=dict(metadata or {}),
            extracted_text=extracted_text,
            extraction_method=extraction_method,
            extraction_status=extraction_status,
            extraction_error=extraction_error,
        )
        return await self.create(record)


__all__ = ["ArtifactRepository"]
