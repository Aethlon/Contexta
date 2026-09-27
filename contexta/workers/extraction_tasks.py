"""Celery tasks for legacy and durable observation processing."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from contexta.core.errors import ExtractionError
from contexta.core.schemas import ObservationPayload
from contexta.db import AsyncSessionFactory
from contexta.repositories.ingestion_repo import IngestionRepository
from contexta.workers.celery_app import celery_app
from contexta.workers.embedding_tasks import enqueue_embedding_generation

logger = logging.getLogger(__name__)

DEFAULT_DURABLE_LEASE_SECONDS = 300
DEFAULT_DURABLE_MAX_ATTEMPTS = 3
DEFAULT_DURABLE_RETRY_DELAY_SECONDS = 60


class DurableAttemptError(Exception):
    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__(result.get("status", "failed"))
        self.result = result


def _as_uuid(value: str | uuid.UUID, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a UUID.") from exc


def _task_id(task: Any) -> str:
    request = getattr(task, "request", None)
    task_id = getattr(request, "id", None)
    return str(task_id) if task_id else str(uuid.uuid4())


def _error_message(exc: BaseException) -> str:
    return f"{type(exc).__name__}: observation processing failed"


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _timing_values(result: Any) -> dict[str, float]:
    timings = getattr(result, "timings", None)
    return {
        "extraction_ms": float(getattr(timings, "extraction_ms", 0.0) or 0.0),
        "deduplication_ms": float(getattr(timings, "deduplication_ms", 0.0) or 0.0),
        "entity_graph_ms": float(getattr(timings, "entity_graph_ms", 0.0) or 0.0),
        "persistence_ms": float(getattr(timings, "persistence_ms", 0.0) or 0.0),
        "total_ms": float(getattr(timings, "total_ms", 0.0) or 0.0),
    }


def _result_summary(result: Any, observation_id: uuid.UUID, attempt_id: uuid.UUID) -> dict[str, Any]:
    return {
        "status": "completed",
        "observation_id": str(observation_id),
        "attempt_id": str(attempt_id),
        "extracted_count": int(getattr(result, "extracted_count", 0) or 0),
        "stored_count": int(getattr(result, "stored_count", 0) or 0),
        "new_entities_count": int(getattr(result, "new_entities_count", 0) or 0),
        "new_edges_count": int(getattr(result, "new_edges_count", 0) or 0),
        "new_links_count": int(getattr(result, "new_links_count", 0) or 0),
        "timings": _timing_values(result),
    }


async def _find_outbox_event(
    repository: IngestionRepository,
    observation_id: uuid.UUID,
    event_id: uuid.UUID | None,
) -> Any:
    outbox = repository.outbox
    if event_id is not None:
        event = await outbox.get_by_id(event_id)
        if event is not None:
            return event
    return await outbox.get_by_event_key(f"observation.accepted:{observation_id}")


async def _mark_outbox_published(
    organization_id: uuid.UUID,
    event_id: uuid.UUID | None,
    event_lease_token: uuid.UUID | None,
) -> None:
    if event_id is None:
        return
    async with AsyncSessionFactory() as session:
        repository = IngestionRepository(session, organization_id)
        try:
            await repository.mark_outbox_published(
                event_id,
                lease_token=event_lease_token,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _mark_outbox_failed(
    organization_id: uuid.UUID,
    event_id: uuid.UUID | None,
    event_lease_token: uuid.UUID | None,
    *,
    error: str,
    max_attempts: int,
    retry_delay_seconds: int,
) -> None:
    if event_id is None:
        return
    async with AsyncSessionFactory() as session:
        repository = IngestionRepository(session, organization_id)
        try:
            await repository.outbox.fail_event(
                event_id,
                error=error,
                available_at=datetime.now(UTC) + timedelta(seconds=max(0, retry_delay_seconds)),
                lease_token=event_lease_token,
                max_attempts=max_attempts,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _record_attempt_failure(
    organization_id: uuid.UUID,
    observation_id: uuid.UUID,
    attempt_id: uuid.UUID,
    worker_id: str,
    lease_token: uuid.UUID | None,
    event_id: uuid.UUID | None,
    event_lease_token: uuid.UUID | None,
    exc: BaseException,
    *,
    max_attempts: int,
    retry_delay_seconds: int,
) -> dict[str, Any]:
    error_type = type(exc).__name__
    error_message = _error_message(exc)
    async with AsyncSessionFactory() as session:
        repository = IngestionRepository(session, organization_id)
        try:
            attempt = await repository.fail_attempt(
                attempt_id,
                worker_id=worker_id,
                lease_token=lease_token,
                error_type=error_type[:200],
                error_message=error_message,
                error_details={"error_type": error_type},
                retry_delay_seconds=retry_delay_seconds,
                max_attempts=max_attempts,
            )
            if attempt is None:
                await session.rollback()
                return {
                    "status": "lease_lost",
                    "observation_id": str(observation_id),
                    "attempt_id": str(attempt_id),
                }
            observation = await repository.get_by_id(observation_id)
            observation_status = str(_value(observation, "status", "retrying"))
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await _mark_outbox_failed(
        organization_id,
        event_id,
        event_lease_token,
        error=error_message,
        max_attempts=max_attempts,
        retry_delay_seconds=retry_delay_seconds,
    )
    return {
        "status": "dead_letter" if observation_status == "dead_letter" else "retrying",
        "observation_id": str(observation_id),
        "attempt_id": str(attempt_id),
        "attempt_count": int(_value(attempt, "attempt_number", 1) or 1),
        "error_type": error_type,
    }


async def _claim_durable_observation(
    organization_id: uuid.UUID,
    observation_id: uuid.UUID,
    *,
    worker_id: str,
    event_id: uuid.UUID | None,
    max_attempts: int,
    lease_seconds: int,
) -> dict[str, Any] | None:
    async with AsyncSessionFactory() as session:
        repository = IngestionRepository(session, organization_id)
        try:
            attempt = await repository.claim_observation(
                observation_id,
                worker_id,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            )
            observation = await repository.get_by_id(observation_id)
            event = await _find_outbox_event(repository, observation_id, event_id)
            if event is not None and str(_value(event, "status", "")) != "published":
                event = await repository.claim_outbox_event(
                    _value(event, "id"),
                    worker_id,
                    lease_seconds=lease_seconds,
                    max_attempts=max_attempts,
                )
            event_record_id = _value(event, "id", event_id)
            event_record_token = _value(event, "lease_token")
            if attempt is None:
                await session.commit()
                return {
                    "attempt": None,
                    "observation_status": _value(observation, "status"),
                    "payload": None,
                    "event_id": event_record_id,
                    "event_lease_token": event_record_token,
                }
            if observation is None:
                await repository.fail_attempt(
                    _value(attempt, "id"),
                    worker_id=worker_id,
                    lease_token=_value(attempt, "lease_token"),
                    error_type="ObservationMissing",
                    error_message="Observation record was not found.",
                    max_attempts=max_attempts,
                )
                await session.commit()
                return {
                    "attempt": None,
                    "observation_status": "dead_letter",
                    "payload": None,
                    "event_id": event_record_id,
                    "event_lease_token": event_record_token,
                }
            payload = _value(observation, "payload")
            attempt_data = {
                "id": _value(attempt, "id"),
                "attempt_number": _value(attempt, "attempt_number", 1),
                "worker_id": _value(attempt, "worker_id"),
                "lease_token": _value(attempt, "lease_token"),
            }
            await session.commit()
            return {
                "attempt": attempt_data,
                "observation_status": _value(observation, "status"),
                "payload": dict(payload) if isinstance(payload, Mapping) else payload,
                "event_id": event_record_id,
                "event_lease_token": event_record_token,
            }
        except Exception:
            await session.rollback()
            raise


async def _process_durable_observation_async(
    observation_id: str | uuid.UUID,
    organization_id: str | uuid.UUID,
    *,
    event_id: str | uuid.UUID | None = None,
    event_lease_token: str | uuid.UUID | None = None,
    worker_id: str | None = None,
    max_attempts: int = DEFAULT_DURABLE_MAX_ATTEMPTS,
    lease_seconds: int = DEFAULT_DURABLE_LEASE_SECONDS,
) -> dict[str, Any]:
    observation_uuid = _as_uuid(observation_id, "observation_id")
    organization_uuid = _as_uuid(organization_id, "organization_id")
    event_uuid = _as_uuid(event_id, "event_id") if event_id is not None else None
    token_uuid = _as_uuid(event_lease_token, "event_lease_token") if event_lease_token is not None else None
    claim_worker = worker_id or f"outbox-consumer:{uuid.uuid4()}"
    claim = await _claim_durable_observation(
        organization_uuid,
        observation_uuid,
        worker_id=claim_worker,
        event_id=event_uuid,
        max_attempts=max_attempts,
        lease_seconds=lease_seconds,
    )
    if claim is None:
        return {"status": "skipped", "observation_id": str(observation_uuid)}
    attempt = claim["attempt"]
    if attempt is None:
        resolved_event_id = claim.get("event_id")
        if claim.get("observation_status") == "completed" and resolved_event_id is not None:
            await _mark_outbox_published(
                organization_uuid,
                _as_uuid(resolved_event_id, "event_id"),
                _as_uuid(claim.get("event_lease_token"), "event_lease_token")
                if claim.get("event_lease_token") is not None
                else None,
            )
        return {
            "status": "skipped",
            "observation_id": str(observation_uuid),
            "observation_status": claim.get("observation_status"),
        }
    attempt_id = _as_uuid(_value(attempt, "id"), "attempt_id")
    attempt_token = _value(attempt, "lease_token")
    if attempt_token is not None:
        attempt_token = _as_uuid(attempt_token, "lease_token")
    resolved_event_id = claim.get("event_id")
    resolved_event_token = claim.get("event_lease_token") or token_uuid
    if resolved_event_id is not None:
        resolved_event_id = _as_uuid(resolved_event_id, "event_id")
    if resolved_event_token is not None:
        resolved_event_token = _as_uuid(resolved_event_token, "event_lease_token")
    try:
        observation = ObservationPayload(**(claim.get("payload") or {}))
        if observation.organization_id != organization_uuid:
            raise ValueError("Observation organization does not match the dispatch context.")
        from contexta.core.pipeline import FastMemoryOrchestrator

        async with AsyncSessionFactory() as session:
            try:
                orchestrator = FastMemoryOrchestrator()
                result = await orchestrator.orchestrate(observation, session)
                repository = IngestionRepository(session, organization_uuid)
                completed = await repository.complete_attempt(
                    attempt_id,
                    worker_id=claim_worker,
                    lease_token=attempt_token,
                )
                if completed is None:
                    await session.rollback()
                    return {
                        "status": "lease_lost",
                        "observation_id": str(observation_uuid),
                        "attempt_id": str(attempt_id),
                    }
                await session.commit()
                for memory_id in result.embedding_memory_ids:
                    enqueue_embedding_generation(memory_id)
            except Exception:
                await session.rollback()
                raise
    except Exception as exc:
        failure = await _record_attempt_failure(
            organization_uuid,
            observation_uuid,
            attempt_id,
            claim_worker,
            attempt_token,
            resolved_event_id,
            resolved_event_token,
            exc,
            max_attempts=max_attempts,
            retry_delay_seconds=DEFAULT_DURABLE_RETRY_DELAY_SECONDS,
        )
        raise DurableAttemptError(failure) from exc
    await _mark_outbox_published(
        organization_uuid,
        resolved_event_id,
        resolved_event_token,
    )
    return _result_summary(result, observation_uuid, attempt_id)


@celery_app.task(
    name="contexta.workers.extraction_tasks.process_observation",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
    task_id = self.request.id
    logger.info("Processing legacy observation: task_id=%s", task_id)
    try:
        return asyncio.run(_process_observation_async(self, payload))
    except PydanticValidationError:
        logger.exception("Invalid legacy observation payload")
        raise
    except ExtractionError as exc:
        logger.exception("Legacy observation extraction failed: task_id=%s", task_id)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("Legacy observation pipeline failed: task_id=%s", task_id)
        raise self.retry(exc=exc)


async def _process_observation_async(self, payload: dict[str, Any]) -> dict[str, Any]:
    task_id = self.request.id
    observation = ObservationPayload(**payload)
    from contexta.core.pipeline import FastMemoryOrchestrator

    async with AsyncSessionFactory() as session:
        try:
            orchestrator = FastMemoryOrchestrator()
            result = await orchestrator.orchestrate(observation, session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    for memory_id in result.embedding_memory_ids:
        enqueue_embedding_generation(memory_id)

    return {

        "task_id": task_id,
        "status": "completed",
        "user_id": str(observation.user_id),
        "organization_id": str(observation.organization_id),
        "session_id": str(observation.session_id),
        "extracted_count": result.extracted_count,
        "stored_count": result.stored_count,
        "new_entities_count": result.new_entities_count,
        "new_edges_count": result.new_edges_count,
        "new_links_count": result.new_links_count,
        "timings": {
            "extraction_ms": result.timings.extraction_ms,
            "deduplication_ms": result.timings.deduplication_ms,
            "entity_graph_ms": result.timings.entity_graph_ms,
            "persistence_ms": result.timings.persistence_ms,
            "total_ms": result.timings.total_ms,
        },
        "processed_details": result.details,
    }


def _release_claim_after_failure(
    organization_id: str | None,
    observation_id: str,
    *,
    error: BaseException,
    max_attempts: int | None,
) -> str:
    """Clear a stuck `processing` lease, or dead-letter once attempts run out.

    Returns "dead_letter" or "released".
    """
    if organization_id is None:
        return "released"
    try:
        org_uuid = _as_uuid(organization_id, "organization_id")
        obs_uuid = _as_uuid(observation_id, "observation_id")
    except (TypeError, ValueError):
        return "released"

    async def _release() -> str:
        from sqlalchemy import text

        async with AsyncSessionFactory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT attempt_count, status FROM ingestion_observation "
                        "WHERE id = :id AND organization_id = :org FOR UPDATE"
                    ),
                    {"id": obs_uuid, "org": org_uuid},
                )
            ).mappings().first()
            if row is None:
                return "released"
            spent = max_attempts is not None and int(row["attempt_count"]) >= max_attempts
            if spent or row["status"] not in {"processing", "retrying"}:
                await session.execute(
                    text(
                        "UPDATE ingestion_observation SET status = 'dead_letter', "
                        "lease_owner = NULL, lease_token = NULL, lease_until = NULL, "
                        "next_attempt_at = NULL, last_error = :err, updated_at = now() "
                        "WHERE id = :id AND organization_id = :org"
                    ),
                    {
                        "id": obs_uuid,
                        "org": org_uuid,
                        "err": f"{type(error).__name__}: {error}"[:500],
                    },
                )
                await session.commit()
                return "dead_letter"
            await session.execute(
                text(
                    "UPDATE ingestion_observation SET status = 'retrying', "
                    "lease_owner = NULL, lease_token = NULL, lease_until = NULL, "
                    "next_attempt_at = now(), last_error = :err, updated_at = now() "
                    "WHERE id = :id AND organization_id = :org"
                ),
                {
                    "id": obs_uuid,
                    "org": org_uuid,
                    "err": f"{type(error).__name__}: {error}"[:500],
                },
            )
            await session.commit()
            return "released"

    try:
        return asyncio.run(_release())
    except Exception:
        logger.warning(
            "Could not release stuck lease for observation %s", observation_id, exc_info=True
        )
        return "released"


@celery_app.task(
    name="contexta.workers.extraction_tasks.process_observation_outbox",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_observation_outbox(
    self,
    observation_id: str,
    organization_id: str | None = None,
    event_id: str | None = None,
    event_lease_token: str | None = None,
    max_attempts: int = DEFAULT_DURABLE_MAX_ATTEMPTS,
    lease_seconds: int = DEFAULT_DURABLE_LEASE_SECONDS,
) -> dict[str, Any]:
    task_id = _task_id(self)
    if organization_id is None:
        return {
            "status": "error",
            "error": "organization_id is required",
            "observation_id": str(observation_id),
        }
    try:
        return asyncio.run(
            _process_durable_observation_async(
                observation_id,
                organization_id,
                event_id=event_id,
                event_lease_token=event_lease_token,
                worker_id=f"outbox-consumer:{task_id}",
                max_attempts=max_attempts,
                lease_seconds=lease_seconds,
            )
        )
    except DurableAttemptError as exc:
        return exc.result
    except (TypeError, ValueError) as exc:
        logger.error("Invalid durable observation task arguments: task_id=%s", task_id)
        return {
            "status": "error",
            "error": str(exc),
            "observation_id": str(observation_id),
        }
    except Exception as exc:
        # A failure *before* an attempt row exists (during claiming) has no
        # attempt to fail, so nothing released the lease the claim had taken. The
        # observation then sat in `processing` with a live lease, every retry was
        # skipped as "already claimed", and once attempt_count reached max_attempts
        # it was stranded in `processing` forever. Release the lease explicitly and
        # dead-letter once the budget is spent, instead of blindly retrying.
        logger.exception(
            "Durable observation claim failed before an attempt was recorded: "
            "task_id=%s observation_id=%s",
            task_id,
            observation_id,
        )
        disposition = _release_claim_after_failure(
            organization_id,
            observation_id,
            error=exc,
            max_attempts=max_attempts,
        )
        if disposition == "dead_letter":
            return {
                "status": "dead_letter",
                "observation_id": str(observation_id),
                "error": f"{type(exc).__name__}: {exc}"[:500],
            }
        raise self.retry(exc=exc)


process_observation_outbox_async = _process_durable_observation_async
consume_observation_outbox = process_observation_outbox
process_observation_from_outbox = process_observation_outbox
process_durable_observation = process_observation_outbox


def dispatch_outbox_for_organization(organization_id: str) -> None:
    from contexta.workers.outbox_tasks import dispatch_outbox

    with suppress(Exception):
        dispatch_outbox.delay(organization_id)


# NOTE: publishing claimed outbox events used to hang off a `task_success` signal
# handler here. It silently never fired in the worker, so every event was claimed
# and leased but never handed to the extraction queue. The publish now happens
# inline in `contexta.workers.outbox_tasks._publish_claimed_events`, which keeps
# claim and dispatch together and makes failures visible.

