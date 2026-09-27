from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError, UnboundExecutionError
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.models.ingestion import (
    IngestionAttempt,
    IngestionDeadLetter,
    IngestionObservation,
    IngestionOutboxEvent,
    IngestionSourceTurn,
)
from contexta.repositories.base import TenantScopedRepository

logger = logging.getLogger(__name__)

OBSERVATION_PENDING = "pending"
OBSERVATION_PROCESSING = "processing"
OBSERVATION_RETRYING = "retrying"
OBSERVATION_COMPLETED = "completed"
OBSERVATION_FAILED = "failed"
OBSERVATION_DEAD_LETTER = "dead_letter"
OUTBOX_PENDING = "pending"
OUTBOX_CLAIMED = "claimed"
OUTBOX_PUBLISHED = "published"
OUTBOX_FAILED = "failed"
OUTBOX_DEAD_LETTER = "dead_letter"


class IdempotencyConflictError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _naive_utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dialect_name(session: AsyncSession) -> str | None:
    try:
        bind = session.get_bind()
    except (AttributeError, TypeError, UnboundExecutionError):
        bind = getattr(session, "bind", None)
    dialect = getattr(bind, "dialect", None)
    name = getattr(dialect, "name", None)
    return name if isinstance(name, str) else None


def _with_skip_locked(statement: Any, session: AsyncSession) -> Any:
    if _dialect_name(session) in {"postgresql", "cockroachdb"}:
        return statement.with_for_update(skip_locked=True)
    return statement


def _request_hash(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None,
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any] | None,
    source: str,
) -> str:
    value = {
        "user_id": str(user_id),
        "session_id": str(session_id) if session_id is not None else None,
        "payload": dict(payload),
        "metadata": dict(metadata) if metadata is not None else None,
        "source": source,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_mapping(
    value: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    return json.loads(json.dumps(dict(value), default=str))


def _check_idempotency_hash(record: IngestionObservation, request_hash: str) -> None:
    if record.payload_hash and record.payload_hash != request_hash:
        raise IdempotencyConflictError(
            "The idempotency key was already used with a different observation."
        )


def _normalize_lease(lease_seconds: int) -> int:
    return max(1, int(lease_seconds))


class IngestionObservationRepository(TenantScopedRepository[IngestionObservation]):
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=IngestionObservation)

    async def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> IngestionObservation | None:
        statement = select(IngestionObservation).where(
            IngestionObservation.idempotency_key == idempotency_key
        )
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def insert_idempotently(
        self,
        *,
        idempotency_key: str | None,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        source: str = "api",
    ) -> tuple[IngestionObservation, bool]:
        key = (idempotency_key or str(uuid.uuid4())).strip()
        if not key:
            key = str(uuid.uuid4())
        payload_dict = _json_mapping(payload) or {}
        metadata_dict = _json_mapping(metadata)
        request_hash = _request_hash(
            user_id=user_id,
            session_id=session_id,
            payload=payload_dict,
            metadata=metadata_dict,
            source=source,
        )
        now = _utcnow()
        values = {
            "id": uuid.uuid4(),
            "organization_id": self.tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "idempotency_key": key,
            "payload_hash": request_hash,
            "payload": payload_dict,
            "metadata_": metadata_dict,
            "source": source,
            "status": OBSERVATION_PENDING,
            "attempt_count": 0,
            "next_attempt_at": now,
            "created_at": _naive_utcnow(),
            "updated_at": now,
        }
        if _dialect_name(self._session) == "postgresql":
            statement = (
                postgresql_insert(IngestionObservation)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        IngestionObservation.organization_id,
                        IngestionObservation.idempotency_key,
                    ]
                )
                .returning(IngestionObservation)
            )
            result = await self._session.execute(statement)
            record = result.scalar_one_or_none()
            if record is not None:
                return record, True
        else:
            existing = await self.get_by_idempotency_key(key)
            if existing is not None:
                _check_idempotency_hash(existing, request_hash)
                return existing, False
            record = IngestionObservation(**values)
            try:
                async with self._session.begin_nested():
                    self._session.add(record)
                    await self._session.flush()
                return record, True
            except IntegrityError:
                existing = await self.get_by_idempotency_key(key)
                if existing is None:
                    raise
                _check_idempotency_hash(existing, request_hash)
                return existing, False
        existing = await self.get_by_idempotency_key(key)
        if existing is None:
            raise RuntimeError("The idempotent observation insert did not return a row.")
        _check_idempotency_hash(existing, request_hash)
        return existing, False

    async def insert_observation(
        self,
        *,
        idempotency_key: str | None,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        source: str = "api",
    ) -> IngestionObservation:
        record, _ = await self.insert_idempotently(
            idempotency_key=idempotency_key,
            user_id=user_id,
            session_id=session_id,
            payload=payload,
            metadata=metadata,
            source=source,
        )
        return record

    async def claim(
        self,
        observation_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> IngestionAttempt | None:
        now = _utcnow()
        lease_until = now + timedelta(seconds=_normalize_lease(lease_seconds))
        statement = select(IngestionObservation).where(
            IngestionObservation.id == observation_id,
            IngestionObservation.status.in_(
                (OBSERVATION_PENDING, OBSERVATION_RETRYING, OBSERVATION_PROCESSING)
            ),
            or_(
                IngestionObservation.next_attempt_at.is_(None),
                IngestionObservation.next_attempt_at <= now,
            ),
            or_(
                IngestionObservation.lease_until.is_(None),
                IngestionObservation.lease_until <= now,
            ),
        )
        statement = self._scope_select(statement)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        observation = result.scalar_one_or_none()
        if observation is None:
            return None
        if max_attempts is not None and observation.attempt_count >= max_attempts:
            return None
        token = uuid.uuid4()
        # Derive the attempt number from stored attempts, not from the denormalized
        # counter. `uq_ingestion_attempt_observation_number` is the real constraint,
        # so a counter that is ever reset - or two claims that race - produces a
        # duplicate number and a UniqueViolationError, which then wedges the
        # observation. Reading MAX(attempt_number) here is authoritative and
        # self-healing.
        existing_max = await self._session.scalar(
            select(func.coalesce(func.max(IngestionAttempt.attempt_number), 0)).where(
                IngestionAttempt.observation_id == observation_id
            )
        )
        attempt_number = int(existing_max or 0) + 1
        observation.status = OBSERVATION_PROCESSING
        observation.attempt_count = max(int(observation.attempt_count or 0), attempt_number)
        observation.lease_owner = worker_id
        observation.lease_token = token
        observation.lease_until = lease_until
        observation.next_attempt_at = None
        observation.updated_at = now
        attempt = IngestionAttempt(
            organization_id=self.tenant_id,
            observation_id=observation.id,
            attempt_number=attempt_number,
            status=OBSERVATION_PROCESSING,
            worker_id=worker_id,
            lease_token=token,
            lease_until=lease_until,
            started_at=now,
        )
        self._session.add(attempt)
        try:
            await self._session.flush()
        except IntegrityError:
            # Another worker inserted the same attempt_number between our read and
            # our write. That worker owns this observation, so stand down cleanly
            # instead of raising a UniqueViolationError that wedges the row.
            await self._session.rollback()
            logger.info(
                "Claim lost the attempt_number race for observation %s; another worker owns it",
                observation_id,
            )
            return None
        return attempt

    async def claim_observation(
        self,
        observation_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> IngestionAttempt | None:
        return await self.claim(
            observation_id,
            worker_id,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

    async def complete_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_details: Mapping[str, Any] | None = None,
    ) -> IngestionAttempt | None:
        now = _utcnow()
        statement = select(IngestionAttempt).where(IngestionAttempt.id == attempt_id)
        # Scope on the selected table, not self._model - see fail_attempt().
        statement = statement.where(IngestionAttempt.organization_id == self._tenant_id)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        attempt = result.scalar_one_or_none()
        if attempt is None:
            return None
        if worker_id is not None and attempt.worker_id != worker_id:
            return None
        if lease_token is not None and attempt.lease_token != lease_token:
            return None
        if attempt.status == OBSERVATION_COMPLETED:
            return attempt
        attempt.status = OBSERVATION_COMPLETED
        attempt.finished_at = now
        attempt.error_type = error_type
        attempt.error_message = error_message
        attempt.error_details = _json_mapping(error_details)
        attempt.lease_until = None
        observation_statement = select(IngestionObservation).where(
            IngestionObservation.id == attempt.observation_id
        )
        observation_statement = self._scope_select(observation_statement)
        observation_statement = _with_skip_locked(observation_statement, self._session)
        observation_result = await self._session.execute(observation_statement)
        observation = observation_result.scalar_one_or_none()
        if observation is not None:
            observation.status = OBSERVATION_COMPLETED
            observation.completed_at = now
            observation.lease_owner = None
            observation.lease_token = None
            observation.lease_until = None
            observation.last_error = None
            observation.updated_at = now
        await self._session.flush()
        return attempt

    async def succeed_attempt(
        self, attempt_id: uuid.UUID
    ) -> IngestionAttempt | None:
        return await self.complete_attempt(attempt_id)

    async def fail_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_details: Mapping[str, Any] | None = None,
        retry_at: datetime | None = None,
        retry_delay_seconds: int = 60,
        max_attempts: int | None = None,
    ) -> IngestionAttempt | None:
        now = _utcnow()
        statement = select(IngestionAttempt).where(IngestionAttempt.id == attempt_id)
        # Scope on the table actually being selected. These methods live on
        # IngestionObservationRepository but query ingestion_attempt, so using
        # self._scope_select() (which filters on self._model == IngestionObservation)
        # produced a cross join against ingestion_observation with no join condition.
        # That multiplied rows and made scalar_one_or_none() raise
        # MultipleResultsFound, which permanently dead-lettered the observation.
        statement = statement.where(IngestionAttempt.organization_id == self._tenant_id)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        attempt = result.scalar_one_or_none()
        if attempt is None:
            return None
        if worker_id is not None and attempt.worker_id != worker_id:
            return None
        if lease_token is not None and attempt.lease_token != lease_token:
            return None
        if attempt.status == OBSERVATION_COMPLETED:
            return attempt
        attempt.status = OBSERVATION_FAILED
        attempt.finished_at = now
        attempt.error_type = error_type
        attempt.error_message = error_message
        attempt.error_details = _json_mapping(error_details)
        attempt.lease_until = None
        observation_statement = select(IngestionObservation).where(
            IngestionObservation.id == attempt.observation_id
        )
        observation_statement = self._scope_select(observation_statement)
        observation_statement = _with_skip_locked(observation_statement, self._session)
        observation_result = await self._session.execute(observation_statement)
        observation = observation_result.scalar_one_or_none()
        if observation is None:
            await self._session.flush()
            return attempt
        should_dead_letter = (
            max_attempts is not None and observation.attempt_count >= max_attempts
        )
        observation.lease_owner = None
        observation.lease_token = None
        observation.lease_until = None
        observation.last_error = error_message
        observation.updated_at = now
        if should_dead_letter:
            observation.status = OBSERVATION_DEAD_LETTER
            observation.next_attempt_at = None
            dead_letter_statement = select(IngestionDeadLetter).where(
                IngestionDeadLetter.observation_id == observation.id,
                IngestionDeadLetter.organization_id == self.tenant_id,
            )
            dead_letter_result = await self._session.execute(dead_letter_statement)
            if dead_letter_result.scalar_one_or_none() is None:
                self._session.add(
                    IngestionDeadLetter(
                        organization_id=self.tenant_id,
                        observation_id=observation.id,
                        attempt_id=attempt.id,
                        reason=error_message or error_type or "ingestion failed",
                        error_type=error_type,
                        error_message=error_message,
                        error_details=_json_mapping(error_details),
                        failed_at=now,
                    )
                )
        else:
            observation.status = OBSERVATION_RETRYING
            observation.next_attempt_at = retry_at or (
                now + timedelta(seconds=max(0, int(retry_delay_seconds)))
            )
        await self._session.flush()
        return attempt

    async def dead_letter(
        self,
        observation_id: uuid.UUID,
        *,
        attempt_id: uuid.UUID | None = None,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
        reason: str,
        error_type: str | None = None,
        error_message: str | None = None,
        error_details: Mapping[str, Any] | None = None,
    ) -> IngestionDeadLetter | None:
        now = _utcnow()
        statement = select(IngestionObservation).where(
            IngestionObservation.id == observation_id
        )
        statement = self._scope_select(statement)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        observation = result.scalar_one_or_none()
        if observation is None:
            return None
        if attempt_id is not None:
            attempt_statement = select(IngestionAttempt).where(
                IngestionAttempt.id == attempt_id,
                IngestionAttempt.observation_id == observation_id,
                IngestionAttempt.organization_id == self.tenant_id,
            )
            attempt_result = await self._session.execute(attempt_statement)
            attempt = attempt_result.scalar_one_or_none()
            if attempt is None:
                return None
            if worker_id is not None and attempt.worker_id != worker_id:
                return None
            if lease_token is not None and attempt.lease_token != lease_token:
                return None
            attempt.status = OBSERVATION_DEAD_LETTER
            attempt.finished_at = now
            attempt.lease_until = None
        existing_statement = select(IngestionDeadLetter).where(
            IngestionDeadLetter.observation_id == observation_id,
            IngestionDeadLetter.organization_id == self.tenant_id,
        )
        existing_result = await self._session.execute(existing_statement)
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing
        observation.status = OBSERVATION_DEAD_LETTER
        observation.next_attempt_at = None
        observation.lease_owner = None
        observation.lease_token = None
        observation.lease_until = None
        observation.last_error = error_message or reason
        observation.updated_at = now
        dead_letter = IngestionDeadLetter(
            organization_id=self.tenant_id,
            observation_id=observation_id,
            attempt_id=attempt_id,
            reason=reason,
            error_type=error_type,
            error_message=error_message,
            error_details=_json_mapping(error_details),
            failed_at=now,
        )
        self._session.add(dead_letter)
        await self._session.flush()
        return dead_letter


class IngestionSourceTurnRepository(TenantScopedRepository[IngestionSourceTurn]):
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=IngestionSourceTurn)

    async def _observation_exists(self, observation_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(IngestionObservation).where(
                IngestionObservation.id == observation_id,
                IngestionObservation.organization_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def insert_source_turn(
        self,
        *,
        observation_id: uuid.UUID,
        turn_index: int,
        role: str,
        content: str,
        source_turn_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> IngestionSourceTurn:
        records = await self.insert_source_turns(
            observation_id,
            [
                {
                    "turn_index": turn_index,
                    "role": role,
                    "content": content,
                    "source_turn_id": source_turn_id,
                    "metadata": metadata,
                }
            ],
        )
        return records[0]

    async def insert_source_turns(
        self,
        observation_id: uuid.UUID,
        turns: Sequence[Mapping[str, Any] | IngestionSourceTurn],
    ) -> Sequence[IngestionSourceTurn]:
        if not await self._observation_exists(observation_id):
            raise ValueError("The source turn observation does not belong to the tenant.")
        records: list[IngestionSourceTurn] = []
        for index, turn in enumerate(turns):
            if isinstance(turn, IngestionSourceTurn):
                self._validate_tenant_ownership(turn)
                if turn.observation_id != observation_id:
                    raise ValueError("The source turn observation does not match.")
                record = turn
            else:
                role = str(turn.get("role", "user"))
                content = turn.get("content", turn.get("message", ""))
                if content is None:
                    content = ""
                turn_index = int(turn.get("turn_index", turn.get("index", index)))
                source_turn_id = turn.get("source_turn_id", turn.get("external_id"))
                metadata = turn.get("metadata")
                record = IngestionSourceTurn(
                    organization_id=self.tenant_id,
                    observation_id=observation_id,
                    turn_index=turn_index,
                    role=role,
                    content=str(content),
                    source_turn_id=(
                        str(source_turn_id) if source_turn_id is not None else None
                    ),
                    metadata_=(
                        _json_mapping(metadata) if isinstance(metadata, Mapping) else None
                    ),
                )
            existing_statement = select(IngestionSourceTurn).where(
                IngestionSourceTurn.observation_id == observation_id,
                IngestionSourceTurn.turn_index == record.turn_index,
            )
            existing_statement = self._scope_select(existing_statement)
            existing_result = await self._session.execute(existing_statement)
            existing = existing_result.scalar_one_or_none()
            if existing is not None:
                if (
                    existing.role != record.role
                    or existing.content != record.content
                    or existing.source_turn_id != record.source_turn_id
                ):
                    raise ValueError("A source turn replay does not match the stored turn.")
                records.append(existing)
                continue
            if _dialect_name(self._session) == "postgresql":
                record_id = record.id or uuid.uuid4()
                record.id = record_id
                values = {
                    "id": record_id,
                    "organization_id": self.tenant_id,
                    "observation_id": observation_id,
                    "turn_index": record.turn_index,
                    "role": record.role,
                    "content": record.content,
                    "source_turn_id": record.source_turn_id,
                    "metadata_": record.metadata_,
                    "created_at": record.created_at or _naive_utcnow(),
                }
                statement = (
                    postgresql_insert(IngestionSourceTurn)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=[
                            IngestionSourceTurn.observation_id,
                            IngestionSourceTurn.turn_index,
                        ]
                    )
                    .returning(IngestionSourceTurn)
                )
                result = await self._session.execute(statement)
                inserted = result.scalar_one_or_none()
                if inserted is None:
                    conflict_statement = select(IngestionSourceTurn).where(
                        IngestionSourceTurn.observation_id == observation_id,
                        IngestionSourceTurn.turn_index == record.turn_index,
                    )
                    conflict_statement = self._scope_select(conflict_statement)
                    conflict_result = await self._session.execute(conflict_statement)
                    inserted = conflict_result.scalar_one_or_none()
                if inserted is None:
                    raise RuntimeError("The source turn insert did not return a row.")
                records.append(inserted)
                continue
            try:
                async with self._session.begin_nested():
                    self._session.add(record)
                    await self._session.flush()
                records.append(record)
            except IntegrityError:
                conflict_statement = select(IngestionSourceTurn).where(
                    IngestionSourceTurn.observation_id == observation_id,
                    IngestionSourceTurn.turn_index == record.turn_index,
                )
                conflict_statement = self._scope_select(conflict_statement)
                conflict_result = await self._session.execute(conflict_statement)
                inserted = conflict_result.scalar_one_or_none()
                if inserted is None:
                    raise
                records.append(inserted)
        return records

    async def add_turns(
        self,
        observation_id: uuid.UUID,
        turns: Sequence[Mapping[str, Any] | IngestionSourceTurn],
    ) -> Sequence[IngestionSourceTurn]:
        return await self.insert_source_turns(observation_id, turns)


class IngestionAttemptRepository(TenantScopedRepository[IngestionAttempt]):
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=IngestionAttempt)

    async def list_for_observation(
        self, observation_id: uuid.UUID
    ) -> Sequence[IngestionAttempt]:
        statement = select(IngestionAttempt).where(
            IngestionAttempt.observation_id == observation_id
        ).order_by(IngestionAttempt.attempt_number)
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalars().all()


class IngestionDeadLetterRepository(TenantScopedRepository[IngestionDeadLetter]):
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=IngestionDeadLetter)

    async def get_for_observation(
        self, observation_id: uuid.UUID
    ) -> IngestionDeadLetter | None:
        statement = select(IngestionDeadLetter).where(
            IngestionDeadLetter.observation_id == observation_id
        )
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


class IngestionOutboxRepository(TenantScopedRepository[IngestionOutboxEvent]):
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
    ) -> None:
        super().__init__(session=session, tenant_id=tenant_id, model=IngestionOutboxEvent)

    async def get_by_event_key(
        self, event_key: str
    ) -> IngestionOutboxEvent | None:
        statement = select(IngestionOutboxEvent).where(
            IngestionOutboxEvent.event_key == event_key
        )
        statement = self._scope_select(statement)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def enqueue(
        self,
        *,
        observation_id: uuid.UUID,
        event_type: str = "observation.accepted",
        event_key: str | None = None,
        attempt_id: uuid.UUID | None = None,
        available_at: datetime | None = None,
    ) -> tuple[IngestionOutboxEvent, bool]:
        observation_result = await self._session.execute(
            select(IngestionObservation).where(
                IngestionObservation.id == observation_id,
                IngestionObservation.organization_id == self.tenant_id,
            )
        )
        if observation_result.scalar_one_or_none() is None:
            raise ValueError("The outbox observation does not belong to the tenant.")
        if attempt_id is not None:
            attempt_result = await self._session.execute(
                select(IngestionAttempt).where(
                    IngestionAttempt.id == attempt_id,
                    IngestionAttempt.organization_id == self.tenant_id,
                )
            )
            attempt = attempt_result.scalar_one_or_none()
            if attempt is None or attempt.observation_id != observation_id:
                raise ValueError("The outbox attempt does not match the observation.")
        key = event_key or f"{event_type}:{observation_id}"
        now = _utcnow()
        values = {
            "id": uuid.uuid4(),
            "organization_id": self.tenant_id,
            "observation_id": observation_id,
            "attempt_id": attempt_id,
            "event_type": event_type,
            "event_key": key,
            "status": OUTBOX_PENDING,
            "available_at": available_at or now,
            "attempt_count": 0,
            "created_at": _naive_utcnow(),
        }
        if _dialect_name(self._session) == "postgresql":
            statement = (
                postgresql_insert(IngestionOutboxEvent)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        IngestionOutboxEvent.organization_id,
                        IngestionOutboxEvent.event_key,
                    ]
                )
                .returning(IngestionOutboxEvent)
            )
            result = await self._session.execute(statement)
            record = result.scalar_one_or_none()
            if record is not None:
                return record, True
        else:
            existing = await self.get_by_event_key(key)
            if existing is not None:
                return existing, False
            record = IngestionOutboxEvent(**values)
            try:
                async with self._session.begin_nested():
                    self._session.add(record)
                    await self._session.flush()
                return record, True
            except IntegrityError:
                existing = await self.get_by_event_key(key)
                if existing is None:
                    raise
                return existing, False
        existing = await self.get_by_event_key(key)
        if existing is None:
            raise RuntimeError("The idempotent outbox insert did not return a row.")
        return existing, False

    async def enqueue_event(
        self,
        *,
        observation_id: uuid.UUID,
        event_type: str = "observation.accepted",
        event_key: str | None = None,
        attempt_id: uuid.UUID | None = None,
        available_at: datetime | None = None,
    ) -> tuple[IngestionOutboxEvent, bool]:
        return await self.enqueue(
            observation_id=observation_id,
            event_type=event_type,
            event_key=event_key,
            attempt_id=attempt_id,
            available_at=available_at,
        )

    async def claim_pending(
        self,
        worker_id: str,
        *,
        limit: int = 100,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> Sequence[IngestionOutboxEvent]:
        if limit <= 0:
            return []
        now = _utcnow()
        lease_until = now + timedelta(seconds=_normalize_lease(lease_seconds))
        statement = (
            select(IngestionOutboxEvent)
            .where(
                IngestionOutboxEvent.status.in_(
                    (OUTBOX_PENDING, OUTBOX_FAILED, OUTBOX_CLAIMED)
                ),
                or_(
                    IngestionOutboxEvent.available_at.is_(None),
                    IngestionOutboxEvent.available_at <= now,
                ),
                or_(
                    IngestionOutboxEvent.lease_until.is_(None),
                    IngestionOutboxEvent.lease_until <= now,
                ),
            )
            .order_by(IngestionOutboxEvent.created_at)
            .limit(min(int(limit), 1000))
        )
        statement = self._scope_select(statement)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        events = list(result.scalars().all())
        claimed: list[IngestionOutboxEvent] = []
        for event in events:
            if max_attempts is not None and event.attempt_count >= max_attempts:
                event.status = OUTBOX_DEAD_LETTER
                event.lease_owner = None
                event.lease_token = None
                event.lease_until = None
                event.last_error = "maximum outbox attempts reached"
                continue
            token = uuid.uuid4()
            event.status = OUTBOX_CLAIMED
            event.claimed_at = now
            event.lease_owner = worker_id
            event.lease_token = token
            event.lease_until = lease_until
            event.attempt_count += 1
            claimed.append(event)
        await self._session.flush()
        return claimed

    async def claim_outbox(
        self,
        worker_id: str,
        *,
        limit: int = 100,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> Sequence[IngestionOutboxEvent]:
        return await self.claim_pending(
            worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

    async def claim_event(
        self,
        event_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> IngestionOutboxEvent | None:
        now = _utcnow()
        lease_until = now + timedelta(seconds=_normalize_lease(lease_seconds))
        statement = select(IngestionOutboxEvent).where(
            IngestionOutboxEvent.id == event_id
        )
        statement = self._scope_select(statement)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        event = result.scalar_one_or_none()
        if event is None or event.status == OUTBOX_PUBLISHED:
            return event
        if event.status == OUTBOX_CLAIMED and event.lease_until and event.lease_until > now:
            return event
        if max_attempts is not None and event.attempt_count >= max_attempts:
            event.status = OUTBOX_DEAD_LETTER
            event.lease_owner = None
            event.lease_token = None
            event.lease_until = None
            event.last_error = "maximum outbox attempts reached"
            await self._session.flush()
            return event
        event.status = OUTBOX_CLAIMED
        event.claimed_at = now
        event.lease_owner = worker_id
        event.lease_token = uuid.uuid4()
        event.lease_until = lease_until
        event.attempt_count += 1
        await self._session.flush()
        return event

    async def mark_published(
        self,
        event_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
    ) -> bool:
        now = _utcnow()
        statement = select(IngestionOutboxEvent).where(
            IngestionOutboxEvent.id == event_id
        )
        statement = self._scope_select(statement)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        event = result.scalar_one_or_none()
        if event is None:
            return False
        if worker_id is not None and event.lease_owner != worker_id:
            return False
        if lease_token is not None and event.lease_token != lease_token:
            return False
        if event.status == OUTBOX_PUBLISHED:
            return True
        if event.status != OUTBOX_CLAIMED:
            return False
        event.status = OUTBOX_PUBLISHED
        event.published_at = now
        event.lease_owner = None
        event.lease_token = None
        event.lease_until = None
        event.last_error = None
        await self._session.flush()
        return True

    async def retry_event(
        self,
        event_id: uuid.UUID,
        *,
        error: str | None = None,
        available_at: datetime | None = None,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
    ) -> bool:
        now = _utcnow()
        statement = select(IngestionOutboxEvent).where(
            IngestionOutboxEvent.id == event_id
        )
        statement = self._scope_select(statement)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        event = result.scalar_one_or_none()
        if event is None:
            return False
        if worker_id is not None and event.lease_owner != worker_id:
            return False
        if lease_token is not None and event.lease_token != lease_token:
            return False
        event.status = OUTBOX_FAILED
        event.available_at = available_at or now
        event.lease_owner = None
        event.lease_token = None
        event.lease_until = None
        event.last_error = error
        await self._session.flush()
        return True

    async def fail_event(
        self,
        event_id: uuid.UUID,
        *,
        error: str | None = None,
        available_at: datetime | None = None,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
        max_attempts: int | None = None,
    ) -> bool:
        now = _utcnow()
        statement = select(IngestionOutboxEvent).where(
            IngestionOutboxEvent.id == event_id
        )
        statement = self._scope_select(statement)
        statement = _with_skip_locked(statement, self._session)
        result = await self._session.execute(statement)
        event = result.scalar_one_or_none()
        if event is None:
            return False
        if worker_id is not None and event.lease_owner != worker_id:
            return False
        if lease_token is not None and event.lease_token != lease_token:
            return False
        event.last_error = error
        event.lease_owner = None
        event.lease_token = None
        event.lease_until = None
        if max_attempts is not None and event.attempt_count >= max_attempts:
            event.status = OUTBOX_DEAD_LETTER
            event.available_at = now
        else:
            event.status = OUTBOX_FAILED
            event.available_at = available_at or now
        await self._session.flush()
        return True


class IngestionRepository(TenantScopedRepository[IngestionObservation]):
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID | None = None,
        *,
        organization_id: uuid.UUID | None = None,
    ) -> None:
        tenant = organization_id if organization_id is not None else tenant_id
        if tenant is None:
            raise ValueError("A tenant organization ID is required.")
        super().__init__(session=session, tenant_id=tenant, model=IngestionObservation)
        self.observations = IngestionObservationRepository(session, tenant)
        self.turns = IngestionSourceTurnRepository(session, tenant)
        self.attempts = IngestionAttemptRepository(session, tenant)
        self.dead_letters = IngestionDeadLetterRepository(session, tenant)
        self.outbox = IngestionOutboxRepository(session, tenant)

    @property
    def observation_repository(self) -> IngestionObservationRepository:
        return self.observations

    @property
    def source_turn_repository(self) -> IngestionSourceTurnRepository:
        return self.turns

    @property
    def attempt_repository(self) -> IngestionAttemptRepository:
        return self.attempts

    @property
    def dead_letter_repository(self) -> IngestionDeadLetterRepository:
        return self.dead_letters

    @property
    def outbox_repository(self) -> IngestionOutboxRepository:
        return self.outbox

    async def get_observation_by_idempotency_key(
        self, idempotency_key: str
    ) -> IngestionObservation | None:
        return await self.observations.get_by_idempotency_key(idempotency_key)

    async def insert_observation(
        self,
        *,
        idempotency_key: str | None,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        source: str = "api",
    ) -> IngestionObservation:
        return await self.observations.insert_observation(
            idempotency_key=idempotency_key,
            user_id=user_id,
            session_id=session_id,
            payload=payload,
            metadata=metadata,
            source=source,
        )

    async def insert_observation_idempotently(
        self,
        *,
        idempotency_key: str | None,
        user_id: uuid.UUID,
        session_id: uuid.UUID | None,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        source: str = "api",
    ) -> tuple[IngestionObservation, bool]:
        return await self.observations.insert_idempotently(
            idempotency_key=idempotency_key,
            user_id=user_id,
            session_id=session_id,
            payload=payload,
            metadata=metadata,
            source=source,
        )

    async def insert_source_turns(
        self,
        observation_id: uuid.UUID,
        turns: Sequence[Mapping[str, Any] | IngestionSourceTurn],
    ) -> Sequence[IngestionSourceTurn]:
        return await self.turns.insert_source_turns(observation_id, turns)

    async def enqueue_outbox(
        self,
        *,
        observation_id: uuid.UUID,
        event_type: str = "observation.accepted",
        event_key: str | None = None,
        attempt_id: uuid.UUID | None = None,
        available_at: datetime | None = None,
    ) -> tuple[IngestionOutboxEvent, bool]:
        return await self.outbox.enqueue(
            observation_id=observation_id,
            event_type=event_type,
            event_key=event_key,
            attempt_id=attempt_id,
            available_at=available_at,
        )

    async def claim_outbox(
        self,
        worker_id: str,
        *,
        limit: int = 100,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> Sequence[IngestionOutboxEvent]:
        return await self.outbox.claim_pending(
            worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

    async def claim_outbox_event(
        self,
        event_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> IngestionOutboxEvent | None:
        return await self.outbox.claim_event(
            event_id,
            worker_id,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

    async def mark_outbox_published(
        self,
        event_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
    ) -> bool:
        return await self.outbox.mark_published(
            event_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )

    async def retry_outbox(
        self,
        event_id: uuid.UUID,
        *,
        error: str | None = None,
        available_at: datetime | None = None,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
    ) -> bool:
        return await self.outbox.retry_event(
            event_id,
            error=error,
            available_at=available_at,
            worker_id=worker_id,
            lease_token=lease_token,
        )

    async def claim_observation(
        self,
        observation_id: uuid.UUID,
        worker_id: str,
        *,
        lease_seconds: int = 300,
        max_attempts: int | None = None,
    ) -> IngestionAttempt | None:
        return await self.observations.claim(
            observation_id,
            worker_id,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )

    async def complete_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_details: Mapping[str, Any] | None = None,
    ) -> IngestionAttempt | None:
        return await self.observations.complete_attempt(
            attempt_id,
            worker_id=worker_id,
            lease_token=lease_token,
            error_type=error_type,
            error_message=error_message,
            error_details=error_details,
        )

    async def fail_attempt(
        self,
        attempt_id: uuid.UUID,
        *,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_details: Mapping[str, Any] | None = None,
        retry_at: datetime | None = None,
        retry_delay_seconds: int = 60,
        max_attempts: int | None = None,
    ) -> IngestionAttempt | None:
        return await self.observations.fail_attempt(
            attempt_id,
            worker_id=worker_id,
            lease_token=lease_token,
            error_type=error_type,
            error_message=error_message,
            error_details=error_details,
            retry_at=retry_at,
            retry_delay_seconds=retry_delay_seconds,
            max_attempts=max_attempts,
        )

    async def dead_letter(
        self,
        observation_id: uuid.UUID,
        *,
        reason: str,
        attempt_id: uuid.UUID | None = None,
        worker_id: str | None = None,
        lease_token: uuid.UUID | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_details: Mapping[str, Any] | None = None,
    ) -> IngestionDeadLetter | None:
        return await self.observations.dead_letter(
            observation_id,
            attempt_id=attempt_id,
            worker_id=worker_id,
            lease_token=lease_token,
            reason=reason,
            error_type=error_type,
            error_message=error_message,
            error_details=error_details,
        )


__all__ = [
    "OBSERVATION_COMPLETED",
    "OBSERVATION_DEAD_LETTER",
    "OBSERVATION_FAILED",
    "OBSERVATION_PENDING",
    "OBSERVATION_PROCESSING",
    "OBSERVATION_RETRYING",
    "OUTBOX_CLAIMED",
    "OUTBOX_DEAD_LETTER",
    "OUTBOX_FAILED",
    "OUTBOX_PENDING",
    "OUTBOX_PUBLISHED",
    "IdempotencyConflictError",
    "IngestionAttemptRepository",
    "IngestionDeadLetterRepository",
    "IngestionObservationRepository",
    "IngestionOutboxRepository",
    "IngestionRepository",
    "IngestionSourceTurnRepository",
]
