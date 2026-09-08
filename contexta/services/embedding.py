"""Embedding generation service."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol

from contexta.config.settings import Settings, get_settings
from contexta.models.memory import MemoryRecord

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]:
        ...


class EmbeddingRepository(Protocol):
    async def update_by_id(self, record_id: uuid.UUID, values: dict) -> int:
        ...


RetryEnqueue = Callable[[uuid.UUID], Awaitable[None] | None]


class EmbeddingService:
    """Generate and persist vector embeddings for memories."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        provider: EmbeddingProvider | None = None,
        retry_enqueue: RetryEnqueue | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._provider = provider or self._create_provider()
        self._retry_enqueue = retry_enqueue

    async def embed_memory(self, memory: MemoryRecord) -> list[float]:
        """Generate embedding from memory title plus content."""
        return await self.embed_text(self._memory_text(memory))

    async def embed_text(self, text: str) -> list[float]:
        """Generate an embedding and validate its dimensions."""
        embedding = await self._provider.embed(text)
        if len(embedding) != self._settings.embedding_dimensions:
            raise EmbeddingError(
                "Embedding dimension mismatch: "
                f"expected {self._settings.embedding_dimensions}, got {len(embedding)}"
            )
        return embedding

    async def generate_and_store(
        self,
        memory: MemoryRecord,
        repository: EmbeddingRepository,
        *,
        enqueue_on_failure: bool = True,
    ) -> bool:
        """Generate and store embedding; return False on graceful degradation."""
        try:
            embedding = await self.embed_memory(memory)
        except Exception as exc:  # noqa: BLE001 - graceful degradation on provider failure
            logger.warning(
                "Embedding generation failed for memory_id=%s: %s",
                memory.id,
                exc,
            )
            if enqueue_on_failure and self._retry_enqueue is not None:
                maybe_awaitable = self._retry_enqueue(memory.id)
                if maybe_awaitable is not None:
                    await maybe_awaitable
            return False

        await repository.update_by_id(memory.id, {"embedding": embedding})
        memory.embedding = embedding
        return True

    def _create_provider(self) -> EmbeddingProvider:
        if self._settings.engine_mode == "offline" or self._settings.embedding_provider in ("local", "qwen", "offline"):
            return LocalModelServerEmbeddingProvider(self._settings)
        if self._settings.embedding_provider == "openai":
            return OpenAIEmbeddingProvider(self._settings)
        if self._settings.embedding_provider == "deterministic":
            return DeterministicEmbeddingProvider(self._settings.embedding_dimensions)
        raise EmbeddingError(
            f"Unsupported embedding provider: {self._settings.embedding_provider}"
        )

    def _memory_text(self, memory: MemoryRecord) -> str:
        return f"{memory.title}\n{memory.content}".strip()


class LocalModelServerEmbeddingProvider:
    """Connects to the persistent Contexta Local Model Server running Qwen/Qwen3-Embedding-0.6B."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def embed(self, text: str) -> list[float]:
        import httpx

        url = getattr(self._settings, "local_model_server_url", "http://localhost:8001")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{url}/v1/embeddings",
                    json={"input": text, "model": "Qwen/Qwen3-Embedding-0.6B"},
                )
                response.raise_for_status()
                data = response.json()
                raw_emb = [float(val) for val in data["data"][0]["embedding"]]
                # Pad or slice to expected dimensions if needed
                expected_dim = self._settings.embedding_dimensions
                if len(raw_emb) < expected_dim:
                    raw_emb = raw_emb + [0.0] * (expected_dim - len(raw_emb))
                elif len(raw_emb) > expected_dim:
                    raw_emb = raw_emb[:expected_dim]
                return raw_emb
        except Exception as exc:
            logger.warning(
                "Local model server call failed (%s). Falling back to deterministic local provider.",
                exc,
            )
            fallback = DeterministicEmbeddingProvider(self._settings.embedding_dimensions)
            return await fallback.embed(text)


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embedding provider with local model server fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._local_fallback = LocalModelServerEmbeddingProvider(settings)

    async def embed(self, text: str) -> list[float]:
        if not self._settings.embedding_api_key:
            logger.info("OpenAI embedding API key missing; falling back to persistent local model server.")
            return await self._local_fallback.embed(text)

        import httpx

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._settings.embedding_base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._settings.embedding_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._settings.embedding_model,
                        "input": text,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return [float(value) for value in data["data"][0]["embedding"]]
        except Exception as exc:
            logger.warning(
                "Cloud embedding call failed (%s); routing through local model server fallback.",
                exc,
            )
            return await self._local_fallback.embed(text)


class DeterministicEmbeddingProvider:
    """Deterministic local provider useful for tests and offline development."""

    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < self._dimensions:
            for byte in digest:
                values.append((byte / 255.0) * 2 - 1)
                if len(values) == self._dimensions:
                    break
            digest = hashlib.sha256(digest).digest()
        return values
