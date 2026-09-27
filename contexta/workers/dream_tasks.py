"""Celery tasks for dream cycle evaluation."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select

from contexta.config.settings import get_settings
from contexta.core.consolidation.memory import CortexConsolidationService
from contexta.db import AsyncSessionFactory
from contexta.models.dream import DreamRecord
from contexta.models.memory import MemoryRecord
from contexta.repositories.consolidation_repo import ConsolidatedObservationRepository
from contexta.repositories.memory_repo import MemoryRepository
from contexta.repositories.proposal_repo import MemoryProposalRepository
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DORMANT_AFTER_HOURS = 24
DORMANT_BATCH_LIMIT = 50


def _dormant_filters(cutoff: datetime) -> tuple[Any, ...]:
    return (
        MemoryRecord.valid_to.is_(None),
        MemoryRecord.is_archived.is_(False),
        MemoryRecord.is_pinned.is_(False),
        or_(
            MemoryRecord.last_accessed_at.is_(None),
            MemoryRecord.last_accessed_at < cutoff,
        ),
    )


def _scope_fields(memory: MemoryRecord) -> dict[str, UUID | None]:
    return {
        "organization_id": memory.organization_id,
        "user_id": memory.user_id,
        "memory_user_id": memory.memory_user_id,
        "agent_id": memory.agent_id,
        "project_id": memory.project_id,
        "session_id": memory.session_id,
    }


async def _eligible_dream_scopes_async() -> list[tuple[UUID, UUID]]:
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(hours=DORMANT_AFTER_HOURS)
    async with AsyncSessionFactory() as session:
        statement = (
            select(MemoryRecord.organization_id, MemoryRecord.user_id)
            .where(*_dormant_filters(cutoff))
            .distinct()
            .order_by(MemoryRecord.organization_id.asc(), MemoryRecord.user_id.asc())
        )
        result = await session.execute(statement)
        rows = result.all()

    scopes: list[tuple[UUID, UUID]] = []
    seen: set[tuple[UUID, UUID]] = set()
    for row in rows:
        scope = (UUID(str(row[0])), UUID(str(row[1])))
        if scope in seen:
            continue
        seen.add(scope)
        scopes.append(scope)
    return scopes


async def _completed_dream_memory_ids(
    session: Any,
    organization_uuid: UUID,
    user_uuid: UUID,
) -> set[UUID]:
    statement = select(DreamRecord.extra_data).where(
        DreamRecord.organization_id == organization_uuid,
        DreamRecord.user_id == user_uuid,
        DreamRecord.cycle_type == "dream",
        DreamRecord.status == "completed",
    )
    result = await session.execute(statement)
    processed: set[UUID] = set()
    for extra_data in result.scalars().all():
        if not isinstance(extra_data, dict):
            continue
        for field_name in ("processed_memory_ids", "dormant_ids"):
            values = extra_data.get(field_name)
            if not isinstance(values, (list, tuple, set)):
                continue
            for value in values:
                try:
                    processed.add(UUID(str(value)))
                except (TypeError, ValueError, AttributeError):
                    continue
    return processed


async def _run_dream_cycle_async(
    user_id: str,
    organization_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a single dream cycle for a user."""
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(hours=DORMANT_AFTER_HOURS)
    organization_uuid = UUID(str(organization_id))
    user_uuid = UUID(str(user_id))

    async with AsyncSessionFactory() as session:
        try:
            processed_memory_ids = await _completed_dream_memory_ids(
                session,
                organization_uuid,
                user_uuid,
            )
            statement = select(MemoryRecord).where(
                MemoryRecord.organization_id == organization_uuid,
                MemoryRecord.user_id == user_uuid,
                *_dormant_filters(cutoff),
            )
            if processed_memory_ids:
                statement = statement.where(MemoryRecord.id.not_in(processed_memory_ids))
            statement = (
                statement.order_by(
                    MemoryRecord.last_accessed_at.asc().nullsfirst(),
                    MemoryRecord.created_at.asc(),
                    MemoryRecord.id.asc(),
                )
                .limit(DORMANT_BATCH_LIMIT)
                .with_for_update(skip_locked=True)
            )
            dormant = (await session.execute(statement)).scalars().all()

            if dry_run:
                return {"status": "dry_run", "dormant_count": len(dormant)}
            if not dormant:
                return {
                    "status": "skipped",
                    "reason": "no_unprocessed_dormant_memories",
                    "dormant_count": 0,
                }

            memory_repo = MemoryRepository(session, tenant_id=organization_uuid)
            selected_ids = [memory.id for memory in dormant]
            hydrated = await memory_repo.get_many_by_ids(selected_ids)
            hydrated_by_id = {memory.id: memory for memory in hydrated}
            dormant = [
                hydrated_by_id[memory_id]
                for memory_id in selected_ids
                if memory_id in hydrated_by_id
            ]
            dormant.sort(key=lambda memory: str(memory.id))
            if not dormant:
                return {
                    "status": "skipped",
                    "reason": "dormant_memories_unavailable",
                    "dormant_count": 0,
                }

            evidence: list[dict[str, Any]] = []
            memory_scopes: list[dict[str, str | None]] = []
            for memory in dormant:
                scope = _scope_fields(memory)
                json_scope = {
                    name: str(value) if value is not None else None
                    for name, value in scope.items()
                }
                evidence.append(
                    {
                        "memory_id": memory.id,
                        **scope,
                        "content": memory.plaintext_content,
                        "fact_key": memory.fact_key,
                        "confidence": memory.confidence,
                        "kind": "memory",
                    }
                )
                memory_scopes.append({"memory_id": str(memory.id), **json_scope})

            evidence_ids = [memory.id for memory in dormant]
            fact_keys = sorted(
                {str(memory.fact_key) for memory in dormant if memory.fact_key}
            )
            digest = hashlib.sha256(
                ",".join(sorted(str(item) for item in evidence_ids)).encode()
            ).hexdigest()[:24]
            consolidation = CortexConsolidationService(
                proposal_repository=MemoryProposalRepository(
                    session,
                    tenant_id=organization_uuid,
                ),
                observation_repository=ConsolidatedObservationRepository(
                    session,
                    tenant_id=organization_uuid,
                ),
            )
            result = await consolidation.consolidate(
                evidence,
                organization_id=organization_uuid,
                user_id=user_uuid,
                proposal_type="summary",
                payload={
                    "content": "Consolidated dormant memory evidence for review.",
                    "dormant_memory_ids": [str(item) for item in evidence_ids],
                    "memory_scopes": memory_scopes,
                },
                evidence_ids=evidence_ids,
                supporting_ids=evidence_ids,
                fact_keys=fact_keys,
                confidence=0.7,
                idempotency_key=f"dream:{organization_uuid}:{user_uuid}:{digest}",
                metadata={
                    "source": "dream_cycle",
                    "dry_run": False,
                    "canonical": False,
                    "scope": {
                        "organization_id": str(organization_uuid),
                        "user_id": str(user_uuid),
                    },
                },
            )
            if (
                getattr(result.proposal, "canonical_memory_id", None) is not None
                or getattr(result.observation, "applied_memory_id", None) is not None
            ):
                raise RuntimeError("Dream consolidation produced a canonical write.")

            proposal_count = 1
            observation_id = str(result.observation.id)
            proposal_id = str(result.proposal.id)
            dormant_ids = [str(memory.id) for memory in dormant]
            scope = {
                "organization_id": str(organization_uuid),
                "user_id": str(user_uuid),
            }
            dream = DreamRecord(
                user_id=user_uuid,
                organization_id=organization_uuid,
                cycle_type="dream",
                status="completed",
                summary=f"Processed {len(dormant)} dormant memories",
                memory_count=len(dormant),
                insights_generated=proposal_count,
                cycles_completed=1,
                extra_data={
                    "dormant_count": len(dormant),
                    "dormant_ids": dormant_ids,
                    "processed_memory_ids": dormant_ids,
                    "memory_scopes": memory_scopes,
                    "proposal_count": proposal_count,
                    "proposal_id": proposal_id,
                    "observation_id": observation_id,
                    "canonical": False,
                    "scope": scope,
                },
                started_at=now,
                completed_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(dream)
            await session.commit()

            return {
                "status": "completed",
                "dormant_count": len(dormant),
                "proposal_count": proposal_count,
                "proposal_id": proposal_id,
                "observation_id": observation_id,
                "canonical_memory_id": None,
                "dream_id": str(dream.id),
            }
        except Exception:
            await session.rollback()
            raise


@celery_app.task(
    name="contexta.workers.dream_tasks.run_dream_cycle",
    bind=True,
    max_retries=1,
)
def run_dream_cycle(
    self,
    user_id: str,
    organization_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Celery task to run a dream cycle (sync wrapper around async impl)."""
    logger.info(
        "Starting dream cycle task for user_id=%s organization_id=%s.",
        user_id,
        organization_id,
    )
    try:
        return asyncio.run(_run_dream_cycle_async(user_id, organization_id, dry_run))
    except Exception as exc:
        logger.exception("Dream cycle task failed")
        raise self.retry(exc=exc)


async def _dispatch_dream_cycles_async() -> dict[str, Any]:
    if not bool(getattr(get_settings(), "feature_dream_cycle", False)):
        return {
            "status": "disabled",
            "scope_count": 0,
            "scheduled_count": 0,
            "scopes": [],
            "task_ids": [],
        }

    scopes = await _eligible_dream_scopes_async()
    task_ids: list[str] = []
    for organization_uuid, user_uuid in scopes:
        task_result = run_dream_cycle.delay(
            user_id=str(user_uuid),
            organization_id=str(organization_uuid),
        )
        task_id = getattr(task_result, "id", None)
        if task_id:
            task_ids.append(str(task_id))

    return {
        "status": "scheduled" if scopes else "completed",
        "scope_count": len(scopes),
        "scheduled_count": len(scopes),
        "scopes": [
            {
                "organization_id": str(organization_uuid),
                "user_id": str(user_uuid),
            }
            for organization_uuid, user_uuid in scopes
        ],
        "task_ids": task_ids,
    }


@celery_app.task(
    name="contexta.workers.dream_tasks.dispatch_dream_cycles",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def dispatch_dream_cycles(self) -> dict[str, Any]:
    """Celery task to dispatch one dream cycle per eligible user scope."""
    logger.info("Starting dream cycle dispatcher task.")
    try:
        return asyncio.run(_dispatch_dream_cycles_async())
    except Exception as exc:
        logger.exception("Dream cycle dispatcher task failed")
        raise self.retry(exc=exc)


__all__ = [
    "DORMANT_AFTER_HOURS",
    "DORMANT_BATCH_LIMIT",
    "dispatch_dream_cycles",
    "run_dream_cycle",
]
