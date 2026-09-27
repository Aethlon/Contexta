from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.errors import AuthorizationError
from contexta.models.account import OrganizationMember
from contexta.models.evidence import Episode
from contexta.models.fact import MemoryFact
from contexta.models.identity import Agent, MemoryUser, Project
from contexta.models.session import Session
from contexta.repositories.base import TenantScopedRepository


class FactKeyMutationError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
    session: AsyncSession, tenant_id: uuid.UUID, record: MemoryFact
) -> None:
    if record.organization_id != tenant_id:
        raise AuthorizationError("The fact scope does not match the tenant.")
    for model, record_id in (
        (MemoryUser, record.memory_user_id),
        (Agent, record.agent_id),
        (Project, record.project_id),
        (Session, record.session_id),
        (Episode, record.episode_id),
    ):
        if record_id is not None and not await _parent_in_tenant(
            session, tenant_id, model, record_id
        ):
            raise AuthorizationError("A fact scope parent is outside the tenant.")
    if record.account_id is not None and not await _account_in_tenant(
        session, tenant_id, record.account_id
    ):
        raise AuthorizationError("The account does not belong to the tenant.")


class MemoryFactRepository(TenantScopedRepository[MemoryFact]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryFact)

    async def create(self, record: MemoryFact) -> MemoryFact:
        await _validate_scope(self._session, self.tenant_id, record)
        return await super().create(record)

    async def create_many(self, records: Sequence[MemoryFact]) -> Sequence[MemoryFact]:
        for record in records:
            await _validate_scope(self._session, self.tenant_id, record)
        return await super().create_many(records)

    async def get_by_fact_key(
        self,
        fact_key: str,
        *,
        user_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
        include_invalid: bool = False,
    ) -> MemoryFact | None:
        statement = select(MemoryFact).where(
            MemoryFact.fact_key == str(fact_key).strip()
        )
        query_time = _timestamp(as_of) if as_of is not None else None
        if user_id is not None:
            statement = statement.where(MemoryFact.user_id == user_id)
        if query_time is not None:
            statement = statement.where(
                MemoryFact.valid_from <= query_time,
                MemoryFact.known_at <= query_time,
            )
            if not include_invalid:
                statement = statement.where(
                    (MemoryFact.valid_to.is_(None)) | (MemoryFact.valid_to > query_time)
                )
        elif not include_invalid:
            statement = statement.where(
                MemoryFact.valid_to.is_(None),
                MemoryFact.status == "active",
            )
        result = await self._session.execute(
            self._scope_select(statement).order_by(
                MemoryFact.known_at.desc(), MemoryFact.created_at.desc()
            )
        )
        return result.scalars().first()

    async def get_current(
        self,
        user_id: uuid.UUID,
        *,
        as_of: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[MemoryFact]:
        statement = select(MemoryFact).where(MemoryFact.user_id == user_id)
        query_time = _timestamp(as_of) if as_of is not None else None
        if query_time is not None:
            statement = statement.where(
                MemoryFact.valid_from <= query_time,
                MemoryFact.known_at <= query_time,
                (MemoryFact.valid_to.is_(None)) | (MemoryFact.valid_to > query_time),
            )
        else:
            statement = statement.where(
                MemoryFact.valid_to.is_(None),
                MemoryFact.status == "active",
            )
        result = await self._session.execute(
            self._scope_select(statement)
            .order_by(MemoryFact.known_at.desc(), MemoryFact.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return result.scalars().all()

    async def list_for_subject(
        self, subject: str, *, user_id: uuid.UUID | None = None
    ) -> Sequence[MemoryFact]:
        statement = select(MemoryFact).where(MemoryFact.subject == subject)
        if user_id is not None:
            statement = statement.where(MemoryFact.user_id == user_id)
        result = await self._session.execute(
            self._scope_select(statement).order_by(MemoryFact.created_at.desc())
        )
        return result.scalars().all()

    async def list_for_predicate(
        self, predicate: str, *, user_id: uuid.UUID | None = None
    ) -> Sequence[MemoryFact]:
        statement = select(MemoryFact).where(MemoryFact.predicate == predicate)
        if user_id is not None:
            statement = statement.where(MemoryFact.user_id == user_id)
        result = await self._session.execute(
            self._scope_select(statement).order_by(MemoryFact.created_at.desc())
        )
        return result.scalars().all()

    async def create_fact(
        self,
        *,
        user_id: uuid.UUID,
        fact_key: str,
        subject: str,
        predicate: str,
        object: str,
        value: Any,
        account_id: uuid.UUID | None = None,
        memory_user_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        episode_id: uuid.UUID | None = None,
        value_type: str = "string",
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        known_at: datetime | None = None,
        source_authority: str = "unknown",
        source_origin: str = "unknown",
        model_version: str | None = None,
        source_id: str | None = None,
        source_message_id: str | None = None,
        lineage_id: str | None = None,
        confidence: float = 0.0,
        importance: float = 0.0,
        status: str = "active",
        metadata: Mapping[str, Any] | None = None,
        **values: Any,
    ) -> MemoryFact:
        normalized_key = str(fact_key).strip()
        if not normalized_key:
            raise ValueError("A fact key is required.")
        if not str(subject).strip() or not str(predicate).strip() or not str(object).strip():
            raise ValueError("A fact requires a subject, predicate, and object.")
        if not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("Fact confidence must be between zero and one.")
        if not 0.0 <= float(importance) <= 1.0:
            raise ValueError("Fact importance must be between zero and one.")
        now = _utcnow()
        timestamp = _timestamp(valid_from) if valid_from is not None else now
        end_timestamp = _timestamp(valid_to) if valid_to is not None else None
        if end_timestamp is not None and end_timestamp < timestamp:
            raise ValueError("The fact validity range is inverted.")
        record_values: dict[str, Any] = {
            "organization_id": self.tenant_id,
            "account_id": account_id,
            "memory_user_id": memory_user_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "project_id": project_id,
            "session_id": session_id,
            "episode_id": episode_id,
            "subject": str(subject).strip(),
            "predicate": str(predicate).strip(),
            "object": str(object).strip(),
            "value": value,
            "value_type": value_type,
            "fact_key": normalized_key,
            "valid_from": timestamp,
            "valid_to": end_timestamp,
            "known_at": _timestamp(known_at) if known_at is not None else now,
            "source_authority": source_authority,
            "source_origin": source_origin,
            "model_version": model_version,
            "source_id": source_id,
            "source_message_id": source_message_id,
            "lineage_id": lineage_id,
            "confidence": float(confidence),
            "importance": float(importance),
            "status": status,
            "metadata_": dict(metadata) if metadata is not None else None,
        }
        record_values.update(values)
        record_values["fact_key"] = normalized_key
        return await self.create(MemoryFact(**record_values))

    async def update_by_id(
        self, record_id: uuid.UUID, values: dict[str, Any]
    ) -> int:
        protected = {
            "subject",
            "predicate",
            "user_id",
            "organization_id",
            "account_id",
            "memory_user_id",
            "agent_id",
            "project_id",
            "session_id",
            "episode_id",
        }
        if protected.intersection(values):
            raise FactKeyMutationError("The fact identity is immutable")
        existing = await self.get_by_id(record_id)
        if existing is None:
            return 0
        if "fact_key" in values and values["fact_key"] != existing.fact_key:
            raise FactKeyMutationError("MemoryFact.fact_key is immutable")
        if "valid_to" in values and values["valid_to"] is not None:
            candidate_end = _timestamp(values["valid_to"])
            if candidate_end < _timestamp(existing.valid_from):
                raise ValueError("The fact validity range is inverted.")
            values = {**values, "valid_to": candidate_end}
        normalized = dict(values)
        if "metadata" in normalized:
            normalized["metadata_"] = normalized.pop("metadata")
        return await super().update_by_id(record_id, normalized)

    async def supersede(
        self,
        fact_id: uuid.UUID,
        valid_to: datetime,
        *,
        superseded_by_id: uuid.UUID | None = None,
    ) -> int:
        current = await self.get_by_id(fact_id)
        if current is None:
            return 0
        if superseded_by_id == fact_id:
            raise ValueError("A fact cannot supersede itself.")
        if current.valid_to is not None or current.status != "active":
            raise ValueError("Only an active fact can be superseded.")
        valid_to = _timestamp(valid_to)
        if valid_to < _timestamp(current.valid_from):
            raise ValueError("The fact validity range is inverted.")
        if superseded_by_id is not None:
            replacement = await self.get_by_id(superseded_by_id)
            if replacement is None:
                raise AuthorizationError("The replacement fact is outside the tenant.")
            if replacement.fact_key != current.fact_key:
                raise ValueError("A replacement must retain the fact key.")
        statement = update(MemoryFact).where(MemoryFact.id == fact_id).values(
            valid_to=valid_to,
            status="superseded",
            superseded_by_id=superseded_by_id,
        )
        result = await self._session.execute(self._scope_update(statement))
        return result.rowcount or 0

    async def replace(
        self,
        fact_id: uuid.UUID,
        *,
        subject: str,
        predicate: str,
        object: str,
        value: Any,
        valid_from: datetime | None = None,
        known_at: datetime | None = None,
        source_authority: str = "unknown",
        source_origin: str = "unknown",
        model_version: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> MemoryFact:
        current = await self.get_by_id(fact_id)
        if current is None:
            raise AuthorizationError("The fact is outside the tenant.")
        if current.valid_to is not None or current.status != "active":
            raise ValueError("Only an active fact can be replaced.")
        replacement = await self.create_fact(
            user_id=current.user_id,
            fact_key=current.fact_key,
            subject=subject,
            predicate=predicate,
            object=object,
            value=value,
            account_id=current.account_id,
            memory_user_id=current.memory_user_id,
            agent_id=current.agent_id,
            project_id=current.project_id,
            session_id=current.session_id,
            episode_id=current.episode_id,
            value_type=current.value_type,
            valid_from=valid_from,
            known_at=known_at,
            source_authority=source_authority,
            source_origin=source_origin,
            model_version=model_version,
            source_id=current.source_id,
            source_message_id=current.source_message_id,
            lineage_id=current.lineage_id,
            confidence=current.confidence,
            importance=current.importance,
            metadata=metadata,
        )
        await self.supersede(
            fact_id,
            valid_from or _utcnow(),
            superseded_by_id=replacement.id,
        )
        return replacement

    async def set_status(self, fact_id: uuid.UUID, status: str) -> int:
        return await self.update_by_id(fact_id, {"status": status})

    async def delete_by_id(self, record_id: uuid.UUID) -> int:
        current = await self.get_by_id(record_id)
        if current is not None and current.valid_to is None:
            raise ValueError("An active fact must be superseded before deletion.")
        return await super().delete_by_id(record_id)


FactRepository = MemoryFactRepository
ImmutableFactError = FactKeyMutationError

__all__ = [
    "FactKeyMutationError",
    "FactRepository",
    "ImmutableFactError",
    "MemoryFactRepository",
]
