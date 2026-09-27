"""Application settings using Pydantic BaseSettings.

Configuration is loaded from environment variables with sensible defaults
for local development. All settings can be overridden via environment
variables or a .env file.
"""

import json
import os
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class EmbeddingProfile:
    name: str
    dimensions: int
    model: str
    version: str
    provider: str
    storage_column: str


OFFLINE_EMBEDDING_PROFILE = EmbeddingProfile(
    name="offline-qwen3-1024",
    dimensions=1024,
    model="Qwen/Qwen3-Embedding-0.6B",
    version="qwen3-embedding-0.6b-v1",
    provider="local",
    storage_column="embedding_1024",
)
ONLINE_EMBEDDING_PROFILE = EmbeddingProfile(
    name="online-openai-1536",
    dimensions=1536,
    model="text-embedding-3-small",
    version="text-embedding-3-small-v1",
    provider="openai",
    storage_column="embedding",
)
DETERMINISTIC_EMBEDDING_PROFILE = EmbeddingProfile(
    name="deterministic",
    dimensions=0,
    model="deterministic",
    version="deterministic-v1",
    provider="deterministic",
    storage_column="embedding",
)
EMBEDDING_PROFILE_ALIASES = {
    "offline": OFFLINE_EMBEDDING_PROFILE.name,
    "local": OFFLINE_EMBEDDING_PROFILE.name,
    "qwen": OFFLINE_EMBEDDING_PROFILE.name,
    "qwen3": OFFLINE_EMBEDDING_PROFILE.name,
    "qwen3-1024": OFFLINE_EMBEDDING_PROFILE.name,
    "online": ONLINE_EMBEDDING_PROFILE.name,
    "openai": ONLINE_EMBEDDING_PROFILE.name,
    "openai-1536": ONLINE_EMBEDDING_PROFILE.name,
    "deterministic": DETERMINISTIC_EMBEDDING_PROFILE.name,
}
PRODUCTION_EMBEDDING_PROFILES = {
    OFFLINE_EMBEDDING_PROFILE.name: OFFLINE_EMBEDDING_PROFILE,
    ONLINE_EMBEDDING_PROFILE.name: ONLINE_EMBEDDING_PROFILE,
}
HNSW_ITERATIVE_SCAN_MODES = ("off", "relaxed_order", "strict_order")


def embedding_profile_for_dimensions(dimensions: int) -> EmbeddingProfile:
    if dimensions == OFFLINE_EMBEDDING_PROFILE.dimensions:
        return OFFLINE_EMBEDDING_PROFILE
    if dimensions == ONLINE_EMBEDDING_PROFILE.dimensions:
        return ONLINE_EMBEDDING_PROFILE
    raise ValueError(
        f"Unsupported embedding dimension {dimensions}. Use the offline 1024-dimensional "
        "profile or the online 1536-dimensional profile; vectors are never padded or truncated."
    )


def get_engine_state_file() -> Path:
    """Resolve the persistent engine state file location."""
    base = os.environ.get("MODEL_CACHE_DIR", os.environ.get("CONTEXTA_MODEL_CACHE_DIR", "models"))
    p = Path(base)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p / "engine_state.json"


def load_persisted_engine_mode() -> str | None:
    """Load engine mode from persistent storage if present."""
    state_file = get_engine_state_file()
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            mode = data.get("mode")
            if mode in ("offline", "online", "auto"):
                return mode
        except (OSError, TypeError, ValueError):
            return None
    return None


def persist_engine_mode(mode: str) -> None:
    """Save engine mode to persistent storage and update active settings."""
    state_file = get_engine_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"mode": mode, "updated_at": time.time()}), encoding="utf-8")
    s = get_settings()
    s.engine_mode = mode


class Settings(BaseSettings):
    """contexta application settings."""

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTA_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/contexta"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False
    db_boot_check: bool = False

    # Sentry DSN
    sentry_dsn: str = ""

    # CORS Allowed Origins
    cors_allowed_origins: list[str] = ["http://localhost:3000"]

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl_seconds: int = 300

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_always_eager: bool = True

    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dimensions: int = 1024
    embedding_provider: str = "local"
    embedding_profile: str = OFFLINE_EMBEDDING_PROFILE.name
    embedding_version: str = OFFLINE_EMBEDDING_PROFILE.version
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"

    # LLM provider (offline-first: local model-server; set online + keys for cloud)
    llm_provider: str = "local"
    llm_model: str = "contexta-lfm-extract"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"

    # Fine-tuned local extractor. The inference server exposes a contract-native
    # /v1/extract endpoint, so extraction never needs prompt assembly here.
    inference_server_url: str = "http://inference-server:8002"
    inference_timeout_seconds: float = 300.0

    # Engine Mode & Local Model Server
    engine_mode: str = "auto"  # "offline", "online", "auto"
    local_model_server_url: str = "http://localhost:8001"
    local_model_server_enabled: bool = True
    validate_online_providers_at_startup: bool = True

    # Feature flags
    feature_sensitive_data_filter: bool = True
    feature_dream_cycle: bool = False
    feature_cortex: bool = True

    # Contexta Cortex (JEV Decision & Routing Layer)
    jev_api_key: str = ""
    jev_base_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = 1.5
    cortex_early_skip_enabled: bool = True
    cortex_exact_keyword_boost: float = 1.5
    cortex_semantic_vector_boost: float = 1.4
    cortex_graph_boost: float = 1.3
    cortex_temporal_boost: float = 1.3

    # Observation limits
    max_observation_size_bytes: int = 1_048_576  # 1MB

    # Retrieval
    retrieval_default_limit: int = 20
    retrieval_max_limit: int = 100
    retrieval_graph_max_hops: int = 3

    # HNSW vector search (pgvector >= 0.8.0)
    hnsw_ef_search: int = 100
    hnsw_iterative_scan: str = "relaxed_order"

    # Decay thresholds (days)
    decay_active_to_warm_days: int = 30
    decay_warm_to_cold_days: int = 90
    decay_cold_to_archived_days: int = 180

    # Authentication
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    @field_validator("hnsw_iterative_scan")
    @classmethod
    def _validate_hnsw_iterative_scan(cls, value: str) -> str:
        mode = str(value).strip().casefold()
        if mode not in HNSW_ITERATIVE_SCAN_MODES:
            raise ValueError(
                "CONTEXTA_HNSW_ITERATIVE_SCAN must be one of "
                f"{', '.join(HNSW_ITERATIVE_SCAN_MODES)} for pgvector 0.8; got {value!r}."
            )
        return mode

    def _configure_embedding_profile(self) -> None:
        fields_set = getattr(self, "__pydantic_fields_set__", set())
        provider = str(self.embedding_provider).strip().casefold()
        if provider in {"local", "qwen", "offline"}:
            profile = OFFLINE_EMBEDDING_PROFILE
        elif provider == "openai":
            profile = ONLINE_EMBEDDING_PROFILE
        elif provider == "deterministic":
            profile = DETERMINISTIC_EMBEDDING_PROFILE
        else:
            return
        # The provider is the axis the profile is selected on, so an explicitly set
        # provider re-derives the profile even when the profile was also pinned in
        # .env. Without this, a partial override (e.g. an injected provider in tests)
        # leaves provider and profile disagreeing and the object is unconstructable.
        if "embedding_provider" in fields_set or "embedding_profile" not in fields_set:
            self.embedding_profile = profile.name
        if "embedding_model" not in fields_set:
            self.embedding_model = profile.model
        if "embedding_dimensions" not in fields_set:
            self.embedding_dimensions = profile.dimensions or OFFLINE_EMBEDDING_PROFILE.dimensions
        if "embedding_version" not in fields_set:
            self.embedding_version = profile.version

    def embedding_profile_definition(self) -> EmbeddingProfile:
        dimensions = int(self.embedding_dimensions)
        if dimensions <= 0:
            raise ValueError(
                "Embedding dimensions must be a positive integer. Set "
                "CONTEXTA_EMBEDDING_DIMENSIONS=1024 for offline Qwen3 or 1536 for online OpenAI."
            )
        profile_name = str(self.embedding_profile).strip().casefold()
        profile_name = EMBEDDING_PROFILE_ALIASES.get(profile_name, profile_name)
        provider = str(self.embedding_provider).strip().casefold()
        model = str(self.embedding_model).strip()
        version = str(self.embedding_version).strip()
        if profile_name == OFFLINE_EMBEDDING_PROFILE.name:
            if provider not in {"local", "qwen", "offline"}:
                raise ValueError(
                    "Embedding profile 'offline-qwen3-1024' requires CONTEXTA_EMBEDDING_PROVIDER=local."
                )
            if dimensions != OFFLINE_EMBEDDING_PROFILE.dimensions:
                raise ValueError(
                    "Embedding profile 'offline-qwen3-1024' requires exactly 1024 dimensions, "
                    f"got {dimensions}. Set CONTEXTA_EMBEDDING_DIMENSIONS=1024; vectors are never padded."
                )
            if not model or not version:
                raise ValueError(
                    "Embedding profile metadata requires non-empty CONTEXTA_EMBEDDING_MODEL and "
                    "CONTEXTA_EMBEDDING_VERSION values."
                )
            return replace(OFFLINE_EMBEDDING_PROFILE, model=model, version=version)
        if profile_name == ONLINE_EMBEDDING_PROFILE.name:
            if provider != "openai":
                raise ValueError(
                    "Embedding profile 'online-openai-1536' requires CONTEXTA_EMBEDDING_PROVIDER=openai."
                )
            if dimensions != ONLINE_EMBEDDING_PROFILE.dimensions:
                raise ValueError(
                    "Embedding profile 'online-openai-1536' requires exactly 1536 dimensions, "
                    f"got {dimensions}. Set CONTEXTA_EMBEDDING_DIMENSIONS=1536; vectors are never truncated."
                )
            if not model or not version:
                raise ValueError(
                    "Embedding profile metadata requires non-empty CONTEXTA_EMBEDDING_MODEL and "
                    "CONTEXTA_EMBEDDING_VERSION values."
                )
            return replace(ONLINE_EMBEDDING_PROFILE, model=model, version=version)
        if profile_name == DETERMINISTIC_EMBEDDING_PROFILE.name:
            if provider != "deterministic":
                raise ValueError(
                    "Embedding profile 'deterministic' requires CONTEXTA_EMBEDDING_PROVIDER=deterministic."
                )
            return EmbeddingProfile(
                name=DETERMINISTIC_EMBEDDING_PROFILE.name,
                dimensions=dimensions,
                model=model or DETERMINISTIC_EMBEDDING_PROFILE.model,
                version=version or DETERMINISTIC_EMBEDDING_PROFILE.version,
                provider="deterministic",
                storage_column=(
                    "embedding_1024"
                    if dimensions == OFFLINE_EMBEDDING_PROFILE.dimensions
                    else "embedding"
                ),
            )
        raise ValueError(
            f"Unsupported embedding profile {self.embedding_profile!r} for provider "
            f"{self.embedding_provider!r}. Supported production profiles are "
            "'offline-qwen3-1024' and 'online-openai-1536'."
        )

    def validate_engine_embedding_compatibility(self) -> EmbeddingProfile:
        profile = self.embedding_profile_definition()
        mode = str(self.engine_mode).strip().casefold()
        if mode == "offline" and profile.provider == "openai":
            raise ValueError(
                "CONTEXTA_ENGINE_MODE=offline requires the offline-qwen3-1024 embedding profile; "
                "set CONTEXTA_EMBEDDING_PROVIDER=local and CONTEXTA_EMBEDDING_DIMENSIONS=1024."
            )
        if mode == "online" and profile.provider == "local":
            raise ValueError(
                "CONTEXTA_ENGINE_MODE=online requires the online-openai-1536 embedding profile; "
                "set CONTEXTA_EMBEDDING_PROVIDER=openai and CONTEXTA_EMBEDDING_DIMENSIONS=1536."
            )
        return profile

    @property
    def embedding_metadata(self) -> dict[str, str | int]:
        profile = self.embedding_profile_definition()
        return {
            "embedding_profile": profile.name,
            "embedding_model": profile.model,
            "embedding_version": profile.version,
            "embedding_dimensions": profile.dimensions,
        }

    @property
    def embedding_model_version(self) -> str:
        return self.embedding_version

    def model_post_init(self, __context: Any, /) -> None:
        persisted = load_persisted_engine_mode()
        provider = str(self.embedding_provider).strip().casefold()
        profile_conflicts_with_persisted_mode = (
            (persisted == "offline" and provider == "openai")
            or (persisted == "online" and provider in {"local", "qwen", "offline"})
        )
        if (
            persisted
            and self.engine_mode == "auto"
            and not profile_conflicts_with_persisted_mode
        ):
            self.engine_mode = persisted
        self._configure_embedding_profile()
        self.embedding_profile_definition()
        if not self.jev_api_key and self.engine_mode == "online":
            self.jev_api_key = os.environ.get(
                "JEV_API",
                os.environ.get("CONTEXTA_JEV_API_KEY", os.environ.get("JEV_API_KEY", "")),
            )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
