"""Celery tasks for dream cycle evaluation."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select

from contexta.db import AsyncSessionFactory
from contexta.models.dream import DreamRecord
from contexta.models.memory import MemoryRecord
from contexta.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DORMANT_AFTER_HOURS = 24
DORMANT_BATCH_LIMIT = 50


async def _run_dream_cycle_async(
    user_id: str,
    organization_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a single dream cycle for a user.

    The dream cycle:
    1. Fetches dormant memories (never accessed, or not accessed in 24h+)
    2. Logs a DreamRecord entry (pattern synthesis lives in DreamCycleEngine,
       invoked from the MCP service layer for now)
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    cutoff = now - timedelta(hours=DORMANT_AFTER_HOURS)

    async with AsyncSessionFactory() as session:
        try:
            # Never-accessed memories are the most dormant: include NULLs.
            dormant = (
                (
                    await session.execute(
                        select(MemoryRecord)
                        .where(
                            MemoryRecord.user_id == user_id,
                            or_(
                                MemoryRecord.last_accessed_at.is_(None),
                                MemoryRecord.last_accessed_at < cutoff,
                            ),
                        )
                        .limit(DORMANT_BATCH_LIMIT)
                    )
                )
                .scalars()
                .all()
            )

            if dry_run:
                return {"status": "dry_run", "dormant_count": len(dormant)}

            dream = DreamRecord(
                user_id=user_id,
                organization_id=organization_id,
                cycle_type="dream",
                status="completed",
                summary=f"Processed {len(dormant)} dormant memories",
                memory_count=len(dormant),
                insights_generated=0,
                cycles_completed=1,
                extra_data={
                    "dormant_count": len(dormant),
                    "dormant_ids": [str(m.id) for m in dormant[:10]],
                },
                started_at=now,
                completed_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(dream)
            await session.commit()

            return {
                "status": "completed",
                "dormant_count": len(dormant),
                "dream_id": str(dream.id),
            }
        except Exception:
            await session.rollback()
            raise


@celery_app.task(name="contexta.workers.dream_tasks.run_dream_cycle", bind=True, max_retries=1)
def run_dream_cycle(self, user_id: str, organization_id: str, dry_run: bool = False) -> dict[str, Any]:
    """Celery task to run a dream cycle (sync wrapper around async impl)."""
    logger.info("Starting dream cycle task for user_id=%s.", user_id)
    try:
        return asyncio.run(_run_dream_cycle_async(user_id, organization_id, dry_run))
    except Exception as exc:  # noqa: BLE001 - worker failsafe, retry on any failure
        logger.exception("Dream cycle task failed")
        raise self.retry(exc=exc)
