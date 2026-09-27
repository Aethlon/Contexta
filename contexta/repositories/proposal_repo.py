from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.proposal import (
    AdmissionState,
    MemoryProposal,
    ProposalValidationState,
)
from contexta.repositories.base import TenantScopedRepository


class ProposalIdempotencyConflictError(ValueError):
    pass


IdempotencyConflictError = ProposalIdempotencyConflictError


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _record_hash(record: MemoryProposal) -> str:
    value = {
        "proposal_type": record.proposal_type,
        "payload": record.payload,
        "evidence_ids": [str(item) for item in record.evidence_ids or []],
        "fact_keys": list(record.fact_keys or []),
        "supporting_ids": [str(item) for item in record.supporting_ids or []],
        "source_observation_ids": [str(item) for item in record.source_observation_ids or []],
        "target_memory_ids": [str(item) for item in record.target_memory_ids or []],
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _check_existing(existing: MemoryProposal, candidate: MemoryProposal) -> None:
    if _record_hash(existing) != _record_hash(candidate):
        raise ProposalIdempotencyConflictError(
            "The proposal idempotency key was already used with different content."
        )


class MemoryProposalRepository(TenantScopedRepository[MemoryProposal]):
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=MemoryProposal)

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> MemoryProposal | None:
        statement = select(self._model).where(
            self._model.idempotency_key == idempotency_key
        )
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def insert_idempotently(
        self, record: MemoryProposal
    ) -> tuple[MemoryProposal, bool]:
        self._validate_tenant_ownership(record)
        key = str(record.idempotency_key or "").strip()
        if not key:
            raise ValueError("A non-empty proposal idempotency key is required.")
        if len(key) > 255:
            raise ValueError("The proposal idempotency key cannot exceed 255 characters.")
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

    async def create_idempotently(self, record: MemoryProposal) -> MemoryProposal:
        created, _ = await self.insert_idempotently(record)
        return created

    async def get_for_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryProposal]:
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

    async def get_by_validation_state(
        self,
        validation_state: ProposalValidationState | str,
        *,
        user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[MemoryProposal]:
        state = (
            validation_state.value
            if isinstance(validation_state, Enum)
            else str(validation_state)
        )
        statement = select(self._model).where(self._model.validation_state == state)
        if user_id is not None:
            statement = statement.where(self._model.user_id == user_id)
        statement = (
            self._scope_select(statement)
            .order_by(self._model.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def get_review_queue(
        self,
        *,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> Sequence[MemoryProposal]:
        states = (
            ProposalValidationState.PENDING.value,
            ProposalValidationState.NEEDS_REVIEW.value,
        )
        statement = select(self._model).where(self._model.validation_state.in_(states))
        if user_id is not None:
            statement = statement.where(self._model.user_id == user_id)
        statement = (
            self._scope_select(statement)
            .order_by(self._model.risk_tier.desc(), self._model.created_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    get_pending = get_review_queue

    async def get_by_fact_key(
        self,
        fact_key: str,
        *,
        user_id: uuid.UUID | None = None,
    ) -> Sequence[MemoryProposal]:
        statement = select(self._model).where(self._model.fact_keys.contains([fact_key]))
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
    ) -> Sequence[MemoryProposal]:
        statement = select(self._model).where(self._model.evidence_ids.contains([evidence_id]))
        if user_id is not None:
            statement = statement.where(self._model.user_id == user_id)
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def update_validation_state(
        self,
        record_id: uuid.UUID,
        validation_state: ProposalValidationState | str,
        *,
        validation_errors: Sequence[Mapping[str, Any]] = (),
        now: datetime | None = None,
    ) -> int:
        state = (
            validation_state.value
            if isinstance(validation_state, Enum)
            else str(validation_state)
        )
        timestamp = now or _utcnow()
        values: dict[str, Any] = {
            "validation_state": state,
            "validation_errors": [dict(item) for item in validation_errors],
            "updated_at": timestamp,
        }
        if state == ProposalValidationState.VALIDATED.value:
            values["validated_at"] = timestamp
        if state == ProposalValidationState.REJECTED.value:
            values["rejected_at"] = timestamp
            values["admission_state"] = AdmissionState.REJECTED.value
        if state == ProposalValidationState.APPLIED.value:
            values["applied_at"] = timestamp
        return await self.update_by_id(record_id, values)

    async def mark_validated(
        self,
        record_id: uuid.UUID,
        *,
        validation_errors: Sequence[Mapping[str, Any]] = (),
        now: datetime | None = None,
    ) -> int:
        return await self.update_validation_state(
            record_id,
            ProposalValidationState.VALIDATED,
            validation_errors=validation_errors,
            now=now,
        )

    async def mark_needs_review(
        self,
        record_id: uuid.UUID,
        *,
        validation_errors: Sequence[Mapping[str, Any]] = (),
        now: datetime | None = None,
    ) -> int:
        return await self.update_validation_state(
            record_id,
            ProposalValidationState.NEEDS_REVIEW,
            validation_errors=validation_errors,
            now=now,
        )

    async def mark_rejected(
        self,
        record_id: uuid.UUID,
        *,
        reason: str = "",
        validation_errors: Sequence[Mapping[str, Any]] = (),
        now: datetime | None = None,
    ) -> int:
        errors = list(validation_errors)
        if reason:
            errors.append({"reason": reason})
        return await self.update_validation_state(
            record_id,
            ProposalValidationState.REJECTED,
            validation_errors=errors,
            now=now,
        )

    async def approve(
        self,
        record_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> int:
        return await self.update_validation_state(
            record_id,
            ProposalValidationState.APPROVED,
            now=now,
        )

    async def mark_applied(
        self,
        record_id: uuid.UUID,
        *,
        canonical_memory_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> int:
        timestamp = now or _utcnow()
        values: dict[str, Any] = {
            "validation_state": ProposalValidationState.APPLIED.value,
            "admission_state": AdmissionState.ADMITTED.value,
            "status": "applied",
            "applied_at": timestamp,
            "updated_at": timestamp,
        }
        if canonical_memory_id is not None:
            values["canonical_memory_id"] = canonical_memory_id
        return await self.update_by_id(record_id, values)


__all__ = [
    "IdempotencyConflictError",
    "MemoryProposalRepository",
    "ProposalIdempotencyConflictError",
]
