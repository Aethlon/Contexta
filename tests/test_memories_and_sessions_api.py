"""Tests for memories and sessions API endpoints."""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app
from contexta.models.memory import MemoryRecord
from contexta.models.session import Session
from contexta.models.version import MemoryVersion


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestMemoriesApi:
    """Tests for memories lifecycle, context, and explain routes."""

    async def test_pin_memory_success(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()
        
        # Configure execute to return a result with rowcount = 1 (indicating success)
        mock_result = MagicMock()
        mock_result.rowcount = 1
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.post(f"/memories/{memory_id}/pin", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"] == str(memory_id)
        assert data["is_pinned"] is True

    async def test_pin_memory_not_found(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()

        # Configure execute to return a result with rowcount = 0 (not found/mismatched org)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.post(f"/memories/{memory_id}/pin", headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Memory not found"

    async def test_unpin_memory_success(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.post(f"/memories/{memory_id}/unpin", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"] == str(memory_id)
        assert data["is_pinned"] is False

    async def test_archive_memory_success(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.post(f"/memories/{memory_id}/archive", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"] == str(memory_id)
        assert data["is_archived"] is True

    async def test_restore_memory_success(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.post(f"/memories/{memory_id}/restore", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"] == str(memory_id)
        assert data["is_archived"] is False

    async def test_delete_memory_success(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()

        mock_result = MagicMock()
        mock_result.rowcount = 1
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.delete(f"/memories/{memory_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"] == str(memory_id)
        assert data["deleted"] is True

    async def test_explain_memory_success(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()

        # Mock the memory record
        mock_memory = MemoryRecord(
            id=memory_id,
            user_id=user_id,
            organization_id=org_id,
            memory_type="preference",
            title="Likes tea",
            content="User prefers green tea over coffee",
            source_type="observation",
            confidence=0.9,
            importance=0.8,
            utility_score=0.75,
            tags=["beverages"],
            created_at=datetime.now(timezone.utc),
        )

        # Mock historical versions
        mock_version = MemoryVersion(
            id=uuid4(),
            memory_id=memory_id,
            content="User likes hot drinks",
            importance=0.5,
            valid_from=datetime.now(timezone.utc),
            valid_to=datetime.now(timezone.utc),
            superseded_by_id=memory_id,
        )

        # Mock the db execution flow:
        # First call: fetch MemoryRecord -> scalar_one_or_none()
        # Second call: fetch MemoryVersion list -> scalars().all()
        mock_result_memory = MagicMock()
        mock_result_memory.scalar_one_or_none.return_value = mock_memory

        mock_result_versions = MagicMock()
        mock_result_versions.scalars.return_value.all.return_value = [mock_version]

        override_db_dependency.execute.side_effect = [mock_result_memory, mock_result_versions]

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        response = await client.get(f"/memories/{memory_id}/explain", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["memory_id"] == str(memory_id)
        assert data["scoring"]["confidence"] == 0.9
        assert len(data["supersession_history"]) == 1
        assert data["supersession_history"][0]["content"] == "User likes hot drinks"

    async def test_explain_memory_not_found(self, client: AsyncClient, override_db_dependency) -> None:
        memory_id = uuid4()
        org_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.get(f"/memories/{memory_id}/explain", headers=headers)
        assert response.status_code == 404

    async def test_timeline_success(self, client: AsyncClient, override_db_dependency) -> None:
        org_id = uuid4()
        user_id = uuid4()
        memory_id = uuid4()

        mock_memory = MemoryRecord(
            id=memory_id,
            user_id=user_id,
            organization_id=org_id,
            memory_type="preference",
            title="Likes tea",
            content="User prefers green tea over coffee",
            source_type="observation",
            confidence=0.9,
            importance=0.8,
            utility_score=0.75,
            tags=["beverages"],
            created_at=datetime.now(timezone.utc),
            is_pinned=False,
            is_archived=False,
            memory_state="active",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_memory]
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        response = await client.get(f"/memories/timeline/{user_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_id)
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "created"
        assert data["events"][0]["memory"]["title"] == "Likes tea"

    async def test_get_context_success(self, client: AsyncClient, override_db_dependency) -> None:
        org_id = uuid4()
        user_id = uuid4()
        session_id = uuid4()
        memory_id = uuid4()

        mock_memory = MemoryRecord(
            id=memory_id,
            user_id=user_id,
            organization_id=org_id,
            memory_type="preference",
            title="Prefers hot drinks",
            content="User prefers hot drinks.",
            source_type="observation",
            confidence=0.9,
            importance=0.85,
            tags=["beverages"],
            created_at=datetime.now(timezone.utc),
            is_pinned=False,
            is_archived=False,
            memory_state="active",
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_memory]
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        params = {
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "session_id": str(session_id),
        }
        response = await client.get("/memories/context", params=params, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "preferences" in data
        assert len(data["preferences"]) == 1
        assert data["preferences"][0]["content"] == "User prefers hot drinks."

    async def test_get_context_forbidden_org_mismatch(self, client: AsyncClient) -> None:
        org_id = uuid4()
        other_org_id = uuid4()
        user_id = uuid4()
        session_id = uuid4()

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        params = {
            "user_id": str(user_id),
            "organization_id": str(other_org_id),
            "session_id": str(session_id),
        }
        response = await client.get("/memories/context", params=params, headers=headers)
        assert response.status_code == 403


class TestSessionsApi:
    """Tests for session management routes."""

    async def test_create_session_success(self, client: AsyncClient, override_db_dependency) -> None:
        org_id = uuid4()
        user_id = uuid4()

        mock_session = Session(
            id=uuid4(),
            user_id=user_id,
            organization_id=org_id,
            started_at=datetime.now(timezone.utc),
            metadata_={"test": "data"},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        payload = {
            "user_id": str(user_id),
            "organization_id": str(org_id),
            "metadata": {"test": "data"},
        }
        response = await client.post("/sessions", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["user_id"] == str(user_id)
        assert data["organization_id"] == str(org_id)

    async def test_create_session_forbidden_mismatch(self, client: AsyncClient) -> None:
        org_id = uuid4()
        other_org_id = uuid4()
        user_id = uuid4()

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        payload = {
            "user_id": str(user_id),
            "organization_id": str(other_org_id),
            "metadata": {},
        }
        response = await client.post("/sessions", json=payload, headers=headers)
        assert response.status_code == 403

    async def test_end_session_success(self, client: AsyncClient, override_db_dependency) -> None:
        session_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()

        mock_session = Session(
            id=session_id,
            user_id=user_id,
            organization_id=org_id,
            started_at=datetime.now(timezone.utc),
        )

        # First call: fetch session -> scalar_one_or_none
        mock_result_get = MagicMock()
        mock_result_get.scalar_one_or_none.return_value = mock_session

        # Second call: update -> rowcount
        mock_result_update = MagicMock()
        mock_result_update.rowcount = 1

        override_db_dependency.execute.side_effect = [mock_result_get, mock_result_update]

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        response = await client.post(f"/sessions/{session_id}/end", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == str(session_id)
        assert "ended_at" in data

    async def test_end_session_not_found(self, client: AsyncClient, override_db_dependency) -> None:
        session_id = uuid4()
        org_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        override_db_dependency.execute.return_value = mock_result

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(uuid4()),
        }
        response = await client.post(f"/sessions/{session_id}/end", headers=headers)
        assert response.status_code == 404

    async def test_inspect_user_success(self, client: AsyncClient, override_db_dependency) -> None:
        org_id = uuid4()
        user_id = uuid4()
        session_id = uuid4()

        mock_session = Session(
            id=session_id,
            user_id=user_id,
            organization_id=org_id,
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            metadata_={"foo": "bar"},
        )

        mock_memory = MemoryRecord(
            id=uuid4(),
            user_id=user_id,
            organization_id=org_id,
            memory_type="fact",
            title="Fact 1",
            content="Something interesting",
            source_type="observation",
            confidence=0.9,
            importance=0.5,
            created_at=datetime.now(timezone.utc),
            session_id=session_id,
        )

        # First query: get_by_user on Session -> scalars().all()
        mock_result_sessions = MagicMock()
        mock_result_sessions.scalars.return_value.all.return_value = [mock_session]

        # Second query: get_by_session on Memory -> scalars().all()
        mock_result_memories = MagicMock()
        mock_result_memories.scalars.return_value.all.return_value = [mock_memory]

        override_db_dependency.execute.side_effect = [mock_result_sessions, mock_result_memories]

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        response = await client.get(f"/sessions/inspect/{user_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_id)
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["memories_count"] == 1
        assert data["sessions"][0]["memories"][0]["title"] == "Fact 1"

    async def test_get_session_summary_success(self, client: AsyncClient, override_db_dependency) -> None:
        session_id = uuid4()
        org_id = uuid4()
        user_id = uuid4()

        mock_session = Session(
            id=session_id,
            user_id=user_id,
            organization_id=org_id,
            started_at=datetime.now(timezone.utc),
            ended_at=None,
            metadata_={"topic": "pricing"},
        )

        mock_memory = MemoryRecord(
            id=uuid4(),
            user_id=user_id,
            organization_id=org_id,
            memory_type="fact",
            title="Fact 1",
            content="Something interesting",
            source_type="observation",
            confidence=0.9,
            importance=0.5,
            created_at=datetime.now(timezone.utc),
            session_id=session_id,
        )

        # First query: get session by ID -> scalar_one_or_none
        mock_result_session = MagicMock()
        mock_result_session.scalar_one_or_none.return_value = mock_session

        # Second query: get memories by session -> scalars().all()
        mock_result_memories = MagicMock()
        mock_result_memories.scalars.return_value.all.return_value = [mock_memory]

        override_db_dependency.execute.side_effect = [mock_result_session, mock_result_memories]

        headers = {
            "x-organization-id": str(org_id),
            "x-user-id": str(user_id),
        }
        response = await client.get(f"/sessions/{session_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == str(session_id)
        assert data["memory_count"] == 1
        assert data["metadata"]["topic"] == "pricing"
        assert "earliest_memory_created_at" in data
