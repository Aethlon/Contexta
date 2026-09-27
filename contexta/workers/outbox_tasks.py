from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select

from contexta.db import AsyncSessionFactory
from contexta.models.ingestion import IngestionOutboxEvent
from contexta.repositories.ingestion_repo import IngestionRepository
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DEFAULT_OUTBOX_LIMIT = 100
DEFAULT_OUTBOX_LEASE_SECONDS = 300


def _organization_id(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _id_result(
    events: Sequence[Any],
) -> dict[str, list[str]]:
    return {
        "event_ids": [str(event.id) for event in events],
        "observation_ids": [str(event.observation_id) for event in events],
        "attempt_ids": [
            str(event.attempt_id) for event in events if event.attempt_id is not None
        ],
        "lease_tokens": [str(event.lease_token) for event in events],
    }


async def claim_outbox_events_async(
    organization_id: str | uuid.UUID,
    *,
    limit: int = DEFAULT_OUTBOX_LIMIT,
    lease_seconds: int = DEFAULT_OUTBOX_LEASE_SECONDS,
    max_attempts: int | None = None,
    worker_id: str | None = None,
) -> dict[str, list[str]]:
    tenant_id = _organization_id(organization_id)
    claim_worker = worker_id or f"outbox:{uuid.uuid4()}"
    async with AsyncSessionFactory() as session, session.begin():
        repository = IngestionRepository(session, tenant_id)
        events = await repository.claim_outbox(
            claim_worker,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )
        return _id_result(events)


@celery_app.task(
    name="contexta.workers.outbox_tasks.claim_outbox_events",
    acks_late=True,
)
def claim_outbox_events(
    organization_id: str,
    limit: int = DEFAULT_OUTBOX_LIMIT,
    lease_seconds: int = DEFAULT_OUTBOX_LEASE_SECONDS,
    max_attempts: int | None = None,
) -> dict[str, list[str]]:
    return asyncio.run(
        claim_outbox_events_async(
            organization_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )
    )


async def _pending_organization_ids_async(limit: int = 100) -> list[uuid.UUID]:
    """Find tenants that have claimable outbox work.

    The status filter must mirror ``IngestionOutboxRepository.claim_outbox`` exactly.
    It previously listed only ``pending``/``failed`` while the claim query also
    accepts ``claimed`` rows whose lease has expired, so an event that was claimed
    but never published stayed invisible to the dispatcher forever.
    """
    now = datetime.now(UTC)
    async with AsyncSessionFactory() as session:
        statement = (
            select(IngestionOutboxEvent.organization_id)
            .where(IngestionOutboxEvent.status.in_(("pending", "failed", "claimed")))
            .where(IngestionOutboxEvent.available_at <= now)
            .where(
                or_(
                    IngestionOutboxEvent.lease_until.is_(None),
                    IngestionOutboxEvent.lease_until <= now,
                )
            )
            .group_by(IngestionOutboxEvent.organization_id)
            .order_by(func.min(IngestionOutboxEvent.available_at).asc())
            .limit(max(1, min(int(limit), 1000)))
        )
        result = await session.execute(statement)
        return [uuid.UUID(str(value)) for value in result.scalars().all()]


def _publish_claimed_events(
    organization_id: str | uuid.UUID,
    result: dict[str, list[str]],
) -> list[str]:
    """Hand every claimed outbox event to the extraction queue.

    This used to be driven by a ``task_success`` signal handler. That was fragile:
    the publish depended on Celery's signal internals and any failure was swallowed
    by a bare ``suppress(Exception)``, so events were claimed, leased, and then
    silently never processed. Publishing inline keeps claim and dispatch in one
    place and makes a failure visible in the logs and in the task result.
    """
    from contexta.workers.extraction_tasks import process_observation_outbox

    event_ids = result.get("event_ids") or []
    observation_ids = result.get("observation_ids") or []
    lease_tokens = result.get("lease_tokens") or []
    published: list[str] = []

    for index, observation_id in enumerate(observation_ids):
        if index >= len(event_ids):
            break
        event_id = event_ids[index]
        lease_token = lease_tokens[index] if index < len(lease_tokens) else None
        try:
            process_observation_outbox.delay(
                str(observation_id),
                str(organization_id),
                str(event_id),
                str(lease_token) if lease_token is not None else None,
            )
        except Exception:
            # Release the lease so the next sweep can retry instead of stranding
            # the event until its lease expires and, before the status filter was
            # fixed, never being rediscovered at all.
            logger.exception(
                "Failed to publish outbox event to the extraction queue: "
                "event_id=%s observation_id=%s organization_id=%s",
                event_id,
                observation_id,
                organization_id,
            )
            continue
        published.append(str(event_id))

    return published


async def dispatch_outbox_all_async(
    *,
    limit: int = DEFAULT_OUTBOX_LIMIT,
    lease_seconds: int = DEFAULT_OUTBOX_LEASE_SECONDS,
    max_attempts: int | None = None,
) -> dict[str, list[str]]:
    organization_ids = await _pending_organization_ids_async(limit=100)
    aggregate: dict[str, list[str]] = {
        "event_ids": [],
        "observation_ids": [],
        "attempt_ids": [],
        "lease_tokens": [],
        "published_event_ids": [],
        "publish_failures": [],
    }
    for organization_id in organization_ids:
        result = await claim_outbox_events_async(
            organization_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )
        for key in ("event_ids", "observation_ids", "attempt_ids", "lease_tokens"):
            aggregate[key].extend(result.get(key, []))
        published = _publish_claimed_events(organization_id, result)
        aggregate["published_event_ids"].extend(published)
        claimed = set(result.get("event_ids") or [])
        aggregate["publish_failures"].extend(
            event_id for event_id in claimed if event_id not in set(published)
        )
    return aggregate


@celery_app.task(
    name="contexta.workers.outbox_tasks.dispatch_outbox",
    acks_late=True,
)
def dispatch_outbox(
    organization_id: str | None = None,
    limit: int = DEFAULT_OUTBOX_LIMIT,
    lease_seconds: int = DEFAULT_OUTBOX_LEASE_SECONDS,
    max_attempts: int | None = None,
) -> dict[str, list[str]]:
    if organization_id is None:
        return asyncio.run(
            dispatch_outbox_all_async(
                limit=limit,
                lease_seconds=lease_seconds,
                max_attempts=max_attempts,
            )
        )
    result = asyncio.run(
        claim_outbox_events_async(
            organization_id,
            limit=limit,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )
    )
    published = _publish_claimed_events(organization_id, result)
    result["published_event_ids"] = published
    result["publish_failures"] = [
        event_id
        for event_id in (result.get("event_ids") or [])
        if event_id not in set(published)
    ]
    return result


__all__ = [
    "DEFAULT_OUTBOX_LEASE_SECONDS",
    "DEFAULT_OUTBOX_LIMIT",
    "claim_outbox_events",
    "claim_outbox_events_async",
    "dispatch_outbox",
    "dispatch_outbox_all_async",
]
