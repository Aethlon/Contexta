"""Tests for dedicated retrieval endpoints and system management APIs."""

import pytest
from httpx import ASGITransport, AsyncClient

from contexta.api.app import app


@pytest.mark.asyncio
async def test_system_engine_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/system/engine-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "current_mode" in data
        assert "active_engine" in data
        assert "local_model_server" in data
        assert "cloud_providers" in data


@pytest.mark.asyncio
async def test_system_engine_mode_toggle_validation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invalid mode
        resp = await client.post("/v1/system/engine-mode", json={"mode": "invalid_mode"})
        assert resp.status_code == 400

        # Switch to offline
        resp = await client.post("/v1/system/engine-mode", json={"mode": "offline"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "offline"

        # Switch to auto
        resp = await client.post("/v1/system/engine-mode", json={"mode": "auto"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "auto"


@pytest.mark.asyncio
async def test_system_validate_providers():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Missing keys should report errors cleanly without crashing
        resp = await client.post(
            "/v1/system/validate-providers",
            json={
                "llm_provider": "openai",
                "llm_api_key": "",
                "embedding_provider": "openai",
                "embedding_api_key": "",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) >= 2
