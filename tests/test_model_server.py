"""Unit and concurrency tests for Contexta Persistent Model Server."""

import asyncio
import pytest
from httpx import ASGITransport, AsyncClient

from contexta.workers.model_server import app


@pytest.mark.asyncio
async def test_model_server_health_and_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Trigger lifespan
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

        status_resp = await client.get("/models/status")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["embedding_model"]["name"] == "Qwen/Qwen3-Embedding-0.6B"
        assert data["reranker_model"]["name"] == "Qwen/Qwen3-Reranker-0.6B"


@pytest.mark.asyncio
async def test_model_server_embeddings_and_concurrency():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Single embedding test
        resp = await client.post("/v1/embeddings", json={"input": "User prefers PostgreSQL."})
        assert resp.status_code == 200
        result = resp.json()
        assert len(result["data"]) == 1
        assert len(result["data"][0]["embedding"]) == 1024

        # Multi-concurrency batching test: 15 parallel requests
        async def fetch_emb(idx: int):
            r = await client.post("/v1/embeddings", json={"input": f"Concurrent test sentence {idx}"})
            assert r.status_code == 200
            return r.json()["data"][0]["embedding"]

        tasks = [fetch_emb(i) for i in range(15)]
        embeddings = await asyncio.gather(*tasks)
        assert len(embeddings) == 15
        for emb in embeddings:
            assert len(emb) == 1024


@pytest.mark.asyncio
async def test_model_server_classify():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/classify",
            json={
                "texts": [
                    "I prefer dark mode in all applications.",
                    "User was born in San Francisco.",
                    "We plan to launch by Q4 2026.",
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["predictions"]) == 3
        labels = [p["label"] for p in data["predictions"]]
        assert "preference" in labels
        assert "fact" in labels
        assert "goal" in labels


@pytest.mark.asyncio
async def test_model_server_rerank():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/rerank",
            json={
                "query": "Postgres database storage",
                "documents": [
                    "The company uses MongoDB for document storage.",
                    "Postgres database is used for relational data and pgvector storage.",
                    "User likes coffee in the morning.",
                ],
                "top_n": 2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        # Best match should be document index 1
        assert data["results"][0]["index"] == 1
