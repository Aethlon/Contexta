"""Tests for entity state management."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from contexta.core.entities.state_manager import EntityStateManager
from contexta.core.errors import ValidationError
from contexta.core.schemas import ExtractedMemory
from contexta.core.types import MemoryType, SourceType
from contexta.models.entity import Entity


class FakeEntityStateRepository:
    def __init__(self, entity: Entity) -> None:
        self.entity = entity
        self.updates: list[tuple[UUID, dict]] = []

    async def get_by_id(self, record_id: UUID) -> Entity | None:
        if self.entity.id == record_id:
            return self.entity
        return None

    async def update_by_id(self, record_id: UUID, values: dict) -> int:
        self.updates.append((record_id, values))
        for key, value in values.items():
            setattr(self.entity, key, value)
        return 1


def make_entity(status: str = "active", last_updated: datetime | None = None) -> Entity:
    return Entity(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
        entity_type="project",
        name="contexta",
        summary=None,
        status=status,
        aggregated_attributes={},
        last_updated=last_updated or datetime.now(timezone.utc),
    )


def make_memory(memory_type: MemoryType = MemoryType.FACT) -> ExtractedMemory:
    return ExtractedMemory(
        memory_type=memory_type,
        source_type=SourceType.USER_EXPLICIT,
        title="contexta fact",
        content="contexta uses FastAPI.",
        structured_data={"framework": "fastapi"},
    )


async def test_update_on_memory_link_refreshes_summary_and_attributes() -> None:
    entity = make_entity()
    repo = FakeEntityStateRepository(entity)
    manager = EntityStateManager(repo)
    observed_at = datetime.now(timezone.utc)

    values = await manager.update_on_memory_link(
        entity.id,
        make_memory(MemoryType.FACT),
        observed_at=observed_at,
    )

    assert values["summary"] == "contexta uses FastAPI."
    assert values["last_updated"] == observed_at
    assert values["aggregated_attributes"]["facts"] == ["contexta uses FastAPI."]
    assert values["aggregated_attributes"]["structured_data"] == {
        "framework": "fastapi"
    }


async def test_inactive_entity_reactivates_on_new_memory() -> None:
    entity = make_entity(status="inactive")
    repo = FakeEntityStateRepository(entity)
    manager = EntityStateManager(repo)

    values = await manager.update_on_memory_link(entity.id, make_memory())

    assert values["status"] == "active"


async def test_valid_state_transitions() -> None:
    entity = make_entity(status="active")
    repo = FakeEntityStateRepository(entity)
    manager = EntityStateManager(repo)

    await manager.transition(entity.id, "inactive")
    assert entity.status == "inactive"

    await manager.transition(entity.id, "archived")
    assert entity.status == "archived"


async def test_invalid_state_transition_raises() -> None:
    entity = make_entity(status="active")
    repo = FakeEntityStateRepository(entity)
    manager = EntityStateManager(repo)

    with pytest.raises(ValidationError):
        await manager.transition(entity.id, "archived")


async def test_active_entity_transitions_inactive_after_90_days() -> None:
    now = datetime.now(timezone.utc)
    entity = make_entity(last_updated=now - timedelta(days=91))
    repo = FakeEntityStateRepository(entity)
    manager = EntityStateManager(repo)

    transitioned = await manager.transition_inactive_if_stale(entity.id, now=now)

    assert transitioned is True
    assert entity.status == "inactive"


async def test_recent_entity_stays_active() -> None:
    now = datetime.now(timezone.utc)
    entity = make_entity(last_updated=now - timedelta(days=10))
    repo = FakeEntityStateRepository(entity)
    manager = EntityStateManager(repo)

    transitioned = await manager.transition_inactive_if_stale(entity.id, now=now)

    assert transitioned is False
    assert entity.status == "active"
