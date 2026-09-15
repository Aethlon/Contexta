"""Tests for Contexta audit log endpoint."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app
from contexta.models.audit import AuditLog


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_get_audit_empty(client: AsyncClient) -> None:
    org_id = uuid4()
    response = await client.get(
        "/v1/audit",
        headers={"x-organization-id": str(org_id)},
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_get_audit_returns_entries(client: AsyncClient, override_db_dependency) -> None:
    org_id = uuid4()
    actor_id = uuid4()

    mock_log = AuditLog(
        id=uuid4(),
        organization_id=org_id,
        actor_id=actor_id,
        operation_type="memory_created",
        target_id=uuid4(),
        details={"title": "Test Memory"},
        created_at=datetime.now(timezone.utc),
    )

    # Configure the mock DB session in conftest to return our mock_log
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_log]
    override_db_dependency.execute.return_value = mock_result

    response = await client.get(
        "/v1/audit",
        headers={"x-organization-id": str(org_id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["operation_type"] == "memory_created"
    assert data[0]["organization_id"] == str(org_id)
    assert data[0]["details"]["title"] == "Test Memory"
