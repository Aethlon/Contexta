"""Tests for observation ingestion API endpoints.

Validates payload size limits, required field validation, and batch submission.
"""

import json
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app


@pytest.fixture
def valid_payload() -> dict:
    """Return a minimal valid observation payload."""
    return {
        "user_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "session_id": str(uuid4()),
        "messages": [{"role": "user", "content": "Hello, world!"}],
    }


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPostObservation:
    """Tests for POST /observations endpoint."""

    async def test_valid_payload_returns_202(self, client: AsyncClient, valid_payload: dict) -> None:
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "accepted"

    async def test_valid_payload_with_optional_fields(self, client: AsyncClient, valid_payload: dict) -> None:
        valid_payload["metadata"] = {"source": "test-sdk"}
        valid_payload["policy"] = "coding-agent"
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 202

    async def test_payload_exceeding_1mb_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        # Create a payload that exceeds 1MB
        valid_payload["messages"] = [{"role": "user", "content": "x" * (1024 * 1024)}]
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 422
        data = response.json()
        assert "exceeds maximum" in data["detail"].lower() or "exceeds maximum" in data["errors"][0]["message"].lower()

    async def test_missing_user_id_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        del valid_payload["user_id"]
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 422
        data = response.json()
        assert any(e["field"] == "user_id" for e in data["errors"])

    async def test_missing_organization_id_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        del valid_payload["organization_id"]
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 422
        data = response.json()
        assert any(e["field"] == "organization_id" for e in data["errors"])

    async def test_missing_session_id_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        del valid_payload["session_id"]
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 422
        data = response.json()
        assert any(e["field"] == "session_id" for e in data["errors"])

    async def test_missing_messages_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        del valid_payload["messages"]
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 422
        data = response.json()
        assert any(e["field"] == "messages" for e in data["errors"])

    async def test_missing_multiple_fields_returns_all_errors(self, client: AsyncClient) -> None:
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        response = await client.post("/observations", json=payload)
        assert response.status_code == 422
        data = response.json()
        error_fields = {e["field"] for e in data["errors"]}
        assert "user_id" in error_fields
        assert "organization_id" in error_fields
        assert "session_id" in error_fields

    async def test_invalid_uuid_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        valid_payload["user_id"] = "not-a-uuid"
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 422

    async def test_null_required_field_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        valid_payload["user_id"] = None
        response = await client.post("/observations", json=valid_payload)
        assert response.status_code == 422
        data = response.json()
        assert any(e["field"] == "user_id" for e in data["errors"])

    async def test_invalid_json_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/observations",
            content=b"not json at all",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422

    async def test_payload_exactly_at_limit_accepted(self, client: AsyncClient) -> None:
        """A payload at exactly 1MB should be accepted."""
        # Build a payload that's just under 1MB
        base = {
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "session_id": str(uuid4()),
            "messages": [{"role": "user", "content": ""}],
        }
        base_size = len(json.dumps(base).encode())
        # Fill content to reach just under 1MB
        remaining = (1024 * 1024) - base_size - 10  # small buffer for safety
        base["messages"][0]["content"] = "a" * remaining
        encoded = json.dumps(base).encode()
        assert len(encoded) <= 1024 * 1024

        response = await client.post(
            "/observations",
            content=encoded,
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 202


class TestPostObservationBatch:
    """Tests for POST /observations/batch endpoint."""

    async def test_valid_batch_returns_202(self, client: AsyncClient, valid_payload: dict) -> None:
        batch = [valid_payload, valid_payload]
        response = await client.post("/observations/batch", json=batch)
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert len(data["jobs"]) == 2
        assert all("job_id" in job for job in data["jobs"])

    async def test_batch_exceeding_1mb_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        valid_payload["messages"] = [{"role": "user", "content": "x" * (1024 * 1024)}]
        batch = [valid_payload]
        response = await client.post("/observations/batch", json=batch)
        assert response.status_code == 422

    async def test_batch_with_invalid_item_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        invalid = {"messages": [{"role": "user", "content": "hi"}]}  # missing required fields
        batch = [valid_payload, invalid]
        response = await client.post("/observations/batch", json=batch)
        assert response.status_code == 422
        data = response.json()
        # Errors should reference the index of the invalid item
        assert any("[1]" in e["field"] for e in data["errors"])

    async def test_empty_batch_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/observations/batch", json=[])
        assert response.status_code == 422

    async def test_non_array_body_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        response = await client.post("/observations/batch", json=valid_payload)
        assert response.status_code == 422

    async def test_batch_item_not_object_returns_422(self, client: AsyncClient, valid_payload: dict) -> None:
        batch = [valid_payload, "not an object"]
        response = await client.post("/observations/batch", json=batch)
        assert response.status_code == 422

    async def test_single_item_batch_returns_202(self, client: AsyncClient, valid_payload: dict) -> None:
        batch = [valid_payload]
        response = await client.post("/observations/batch", json=batch)
        assert response.status_code == 202
        data = response.json()
        assert len(data["jobs"]) == 1
