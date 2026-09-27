from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.consolidation import ConsolidatedObservation
from contexta.models.proposal import AdmissionState, ProposalValidationState
from contexta.repositories.base import TenantScopedRepository


class ObservationIdempotencyConflictError(ValueError):
    pass


ConsolidationIdempotencyConflictError = ObservationIdempotencyConflictError


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _record_hash(record: ConsolidatedObservation) -> str:
    value = {
        "content": record.content,
        "structured_data": record.structured_data,
        "evidence_ids": [str(item) for item in record.evidence_ids or []],
        "supporting_ids": [str(item) for item in record.supporting_ids or []],
        "source_observation_ids": [str(item) for item in record.source_observation_ids or []],
        "fact_keys": list(record.fact_keys or []),
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _check_existing(
    existing: ConsolidatedObservation,
    candidate: ConsolidatedObservation,
) -> None:
    if _record_hash(existing) != _record_hash(candidate):
        raise ObservationIdempotencyConflictError(
            "The observation idempotency key was already used with different content."
        )


class ConsolidatedObservationRepository(TenantScopedRepository[ConsolidatedObservation]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(
            session=session,
            tenant_id=tenant_id,
            model=ConsolidatedObservation,
        )

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> ConsolidatedObservation | None:
        statement = select(self._model).where(
            self._model.idempotency_key == idempotency_key
        )
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def insert_idempotently(
        self, record: ConsolidatedObservation
    ) -> tuple[ConsolidatedObservation, bool]:
        self._validate_tenant_ownership(record)
        key = str(record.idempotency_key or "").strip()
        if not key:
            raise ValueError("A non-empty observation idempotency key is required.")
        if len(key) > 255:
            raise ValueError("The observation idempotency key cannot exceed 255 characters.")
        record.idempotency_key = key
        record.id = record.id or uuid.uuid4()
        record.updated_at = _utcnow()
        existing = await self.get_by_idempotency_key(key)
        if existing is not None:
            _check_existing(existing, record)
            return existing, False
        try:
            self._session.add(record)
            await self._session.flush()
        except IntegrityError:
            existing = await self.get_by_idempotency_key(key)
            if existing is None:
                raise
            _check_existing(existing, record)
            return existing, False
        return record, True

    async def create_idempotently(
        self, record: ConsolidatedObservation
    ) -> ConsolidatedObservation:
        created, _ = await self.insert_idempotently(record)
        return created

    async def get_for_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ConsolidatedObservation]:
        statement = (
            select(self._model)
            .where(self._model.user_id == user_id)
            .order_by(self._model.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def get_by_state(
        self,
        validation_state: ProposalValidationState | str,
        *,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> Sequence[ConsolidatedObservation]:
        state = validation_state.value if isinstance(validation_state, Enum) else str(validation_state)
        statement = select(self._model).where(self._model.validation_state == state)
        if user_id is not None:
            statement = statement.where(self._model.user_id == user_id)
        statement = (
            self._scope_select(statement)
            .order_by(self._model.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def get_by_supporting_id(
        self,
        supporting_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
    ) -> Sequence[ConsolidatedObservation]:
        statement = select(self._model).where(
            self._model.supporting_ids.contains([supporting_id])
        )
        if user_id is not None:
            statement = statement.where(self._model.user_id == user_id)
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def get_by_evidence_id(
        self,
        evidence_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
    ) -> Sequence[ConsolidatedObservation]:
        statement = select(self._model).where(
            self._model.evidence_ids.contains([evidence_id])
        )
        if user_id is not None:
            statement = statement.where(self._model.user_id == user_id)
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def update_state(
        self,
        record_id: uuid.UUID,
        validation_state: ProposalValidationState | str,
        *,
        admission_state: AdmissionState | str | None = None,
        now: datetime | None = None,
    ) -> int:
        timestamp = now or _utcnow()
        state = validation_state.value if isinstance(validation_state, Enum) else str(validation_state)
        values: dict[str, Any] = {
            "validation_state": state,
            "updated_at": timestamp,
        }
        if admission_state is not None:
            values["admission_state"] = (
                admission_state.value
                if isinstance(admission_state, Enum)
                else str(admission_state)
            )
        return await self.update_by_id(record_id, values)

    async def mark_applied(
        self,
        record_id: uuid.UUID,
        *,
        canonical_memory_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> int:
        timestamp = now or _utcnow()
        values: dict[str, Any] = {
            "status": "applied",
            "validation_state": ProposalValidationState.APPLIED.value,
            "updated_at": timestamp,
        }
        if canonical_memory_id is not None:
            values["applied_memory_id"] = canonical_memory_id
        return await self.update_by_id(record_id, values)


__all__ = [
    "ConsolidatedObservationRepository",
    "ConsolidationIdempotencyConflictError",
    "ObservationIdempotencyConflictError",
]
