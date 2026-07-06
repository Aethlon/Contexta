"""Tests for contexta API-key management endpoints."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_create_api_key_returns_token_once(client: AsyncClient) -> None:
    organization_id = uuid4()
    actor_id = uuid4()

    response = await client.post(
        "/api-keys",
        json={
            "name": "Production agent",
            "organization_id": str(organization_id),
            "actor_id": str(actor_id),
            "scopes": ["observe", "retrieve"],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["token"].startswith("mk_live_")
    assert data["key"]["name"] == "Production agent"
    assert data["key"]["organization_id"] == str(organization_id)
    assert data["key"]["prefix"] == data["token"][:16]


async def test_list_api_keys_is_tenant_scoped(client: AsyncClient) -> None:
    organization_id = uuid4()
    other_organization_id = uuid4()
    actor_id = uuid4()

    await client.post(
        "/api-keys",
        json={
            "name": "Visible",
            "organization_id": str(organization_id),
            "actor_id": str(actor_id),
            "scopes": ["observe"],
        },
    )
    await client.post(
        "/api-keys",
        json={
            "name": "Hidden",
            "organization_id": str(other_organization_id),
            "actor_id": str(actor_id),
            "scopes": ["retrieve"],
        },
    )

    response = await client.get(
        "/api-keys",
        params={"organization_id": str(organization_id)},
    )

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "Visible" in names
    assert "Hidden" not in names
