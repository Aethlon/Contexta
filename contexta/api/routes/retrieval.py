"""Retrieval API routes."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.db import get_db_session
from contexta.core.schemas import RetrievalQuery
from contexta.core.retrieval.engine import RetrievalEngine
from contexta.repositories.memory_repo import MemoryRepository
from contexta.repositories.entity_repo import EntityEdgeRepository, MemoryEntityLinkRepository
from contexta.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/retrieve")
async def retrieve(
    query: RetrievalQuery,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Execute hybrid semantic, keyword, and graph-based memory retrieval.

    Generates the query embedding, executes the scorer engine, and returns
    relevance-ranked memories.
    """
    try:
        # 1. Generate text embedding for the search text
        embed_service = EmbeddingService()
        query_embedding = await embed_service.embed_text(query.query_text)
    except Exception as exc:
        logger.error("Failed to generate query embedding: %s", exc)
        # Fall back to keyword-only retrieval if embedding service is offline
        query_embedding = None

    # 2. Instantiate repositories
    memory_repo = MemoryRepository(session, tenant_id=query.organization_id)
    link_repo = MemoryEntityLinkRepository(session, tenant_id=query.organization_id)
    edge_repo = EntityEdgeRepository(session, tenant_id=query.organization_id)

    # 3. Execute hybrid retrieval engine
    engine = RetrievalEngine(
        memory_repository=memory_repo,
        link_repository=link_repo,
        edge_repository=edge_repo,
    )

    results = await engine.retrieve(query, query_embedding=query_embedding)

    # 4. Serialize results
    serialized_results = []
    for item in results:
        serialized_results.append({
            "memory": {
                "id": str(item.memory.id),
                "user_id": str(item.memory.user_id),
                "organization_id": str(item.memory.organization_id),
                "memory_type": item.memory.memory_type,
                "title": item.memory.title,
                "content": item.memory.content,
                "structured_data": item.memory.structured_data,
                "tags": item.memory.tags,
                "is_pinned": item.memory.is_pinned,
                "is_archived": item.memory.is_archived,
                "memory_state": item.memory.memory_state,
                "created_at": item.memory.created_at.isoformat() if item.memory.created_at else None,
            },
            "score": item.score,
            "semantic_score": item.semantic_score,
            "graph_score": item.graph_score,
            "importance_score": item.importance_score,
            "recency_score": item.recency_score,
            "keyword_score": item.keyword_score,
        })

    return {
        "status": "success",
        "query": query.query_text,
        "results": serialized_results,
    }
