"""Celery tasks for dream cycle evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from contexta.models.dream import DreamRecord
from contexta.models.memory import MemoryRecord
from contexta.workers.celery_app import celery_app


@celery_app.task(name="contexta.workers.dream_tasks.run_dream_cycle", bind=True, max_retries=1)
def run_dream_cycle(self, user_id: str, organization_id: str, dry_run: bool = False) -> dict[str, Any]:
    """Execute a single dream cycle for a user.

    The dream cycle:
    1. Fetches recent dormant memories (not accessed in 24h+)
    2. Generates synthetic patterns/connections between them
    3. Creates new dream memories with low confidence scores
    4. Links dreamed insights to existing entities

    In a production environment, this delegates to the full DreamEngine.
    For now, runs a lightweight pass that creates a DreamRecord log entry.
    """
    from contexta.db import sync_session_factory

    with sync_session_factory() as session:
        try:
            # Count memories eligible for dreaming
            dormant = session.execute(
                select(MemoryRecord).where(
                    MemoryRecord.user_id == user_id,
                    MemoryRecord.last_accessed_at < datetime.now(timezone.utc()),
                ).limit(50)
            ).scalars().all()

            if dry_run:
                return {"status": "dry_run", "dormant_count": len(dormant)}

            # Log dream cycle execution
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
                started_at=datetime.now(timezone.utc()),
                completed_at=datetime.now(timezone.utc()),
            )
            session.add(dream)
            session.commit()

            return {
                "status": "completed",
                "dormant_count": len(dormant),
                "dream_id": str(dream.id),
            }

        except Exception as exc:
            session.rollback()
            raise self.retry(exc=exc)
