"""Embedding generation service."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Awaitable, Callable, Protocol

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
        except Exception as exc:
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
        if self._settings.embedding_provider == "openai":
            return OpenAIEmbeddingProvider(self._settings)
        if self._settings.embedding_provider == "deterministic":
            return DeterministicEmbeddingProvider(self._settings.embedding_dimensions)
        raise EmbeddingError(
            f"Unsupported embedding provider: {self._settings.embedding_provider}"
        )

    def _memory_text(self, memory: MemoryRecord) -> str:
        return f"{memory.title}\n{memory.content}".strip()


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embedding provider."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def embed(self, text: str) -> list[float]:
        if not self._settings.embedding_api_key:
            raise EmbeddingError("Embedding API key not configured.")

        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
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
