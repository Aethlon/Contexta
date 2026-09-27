from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.errors import AuthorizationError
from contexta.models.account import OrganizationMember
from contexta.models.block import MemoryBlock, MemoryBlockRevision
from contexta.models.evidence import ImmutableRecordError
from contexta.models.identity import Agent, MemoryUser, Project
from contexta.models.session import Session
from contexta.repositories.base import TenantScopedRepository


class BlockVersionConflict(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_content(content: str, structured_data: Mapping[str, Any] | None) -> str:
    value = {
        "content": content,
        "structured_data": dict(structured_data) if structured_data is not None else None,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def _account_in_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(OrganizationMember.account_id).where(
            OrganizationMember.organization_id == tenant_id,
            OrganizationMember.account_id == account_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _parent_in_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    model: type[Any],
    record_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        select(model.id).where(model.id == record_id, model.organization_id == tenant_id)
    )
    return result.scalar_one_or_none() is not None


async def _validate_scope(
    session: AsyncSession, tenant_id: uuid.UUID, record: Any
) -> None:
    if record.organization_id != tenant_id:
        raise AuthorizationError("The block scope does not match the tenant.")
    for model, record_id in (
        (MemoryUser, record.memory_user_id),
        (Agent, record.agent_id),
        (Project, record.project_id),
        (Session, record.session_id),
    ):
        if record_id is not None and not await _parent_in_tenant(
            session, tenant_id, model, record_id
        ):
            raise AuthorizationError("A block scope parent is outside the tenant.")
    if record.account_id is not None and not await _account_in_tenant(
        session, tenant_id, record.account_id
    ):
        raise AuthorizationError("The account does not belong to the tenant.")
    created_by = getattr(record, "created_by", None)
    if created_by is not None and not await _account_in_tenant(
        session, tenant_id, created_by
    ):
        raise AuthorizationError("The revision creator does not belong to the tenant.")


class MemoryBlockRepository(TenantScopedRepository[MemoryBlock]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryBlock)

    async def _revision_in_tenant(
        self, revision_id: uuid.UUID, block_id: uuid.UUID
    ) -> bool:
        result = await self._session.execute(
            select(MemoryBlockRevision.id).where(
                MemoryBlockRevision.id == revision_id,
                MemoryBlockRevision.block_id == block_id,
                MemoryBlockRevision.organization_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def create(self, record: MemoryBlock) -> MemoryBlock:
        await _validate_scope(self._session, self.tenant_id, record)
        if record.current_revision_id is not None and not await self._revision_in_tenant(
            record.current_revision_id, record.id
        ):
            raise AuthorizationError("The current revision is outside the block.")
        return await super().create(record)

    async def update_by_id(
        self, record_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        values = dict(values)
        protected = {
            "organization_id",
            "account_id",
            "memory_user_id",
            "user_id",
            "agent_id",
            "project_id",
            "session_id",
        }
        if "organization_id" in values and values["organization_id"] != self.tenant_id:
            raise AuthorizationError("The block scope does not match the tenant.")
        if "metadata" in values:
            values = {**values, "metadata_": values.pop("metadata")}
        if protected.intersection(values) - {"organization_id"}:
            raise AuthorizationError("The block scope is immutable.")
        if (
            "current_revision_id" in values
            and values["current_revision_id"] is not None
            and not await self._revision_in_tenant(values["current_revision_id"], record_id)
        ):
            raise AuthorizationError("The current revision is outside the block.")
        return await super().update_by_id(record_id, values)

    async def get_by_key(self, block_key: str) -> MemoryBlock | None:
        statement = select(MemoryBlock).where(MemoryBlock.block_key == block_key)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def _next_revision_number(self, block_id: uuid.UUID) -> int:
        statement = select(func.max(MemoryBlockRevision.revision_number)).where(
            MemoryBlockRevision.block_id == block_id,
            MemoryBlockRevision.organization_id == self.tenant_id,
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one() or 0)

    async def create_with_revision(
        self,
        block: MemoryBlock | None = None,
        content: str | None = None,
        *,
        structured_data: Mapping[str, Any] | None = None,
        model_version: str | None = None,
        source_authority: str = "unknown",
        source_origin: str = "unknown",
        created_by: uuid.UUID | None = None,
        expected_version: int | None = None,
        **block_values: Any,
    ) -> tuple[MemoryBlock, MemoryBlockRevision]:
        if block is None:
            values = dict(block_values)
            if "metadata" in values:
                values["metadata_"] = values.pop("metadata")
            values.setdefault("organization_id", self.tenant_id)
            block = MemoryBlock(**values)
        else:
            values = dict(block_values)
            if "metadata" in values:
                values["metadata_"] = values.pop("metadata")
            for key, value in values.items():
                if getattr(block, key, None) is None:
                    setattr(block, key, value)
        if block.organization_id is None:
            block.organization_id = self.tenant_id
        if block.organization_id != self.tenant_id:
            raise AuthorizationError("The block scope does not match the tenant.")
        if expected_version is not None and (block.current_version or 0) != expected_version:
            raise BlockVersionConflict("The block version does not match.")
        if block.current_revision_id is not None:
            raise BlockVersionConflict("The block already has a current revision.")
        now = _utcnow()
        revision_content = content if content is not None else (block.content or "")
        revision_data = (
            dict(structured_data)
            if structured_data is not None
            else (dict(block.structured_data) if block.structured_data is not None else None)
        )
        block.content = revision_content
        block.structured_data = revision_data
        block.content_hash = _hash_content(revision_content, revision_data)
        block.valid_from = block.valid_from or now
        block.source_authority = block.source_authority or source_authority
        block.source_origin = block.source_origin or source_origin
        created = await self.create(block)
        revision = MemoryBlockRevision(
            organization_id=self.tenant_id,
            block_id=created.id,
            account_id=created.account_id,
            memory_user_id=created.memory_user_id,
            user_id=created.user_id,
            agent_id=created.agent_id,
            project_id=created.project_id,
            session_id=created.session_id,
            revision_number=1,
            content=revision_content,
            structured_data=revision_data,
            model_version=model_version,
            source_authority=source_authority,
            source_origin=source_origin,
            created_by=created_by,
            valid_from=now,
            metadata_=created.metadata_,
        )
        self._session.add(revision)
        await self._session.flush()
        created.current_revision_id = revision.id
        created.current_version = revision.revision_number
        created.updated_at = now
        await self._session.flush()
        return created, revision

    async def append_revision(
        self,
        block_id: uuid.UUID,
        content: str,
        *,
        structured_data: Mapping[str, Any] | None = None,
        model_version: str | None = None,
        source_authority: str = "unknown",
        source_origin: str = "unknown",
        created_by: uuid.UUID | None = None,
        expected_version: int | None = None,
    ) -> MemoryBlockRevision | None:
        statement = select(MemoryBlock).where(MemoryBlock.id == block_id)
        result = await self._session.execute(
            self._scope_select(statement).with_for_update()
        )
        block = result.scalar_one_or_none()
        if block is None:
            return None
        if expected_version is not None and (block.current_version or 0) != expected_version:
            raise BlockVersionConflict("The block version does not match.")
        now = _utcnow()
        revision_number = max(
            block.current_version or 0,
            await self._next_revision_number(block.id),
        ) + 1
        revision_data = dict(structured_data) if structured_data is not None else None
        revision = MemoryBlockRevision(
            organization_id=self.tenant_id,
            block_id=block.id,
            account_id=block.account_id,
            memory_user_id=block.memory_user_id,
            user_id=block.user_id,
            agent_id=block.agent_id,
            project_id=block.project_id,
            session_id=block.session_id,
            revision_number=revision_number,
            content=content,
            structured_data=revision_data,
            model_version=model_version,
            source_authority=source_authority,
            source_origin=source_origin,
            created_by=created_by,
            supersedes_revision_id=block.current_revision_id,
            valid_from=now,
            metadata_=block.metadata_,
        )
        self._session.add(revision)
        await self._session.flush()
        block.content = content
        block.structured_data = revision_data
        block.content_hash = revision.content_hash
        block.model_version = model_version
        block.source_authority = source_authority
        block.source_origin = source_origin
        block.current_revision_id = revision.id
        block.current_version = revision_number
        block.updated_at = now
        await self._session.flush()
        return revision

    async def get_current_revision(self, block_id: uuid.UUID) -> MemoryBlockRevision | None:
        block = await self.get_by_id(block_id)
        if block is None:
            return None
        statement = (
            select(MemoryBlockRevision)
            .join(MemoryBlock, MemoryBlock.current_revision_id == MemoryBlockRevision.id)
            .where(
                MemoryBlock.id == block_id,
                MemoryBlock.organization_id == self.tenant_id,
                MemoryBlockRevision.organization_id == self.tenant_id,
            )
        )
        result = await self._session.execute(statement)
        revision = result.scalar_one_or_none()
        if revision is not None:
            return revision
        statement = (
            select(MemoryBlockRevision)
            .where(
                MemoryBlockRevision.block_id == block_id,
                MemoryBlockRevision.organization_id == self.tenant_id,
            )
            .order_by(MemoryBlockRevision.revision_number.desc())
        )
        result = await self._session.execute(statement)
        return result.scalars().first()

    async def list_revisions(self, block_id: uuid.UUID) -> list[MemoryBlockRevision]:
        statement = (
            select(MemoryBlockRevision)
            .where(
                MemoryBlockRevision.block_id == block_id,
                MemoryBlockRevision.organization_id == self.tenant_id,
            )
            .order_by(MemoryBlockRevision.revision_number)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def set_status(self, block_id: uuid.UUID, status: str) -> int:
        return await self.update_by_id(block_id, {"status": status})


class MemoryBlockRevisionRepository(TenantScopedRepository[MemoryBlockRevision]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(
            session=session,
            tenant_id=tenant_id,
            model=MemoryBlockRevision,
        )

    async def _block_in_tenant(self, block_id: uuid.UUID) -> bool:
        return await _parent_in_tenant(
            self._session, self.tenant_id, MemoryBlock, block_id
        )

    async def create(self, record: MemoryBlockRevision) -> MemoryBlockRevision:
        if record.organization_id is None:
            record.organization_id = self.tenant_id
        if not await self._block_in_tenant(record.block_id):
            raise AuthorizationError("The block does not belong to the tenant.")
        await _validate_scope(self._session, self.tenant_id, record)
        if record.revision_number is None:
            statement = select(func.max(MemoryBlockRevision.revision_number)).where(
                MemoryBlockRevision.block_id == record.block_id,
                MemoryBlockRevision.organization_id == self.tenant_id,
            )
            result = await self._session.execute(statement)
            record.revision_number = int(result.scalar_one() or 0) + 1
        if record.supersedes_revision_id is not None:
            parent = await self.get_by_id(record.supersedes_revision_id)
            if parent is None or parent.block_id != record.block_id:
                raise AuthorizationError("The parent revision is outside the block.")
        return await super().create(record)

    async def get_for_block(
        self, block_id: uuid.UUID, revision_number: int
    ) -> MemoryBlockRevision | None:
        statement = select(MemoryBlockRevision).where(
            MemoryBlockRevision.block_id == block_id,
            MemoryBlockRevision.revision_number == revision_number,
        )
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def get_by_hash(self, content_hash: str) -> Sequence[MemoryBlockRevision]:
        statement = select(MemoryBlockRevision).where(
            MemoryBlockRevision.content_hash == content_hash
        )
        result = await self._session.execute(
            self._scope_select(statement).order_by(
                MemoryBlockRevision.created_at.desc()
            )
        )
        return result.scalars().all()

    async def list_for_block(self, block_id: uuid.UUID) -> list[MemoryBlockRevision]:
        statement = (
            select(MemoryBlockRevision)
            .where(
                MemoryBlockRevision.block_id == block_id,
                MemoryBlockRevision.organization_id == self.tenant_id,
            )
            .order_by(MemoryBlockRevision.revision_number)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def update_by_id(self, record_id: uuid.UUID, values: dict[str, Any]) -> int:
        raise ImmutableRecordError("MemoryBlockRevision records are immutable")

    async def delete_by_id(self, record_id: uuid.UUID) -> int:
        raise ImmutableRecordError("MemoryBlockRevision records are immutable")


MemoryBlockVersionRepository = MemoryBlockRevisionRepository
BlockRepository = MemoryBlockRepository

__all__ = [
    "BlockRepository",
    "BlockVersionConflict",
    "MemoryBlockRepository",
    "MemoryBlockRevisionRepository",
    "MemoryBlockVersionRepository",
]
