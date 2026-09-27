"""Embedding generation service."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm.attributes import set_committed_value

from contexta.config.settings import EmbeddingProfile, Settings, get_settings
from contexta.models.memory import MemoryContentDecryptionError, MemoryRecord

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Base exception for embedding generation and persistence failures."""


class EmbeddingProfileError(EmbeddingError):
    """Raised when the configured embedding profile is invalid."""


class EmbeddingDimensionError(EmbeddingError):
    """Raised when a provider returns a vector with an incompatible width."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when the configured provider cannot produce a vector."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the active profile cannot be used by its configured provider."""


class EmbeddingCompatibilityError(EmbeddingError):
    """Raised when a stored vector cannot be used with the active profile."""


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]:
        ...


class EmbeddingRepository(Protocol):
    async def update_by_id(self, record_id: uuid.UUID, values: dict) -> int:
        ...


RetryEnqueue = Callable[[uuid.UUID], Awaitable[None] | None]


class EmbeddingService:
    """Generate and persist vectors for one explicit embedding profile."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        provider: EmbeddingProvider | None = None,
        retry_enqueue: RetryEnqueue | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._profile = self._resolve_profile()
        self._provider = provider or self._create_provider()
        self._retry_enqueue = retry_enqueue
        self._cache_disabled = False
        self._redis_client: Any = None

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    @property
    def metadata(self) -> dict[str, str | int]:
        return {
            "embedding_profile": self._profile.name,
            "embedding_model": self._profile.model,
            "embedding_version": self._profile.version,
            "embedding_dimensions": self._profile.dimensions,
        }

    async def embed_memory(self, memory: MemoryRecord) -> list[float]:
        return await self.embed_text(self._memory_text(memory))

    async def embed_text(self, text: str) -> list[float]:
        """Embed free text, using a short-lived Redis cache for repeated queries.

        Retrieval is dominated by this call: a single query embedding measured ~90 ms
        on CPU, and agent workloads re-issue the same or near-identical queries far
        more often than they invent new ones. The cache is keyed by the active
        profile and the exact text, so a profile switch can never serve a vector from
        the wrong model. Every cache interaction is fail-open: if Redis is unavailable
        the embedding is simply computed.
        """
        key = self._cache_key(text)
        if key is not None:
            cached = await self._cache_get(key)
            if cached is not None:
                return cached
        embedding = await self._provider.embed(text)
        validated = self.validate_embedding(embedding)
        if key is not None:
            await self._cache_set(key, validated)
        return validated

    def _cache_key(self, text: str) -> str | None:
        normalized = " ".join(text.split())
        if not normalized:
            return None
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"embedq:{self._profile.name}:{self._profile.version}:{digest}"

    async def _cache_get(self, key: str) -> list[float] | None:
        client = self._cache_client()
        if client is None:
            return None
        try:
            raw = await client.get(key)
        except Exception:
            logger.debug("Embedding cache read failed for %s", key, exc_info=True)
            return None
        if not raw:
            return None
        try:
            values = json.loads(raw)
            vector = [float(value) for value in values]
        except (TypeError, ValueError, json.JSONDecodeError):
            # A poisoned or stale-format entry must never break retrieval.
            return None
        if len(vector) != self._profile.dimensions:
            return None
        return vector

    async def _cache_set(self, key: str, vector: list[float]) -> None:
        client = self._cache_client()
        if client is None:
            return
        try:
            await client.set(key, json.dumps(vector), ex=self._cache_ttl_seconds())
        except Exception:
            logger.debug("Embedding cache write failed for %s", key, exc_info=True)

    def _cache_client(self):
        if self._cache_disabled:
            return None
        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis

                self._redis_client = aioredis.from_url(self._settings.redis_url)
            except Exception:
                logger.debug("Embedding cache unavailable", exc_info=True)
                self._cache_disabled = True
                return None
        return self._redis_client

    @staticmethod
    def _cache_ttl_seconds() -> int:
        return 900

    def validate_embedding(self, embedding: Any) -> list[float]:
        try:
            values = list(embedding)
        except TypeError as exc:
            raise EmbeddingDimensionError(
                f"Embedding profile '{self._profile.name}' expected "
                f"{self._profile.dimensions} numeric values, but the provider returned "
                f"{type(embedding).__name__}."
            ) from exc
        try:
            normalized = [float(value) for value in values]
        except (TypeError, ValueError) as exc:
            raise EmbeddingDimensionError(
                f"Embedding profile '{self._profile.name}' returned non-numeric vector values."
            ) from exc
        if len(normalized) != self._profile.dimensions:
            raise EmbeddingDimensionError(
                f"Embedding dimension mismatch for profile '{self._profile.name}': expected "
                f"{self._profile.dimensions}, got {len(normalized)} from model "
                f"'{self._profile.model}'. Set CONTEXTA_EMBEDDING_PROFILE and "
                "CONTEXTA_EMBEDDING_DIMENSIONS to the matching profile; vectors are never "
                "padded or truncated."
            )
        if any(not math.isfinite(value) for value in normalized):
            raise EmbeddingDimensionError(
                f"Embedding profile '{self._profile.name}' returned a non-finite vector from model "
                f"'{self._profile.model}'."
            )
        return normalized

    def ensure_memory_compatible(self, memory: MemoryRecord) -> None:
        vectors = self._stored_vectors(memory)
        metadata = {
            "embedding_profile": memory.embedding_profile,
            "embedding_model": memory.embedding_model,
            "embedding_version": memory.embedding_version,
            "embedding_dimensions": memory.embedding_dimensions,
        }
        present = [value is not None for value in metadata.values()]
        if any(present) and not all(present):
            raise EmbeddingCompatibilityError(self._compatibility_message(memory, vectors, metadata))
        if vectors and not all(present):
            raise EmbeddingCompatibilityError(self._compatibility_message(memory, vectors, metadata))
        if not all(present):
            return
        stored_profile = str(metadata["embedding_profile"])
        stored_model = str(metadata["embedding_model"])
        stored_version = str(metadata["embedding_version"])
        try:
            stored_dimensions = int(metadata["embedding_dimensions"])
        except (TypeError, ValueError) as exc:
            raise EmbeddingCompatibilityError(
                self._compatibility_message(memory, vectors, metadata)
            ) from exc
        if (
            stored_profile != self._profile.name
            or stored_model != self._profile.model
            or stored_version != self._profile.version
            or stored_dimensions != self._profile.dimensions
        ):
            raise EmbeddingCompatibilityError(self._compatibility_message(memory, vectors, metadata))
        for _, vector, dimensions in vectors:
            if dimensions != self._profile.dimensions:
                raise EmbeddingCompatibilityError(
                    self._compatibility_message(memory, vectors, metadata)
                )

    async def generate_and_store(
        self,
        memory: MemoryRecord,
        repository: EmbeddingRepository,
        *,
        enqueue_on_failure: bool = True,
    ) -> bool:
        self.ensure_memory_compatible(memory)
        try:
            embedding = await self.embed_memory(memory)
        except (
            EmbeddingCompatibilityError,
            EmbeddingConfigurationError,
            EmbeddingDimensionError,
            EmbeddingProfileError,
        ):
            raise
        except MemoryContentDecryptionError:
            raise
        except (EmbeddingError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(
                "Embedding generation failed for memory_id=%s: %s",
                memory.id,
                exc,
            )
            await self._enqueue_retry(memory.id, enqueue_on_failure)
            return False
        await self.persist_embedding(memory, repository, embedding)
        return True

    async def persist_embedding(
        self,
        memory: MemoryRecord,
        repository: EmbeddingRepository,
        embedding: list[float],
    ) -> int:
        self.ensure_memory_compatible(memory)
        normalized = self.validate_embedding(embedding)
        store = (
            getattr(repository, "store_embedding", None)
            if hasattr(type(repository), "store_embedding")
            else None
        )
        if callable(store):
            rows = await store(memory.id, normalized, self._profile)
        else:
            rows = await repository.update_by_id(
                memory.id,
                {
                    self._profile.storage_column: normalized,
                    **self.metadata,
                },
            )
        if rows is None or rows == 0:
            raise EmbeddingError(
                f"Embedding persistence failed for memory_id={memory.id}; the tenant-scoped record "
                "was not updated."
            )
        self._apply_embedding_state(memory, normalized)
        return rows

    async def _enqueue_retry(self, memory_id: uuid.UUID, enabled: bool) -> None:
        if not enabled or self._retry_enqueue is None:
            return
        maybe_awaitable = self._retry_enqueue(memory_id)
        if maybe_awaitable is not None:
            await maybe_awaitable

    def _resolve_profile(self) -> EmbeddingProfile:
        try:
            profile = self._settings.embedding_profile_definition()
        except ValueError as exc:
            raise EmbeddingProfileError(str(exc)) from exc
        mode = str(self._settings.engine_mode).strip().casefold()
        if profile.provider == "local" and mode == "online":
            raise EmbeddingProfileError(
                "CONTEXTA_ENGINE_MODE=online is incompatible with the offline 1024 profile; "
                "select online-openai-1536 or use engine mode auto/offline."
            )
        if profile.provider == "openai" and mode == "offline":
            raise EmbeddingProfileError(
                "CONTEXTA_ENGINE_MODE=offline is incompatible with the online 1536 profile; "
                "select offline-qwen3-1024 or use engine mode auto/online."
            )
        return profile

    def _create_provider(self) -> EmbeddingProvider:
        if self._profile.provider == "local":
            return LocalModelServerEmbeddingProvider(self._settings, self._profile)
        if self._profile.provider == "openai":
            return OpenAIEmbeddingProvider(self._settings, self._profile)
        if self._profile.provider == "deterministic":
            return DeterministicEmbeddingProvider(self._profile.dimensions)
        raise EmbeddingProfileError(
            f"Unsupported embedding provider '{self._profile.provider}' for profile "
            f"'{self._profile.name}'."
        )

    def _memory_text(self, memory: MemoryRecord) -> str:
        title = str(memory.title or "")
        return f"{title}\n{memory.plaintext_content}".strip()

    def _stored_vectors(
        self,
        memory: MemoryRecord,
    ) -> list[tuple[str, Any, int]]:
        vectors: list[tuple[str, Any, int]] = []
        for name in ("embedding_1024", "embedding"):
            value = getattr(memory, name, None)
            if value is None:
                continue
            try:
                dimensions = len(value)
            except TypeError as exc:
                raise EmbeddingCompatibilityError(
                    f"Memory {memory.id} has an unreadable {name} vector."
                ) from exc
            if name == "embedding" and dimensions == 1024 and any(
                item[2] == 1024 for item in vectors
            ):
                continue
            vectors.append((name, value, dimensions))
        return vectors

    def _compatibility_message(
        self,
        memory: MemoryRecord,
        vectors: list[tuple[str, Any, int]],
        metadata: dict[str, Any],
    ) -> str:
        stored = ", ".join(
            f"{name}={dimensions}d" for name, _, dimensions in vectors
        ) or "no stored vector"
        return (
            f"Embedding compatibility failure for memory {memory.id}: stored {stored}; "
            f"stored profile={metadata['embedding_profile']!r}, model={metadata['embedding_model']!r}, "
            f"version={metadata['embedding_version']!r}, dimensions={metadata['embedding_dimensions']!r}; "
            f"active profile={self._profile.name!r}, model={self._profile.model!r}, "
            f"version={self._profile.version!r}, dimensions={self._profile.dimensions}. "
            "Select the matching embedding profile or run an explicit, reviewed backfill; "
            "automatic re-embedding is disabled."
        )

    def _apply_embedding_state(
        self,
        memory: MemoryRecord,
        embedding: list[float],
    ) -> None:
        try:
            state = sa_inspect(memory)
        except NoInspectionAvailable:
            state = None
        committed = bool(
            state is not None
            and (
                getattr(state, "persistent", False)
                or getattr(state, "detached", False)
                or getattr(state, "pending", False)
            )
        )

        def set_value(name: str, value: Any) -> None:
            if committed:
                set_committed_value(memory, name, value)
            else:
                setattr(memory, name, value)

        if self._profile.storage_column == "embedding_1024":
            set_value("embedding_1024", embedding)
            set_value("embedding", None)
        else:
            set_value("embedding_1024", None)
            set_value("embedding", embedding)
        for name, value in self.metadata.items():
            set_value(name, value)


class LocalModelServerEmbeddingProvider:
    """Connects to the persistent Contexta local model server."""

    def __init__(self, settings: Settings, profile: EmbeddingProfile | None = None) -> None:
        self._settings = settings
        self._profile = profile or settings.embedding_profile_definition()

    async def embed(self, text: str) -> list[float]:
        import httpx

        if not getattr(self._settings, "local_model_server_enabled", True):
            raise EmbeddingConfigurationError(
                "The offline Qwen3 embedding profile requires the local model server, but "
                "CONTEXTA_LOCAL_MODEL_SERVER_ENABLED is false. Enable the model server or select "
                "the explicitly configured online profile."
            )
        url = str(self._settings.local_model_server_url).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{url}/v1/embeddings",
                    json={"input": text, "model": self._profile.model},
                )
                response.raise_for_status()
                data = response.json()
                response_model = str(data.get("model", ""))
                if response_model != self._profile.model:
                    raise EmbeddingCompatibilityError(
                        f"Local model server returned model {response_model!r} for configured "
                        f"profile {self._profile.name!r} ({self._profile.model!r}); refusing to "
                        "store a vector from a different profile."
                    )
                raw_embedding = data["data"][0]["embedding"]
                values = [float(value) for value in raw_embedding]
                if len(values) != self._profile.dimensions:
                    raise EmbeddingDimensionError(
                        f"Local provider returned {len(values)} dimensions for profile "
                        f"'{self._profile.name}', expected {self._profile.dimensions}; vectors are "
                        "never padded or truncated."
                    )
                return values
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(
                f"Local Qwen3 embedding server at {url} failed for profile "
                f"'{self._profile.name}': {exc}. Start the model server or select the matching "
                "configured profile; no cross-profile fallback is used."
            ) from exc


class OpenAIEmbeddingProvider:
    """OpenAI-compatible embedding provider for the online profile."""

    def __init__(self, settings: Settings, profile: EmbeddingProfile | None = None) -> None:
        self._settings = settings
        self._profile = profile or settings.embedding_profile_definition()

    async def embed(self, text: str) -> list[float]:
        import httpx

        if not self._settings.embedding_api_key:
            raise EmbeddingConfigurationError(
                "The online OpenAI 1536 embedding profile requires CONTEXTA_EMBEDDING_API_KEY. "
                "Set the key or select offline-qwen3-1024; the service does not substitute a "
                "1024-dimensional local vector."
            )
        url = str(self._settings.embedding_base_url).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._settings.embedding_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self._profile.model, "input": text},
                )
                response.raise_for_status()
                data = response.json()
                raw_embedding = data["data"][0]["embedding"]
                values = [float(value) for value in raw_embedding]
                if len(values) != self._profile.dimensions:
                    raise EmbeddingDimensionError(
                        f"Online provider returned {len(values)} dimensions for profile "
                        f"'{self._profile.name}', expected {self._profile.dimensions}; vectors are "
                        "never padded or truncated."
                    )
                return values
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingProviderError(
                f"Online embedding request failed for profile '{self._profile.name}' at {url}: {exc}. "
                "Fix the provider configuration or select the offline profile; no cross-profile "
                "fallback is used."
            ) from exc


class DeterministicEmbeddingProvider:
    """Deterministic provider for explicit tests and deterministic development."""

    def __init__(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise EmbeddingProfileError("Deterministic embeddings require a positive dimension count.")
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
