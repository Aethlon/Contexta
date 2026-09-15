"""Application settings using Pydantic BaseSettings.

Configuration is loaded from environment variables with sensible defaults
for local development. All settings can be overridden via environment
variables or a .env file.
"""

from functools import lru_cache
import json
import os
from pathlib import Path
import time
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


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
        except Exception:
            pass
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

    # Embedding model (offline-first OSS defaults: local Qwen3, 1024-dim)
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dimensions: int = 1024
    embedding_provider: str = "local"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"

    # LLM provider (offline-first: local model-server; set online + keys for cloud)
    llm_provider: str = "local"
    llm_model: str = "Qwen/Qwen3-Reranker-0.6B"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"

    # Engine Mode & Local Model Server
    engine_mode: str = "auto"  # "offline", "online", "auto"
    local_model_server_url: str = "http://localhost:8001"
    validate_online_providers_at_startup: bool = True

    # Feature flags
    feature_sensitive_data_filter: bool = True
    feature_reflection_engine: bool = True
    feature_dream_cycle: bool = False
    feature_compression: bool = True
    feature_semantic_clustering: bool = True
    feature_retrieval_feedback: bool = True
    feature_decay_engine: bool = True

    # Observation limits
    max_observation_size_bytes: int = 1_048_576  # 1MB

    # Retrieval
    retrieval_default_limit: int = 20
    retrieval_max_limit: int = 100
    retrieval_graph_max_hops: int = 3

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

    def model_post_init(self, __context: Any) -> None:
        persisted = load_persisted_engine_mode()
        if persisted:
            self.engine_mode = persisted


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
