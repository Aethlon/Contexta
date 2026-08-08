"""FastAPI dependency injection for contexta API."""

from __future__ import annotations

from contexta.ai.embeddings import EmbeddingProvider
from contexta.config import Settings
from contexta.core.engines import (
    ClusteringEngine,
    CompressionEngine,
    DecayEngine,
    ExtractionEngine,
    ReflectionEngine,
    RetrievalEngine,
    ScoringEngine,
    TruthEngine,
)


async def get_settings() -> Settings:
    return Settings()


async def get_embedding_provider() -> EmbeddingProvider:
    settings = await get_settings()
    return EmbeddingProvider(settings)


async def get_extraction_engine(
    embedding_provider: EmbeddingProvider = None,
) -> ExtractionEngine:
    if embedding_provider is None:
        embedding_provider = await get_embedding_provider()
    return ExtractionEngine(
        embedding_provider=embedding_provider,
        scoring_engine=ScoringEngine(),
        truth_engine=TruthEngine(),
    )


async def get_scoring_engine() -> ScoringEngine:
    return ScoringEngine()


async def get_truth_engine() -> TruthEngine:
    return TruthEngine()


async def get_retrieval_engine(
    embedding_provider: EmbeddingProvider = None,
) -> RetrievalEngine:
    if embedding_provider is None:
        embedding_provider = await get_embedding_provider()
    return RetrievalEngine(
        embedding_provider=embedding_provider,
        scoring_engine=ScoringEngine(),
    )


async def get_lifecycle_engines() -> dict:
    return {
        "compression": CompressionEngine(),
        "decay": DecayEngine(),
        "clustering": ClusteringEngine(),
        "reflection": ReflectionEngine(),
        "extraction": await get_extraction_engine(),
        "retrieval": await get_retrieval_engine(),
    }
