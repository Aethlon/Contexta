"""Application settings using Pydantic BaseSettings.

Configuration is loaded from environment variables with sensible defaults
for local development. All settings can be overridden via environment
variables or a .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """contexta application settings."""

    model_config = SettingsConfigDict(
        env_prefix="CONTEXTA_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/contexta"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False
    db_boot_check: bool = True

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

    # Embedding model
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_provider: str = "openai"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"

    # LLM provider
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"

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

    # Dodo Payments
    dodo_api_key: str = ""
    dodo_mode: str = "test"
    dodo_webhook_secret: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
