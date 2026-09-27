from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.errors import AuthorizationError
from contexta.models.account import OrganizationMember
from contexta.models.evidence import (
    Episode,
    ImmutableRecordError,
    MemoryEvidence,
    SourceTurn,
)
from contexta.models.fact import MemoryFact
from contexta.models.identity import Agent, MemoryUser, Project
from contexta.models.ingestion import IngestionObservation
from contexta.models.session import Session
from contexta.repositories.base import TenantScopedRepository


async def _model_in_tenant(
    session: AsyncSession,
    model: type[Any],
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        select(model.id).where(model.id == record_id, model.organization_id == tenant_id)
    )
    return result.scalar_one_or_none() is not None


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


async def _validate_scope(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    record: Any,
) -> None:
    if record.organization_id != tenant_id:
        raise AuthorizationError("The record scope does not match the tenant.")
    for model, record_id in (
        (MemoryUser, record.memory_user_id),
        (Agent, record.agent_id),
        (Project, record.project_id),
        (Session, record.session_id),
    ):
        if record_id is not None and not await _model_in_tenant(
            session, model, tenant_id, record_id
        ):
            raise AuthorizationError("A scope parent is outside the tenant.")
    if record.account_id is not None and not await _account_in_tenant(
        session, tenant_id, record.account_id
    ):
        raise AuthorizationError("The account does not belong to the tenant.")


class EpisodeRepository(TenantScopedRepository[Episode]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=Episode)

    async def create(self, record: Episode) -> Episode:
        await _validate_scope(self._session, self.tenant_id, record)
        return await super().create(record)

    async def create_many(self, records: Sequence[Episode]) -> Sequence[Episode]:
        for record in records:
            await _validate_scope(self._session, self.tenant_id, record)
        return await super().create_many(records)

    async def get_by_external_id(self, external_id: str) -> Episode | None:
        statement = select(Episode).where(Episode.external_id == external_id)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def get_by_key(self, episode_key: str) -> Episode | None:
        statement = select(Episode).where(Episode.episode_key == episode_key)
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def list_for_session(self, session_id: uuid.UUID) -> Sequence[Episode]:
        statement = (
            select(Episode)
            .where(Episode.session_id == session_id)
            .order_by(Episode.occurred_at, Episode.created_at)
        )
        result = await self._session.execute(self._scope_select(statement))
        return result.scalars().all()

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Episode]:
        statement = (
            select(Episode)
            .where(Episode.user_id == user_id)
            .order_by(Episode.occurred_at, Episode.created_at)
        )
        result = await self._session.execute(self._scope_select(statement))
        return result.scalars().all()

    async def create_with_turns(
        self,
        episode: Episode,
        turns: Sequence[Mapping[str, Any] | SourceTurn],
    ) -> tuple[Episode, Sequence[SourceTurn]]:
        created = await self.create(episode)
        repository = SourceTurnRepository(self._session, self.tenant_id)
        created_turns = await repository.create_many(created.id, turns)
        return created, created_turns

    async def update_by_id(self, record_id: uuid.UUID, values: dict[str, Any]) -> int:
        raise ImmutableRecordError("Episode records are immutable")

    async def delete_by_id(self, record_id: uuid.UUID) -> int:
        raise ImmutableRecordError("Episode records are immutable")


class SourceTurnRepository(TenantScopedRepository[SourceTurn]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=SourceTurn)

    async def _episode_in_tenant(self, episode_id: uuid.UUID) -> bool:
        return await _model_in_tenant(
            self._session, Episode, self.tenant_id, episode_id
        )

    async def _validate_record(self, record: SourceTurn) -> None:
        if not await self._episode_in_tenant(record.episode_id):
            raise AuthorizationError("The episode does not belong to the tenant.")
        await _validate_scope(self._session, self.tenant_id, record)

    async def create(self, record: SourceTurn) -> SourceTurn:
        await self._validate_record(record)
        return await super().create(record)

    async def create_many(
        self,
        records_or_episode_id: Sequence[SourceTurn] | uuid.UUID,
        turns: Sequence[Mapping[str, Any] | SourceTurn] | None = None,
    ) -> Sequence[SourceTurn]:
        if turns is None:
            if isinstance(records_or_episode_id, SourceTurn):
                records = [records_or_episode_id]
            else:
                records = list(records_or_episode_id)
            for record in records:
                await self._validate_record(record)
            return await super().create_many(records)
        episode_id = records_or_episode_id
        if not isinstance(episode_id, uuid.UUID):
            raise TypeError("The episode id must be a UUID.")
        if not await self._episode_in_tenant(episode_id):
            raise AuthorizationError("The episode does not belong to the tenant.")
        records: list[SourceTurn] = []
        for index, turn in enumerate(turns):
            if isinstance(turn, SourceTurn):
                if turn.episode_id != episode_id:
                    raise ValueError("The source turn episode does not match.")
                record = turn
            else:
                record = SourceTurn(
                    organization_id=self.tenant_id,
                    episode_id=episode_id,
                    account_id=turn.get("account_id"),
                    memory_user_id=turn.get("memory_user_id"),
                    user_id=turn.get("user_id"),
                    agent_id=turn.get("agent_id"),
                    project_id=turn.get("project_id"),
                    session_id=turn.get("session_id"),
                    turn_index=int(turn.get("turn_index", turn.get("index", index))),
                    role=str(turn.get("role", "user")),
                    content=str(turn.get("content", turn.get("message", ""))),
                    source_turn_id=(
                        str(turn["source_turn_id"])
                        if turn.get("source_turn_id") is not None
                        else (
                            str(turn["external_id"])
                            if turn.get("external_id") is not None
                            else None
                        )
                    ),
                    occurred_at=turn.get("occurred_at"),
                    observed_at=turn.get("observed_at"),
                    source_authority=str(turn.get("source_authority", "unknown")),
                    source_origin=str(turn.get("source_origin", "unknown")),
                    model_version=turn.get("model_version"),
                    metadata_=turn.get("metadata_", turn.get("metadata")),
                )
            records.append(await self.create(record))
        return records

    async def get_by_source_id(self, source_turn_id: str) -> SourceTurn | None:
        statement = select(SourceTurn).where(
            SourceTurn.source_turn_id == source_turn_id
        )
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def list_for_episode(self, episode_id: uuid.UUID) -> Sequence[SourceTurn]:
        statement = (
            select(SourceTurn)
            .where(SourceTurn.episode_id == episode_id)
            .order_by(SourceTurn.turn_index)
        )
        result = await self._session.execute(self._scope_select(statement))
        return result.scalars().all()

    async def update_by_id(self, record_id: uuid.UUID, values: dict[str, Any]) -> int:
        raise ImmutableRecordError("SourceTurn records are immutable")

    async def delete_by_id(self, record_id: uuid.UUID) -> int:
        raise ImmutableRecordError("SourceTurn records are immutable")


class MemoryEvidenceRepository(TenantScopedRepository[MemoryEvidence]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryEvidence)

    async def _validate_parents(self, record: MemoryEvidence) -> None:
        await _validate_scope(self._session, self.tenant_id, record)
        for model, record_id, message in (
            (MemoryFact, record.fact_id, "fact"),
            (Episode, record.episode_id, "episode"),
            (SourceTurn, record.source_turn_id_record, "source turn"),
            (IngestionObservation, record.observation_id, "observation"),
        ):
            if record_id is not None and not await _model_in_tenant(
                self._session, model, self.tenant_id, record_id
            ):
                raise AuthorizationError(f"The {message} does not belong to the tenant.")
        if record.episode_id is not None and record.source_turn_id_record is not None:
            result = await self._session.execute(
                select(SourceTurn.episode_id).where(
                    SourceTurn.id == record.source_turn_id_record,
                    SourceTurn.organization_id == self.tenant_id,
                )
            )
            if result.scalar_one_or_none() != record.episode_id:
                raise ValueError("The evidence episode and source turn do not match.")
        if record.episode_id is not None and record.fact_id is not None:
            result = await self._session.execute(
                select(MemoryFact.episode_id).where(
                    MemoryFact.id == record.fact_id,
                    MemoryFact.organization_id == self.tenant_id,
                )
            )
            fact_episode_id = result.scalar_one_or_none()
            if fact_episode_id is not None and fact_episode_id != record.episode_id:
                raise ValueError("The evidence episode and fact do not match.")

    async def create(self, record: MemoryEvidence) -> MemoryEvidence:
        await self._validate_parents(record)
        return await super().create(record)

    async def create_many(
        self, records: Sequence[MemoryEvidence]
    ) -> Sequence[MemoryEvidence]:
        for record in records:
            await self._validate_parents(record)
        return await super().create_many(records)

    async def get_by_key(self, evidence_key: str) -> MemoryEvidence | None:
        statement = select(MemoryEvidence).where(
            MemoryEvidence.evidence_key == evidence_key
        )
        result = await self._session.execute(self._scope_select(statement))
        return result.scalar_one_or_none()

    async def list_for_fact(self, fact_id: uuid.UUID) -> Sequence[MemoryEvidence]:
        statement = select(MemoryEvidence).where(MemoryEvidence.fact_id == fact_id)
        result = await self._session.execute(
            self._scope_select(statement).order_by(MemoryEvidence.created_at)
        )
        return result.scalars().all()

    async def list_for_episode(self, episode_id: uuid.UUID) -> Sequence[MemoryEvidence]:
        statement = select(MemoryEvidence).where(MemoryEvidence.episode_id == episode_id)
        result = await self._session.execute(
            self._scope_select(statement).order_by(MemoryEvidence.created_at)
        )
        return result.scalars().all()

    async def list_for_turn(self, turn_id: uuid.UUID) -> Sequence[MemoryEvidence]:
        statement = select(MemoryEvidence).where(
            MemoryEvidence.source_turn_id_record == turn_id
        )
        result = await self._session.execute(
            self._scope_select(statement).order_by(MemoryEvidence.created_at)
        )
        return result.scalars().all()

    async def update_by_id(self, record_id: uuid.UUID, values: dict[str, Any]) -> int:
        raise ImmutableRecordError("MemoryEvidence records are immutable")

    async def delete_by_id(self, record_id: uuid.UUID) -> int:
        raise ImmutableRecordError("MemoryEvidence records are immutable")


EpisodeSourceTurnRepository = SourceTurnRepository
EvidenceRepository = MemoryEvidenceRepository

__all__ = [
    "EpisodeRepository",
    "EpisodeSourceTurnRepository",
    "EvidenceRepository",
    "MemoryEvidenceRepository",
    "SourceTurnRepository",
]
