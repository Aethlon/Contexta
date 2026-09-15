"""Retrieval API routes."""

from __future__ import annotations

import logging

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from contexta.core.retrieval.agentic_engine import AgenticRetrievalEngine
from contexta.core.retrieval.engine import RetrievalEngine
from contexta.core.schemas import RetrievalQuery
from contexta.db import get_db_session
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.repositories.memory_repo import MemoryRepository
from contexta.services.embedding import EmbeddingService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/retrieve")
async def retrieve(
    query: RetrievalQuery,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Retrieve memories using hybrid semantic, keyword, recency, importance, and graph scoring."""
    # 1. Embed query text if provider is configured
    embedding_service = EmbeddingService()
    try:
        query_embedding = await embedding_service.embed_text(query.query_text)
    except Exception:  # noqa: BLE001 - graceful fallback to keyword + recency scoring
        logger.warning("Query embedding generation failed, falling back to non-semantic scoring")
        query_embedding = None

    # 2. Instantiate repositories
    memory_repo = MemoryRepository(session, tenant_id=query.organization_id)
    entity_repo = EntityRepository(session, tenant_id=query.organization_id)
    link_repo = MemoryEntityLinkRepository(session, tenant_id=query.organization_id)
    edge_repo = EntityEdgeRepository(session, tenant_id=query.organization_id)

    # 3. Execute hybrid retrieval engine
    engine = RetrievalEngine(
        memory_repository=memory_repo,
        link_repository=link_repo,
        edge_repository=edge_repo,
        entity_repository=entity_repo,
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


from pydantic import BaseModel


class BatchRetrievalQuery(BaseModel):
    queries: list[RetrievalQuery]


@router.post("/retrieve/batch")
async def retrieve_batch(
    payload: BatchRetrievalQuery,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Concurrently execute multiple memory retrieval queries in parallel."""
    import asyncio

    if not payload.queries:
        return {"status": "success", "count": 0, "batch_results": []}

    embedding_service = EmbeddingService()

    # 1. Batch generate embeddings for all queries concurrently
    async def _safe_embed(q_text: str):
        try:
            return await embedding_service.embed_text(q_text)
        except Exception:
            return None

    query_embeddings = await asyncio.gather(*[_safe_embed(q.query_text) for q in payload.queries])

    # 2. Execute retrieval queries concurrently
    async def _execute_single(query: RetrievalQuery, q_emb: list[float] | None):
        memory_repo = MemoryRepository(session, tenant_id=query.organization_id)
        entity_repo = EntityRepository(session, tenant_id=query.organization_id)
        link_repo = MemoryEntityLinkRepository(session, tenant_id=query.organization_id)
        edge_repo = EntityEdgeRepository(session, tenant_id=query.organization_id)

        engine = RetrievalEngine(
            memory_repository=memory_repo,
            link_repository=link_repo,
            edge_repository=edge_repo,
            entity_repository=entity_repo,
        )
        results = await engine.retrieve(query, query_embedding=q_emb)

        serialized = []
        for item in results:
            serialized.append({
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
            "query": query.query_text,
            "count": len(serialized),
            "results": serialized,
        }

    batch_results = []
    for q, emb in zip(payload.queries, query_embeddings):
        res = await _execute_single(q, emb)
        batch_results.append(res)

    return {
        "status": "success",
        "count": len(batch_results),
        "batch_results": list(batch_results),
    }


class InvestigateRetrievalQuery(BaseModel):
    query_text: str
    user_id: UUID
    organization_id: UUID | None = None
    max_hops: int = 2
    limit: int = 15


@router.post("/retrieve/investigate")
async def retrieve_investigate(
    payload: InvestigateRetrievalQuery,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Execute iterative agentic investigative retrieval (ASMR-style multi-hop memory reasoning)."""
    org_id = payload.organization_id or UUID(
        str(getattr(request.state, "organization_id", "00000000-0000-0000-0000-000000000001"))
    )

    memory_repo = MemoryRepository(session, tenant_id=org_id)
    entity_repo = EntityRepository(session, tenant_id=org_id)
    link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)
    edge_repo = EntityEdgeRepository(session, tenant_id=org_id)

    engine = RetrievalEngine(
        memory_repository=memory_repo,
        link_repository=link_repo,
        edge_repository=edge_repo,
        entity_repository=entity_repo,
    )

    agentic_engine = AgenticRetrievalEngine(
        retrieval_engine=engine,
        entity_repository=entity_repo,
        edge_repository=edge_repo,
    )

    embedding_service = EmbeddingService()
    try:
        q_emb = await embedding_service.embed_text(payload.query_text)
    except Exception:
        q_emb = None

    result = await agentic_engine.investigate(
        query_text=payload.query_text,
        user_id=payload.user_id,
        organization_id=org_id,
        max_hops=payload.max_hops,
        limit=payload.limit,
        query_embedding=q_emb,
    )

    return {
        "status": "success",
        "query": result.query,
        "execution_time_ms": result.execution_time_ms,
        "entities_discovered": result.entities_discovered,
        "investigation_trace": [
            {
                "step": s.step_number,
                "action": s.action,
                "target": s.target,
                "rationale": s.rationale,
                "discovered_count": s.discovered_count,
            }
            for s in result.investigation_trace
        ],
        "temporal_evolution": result.temporal_evolution,
        "synthesized_context": result.synthesized_context,
        "results": [
            {
                "id": str(r.memory.id),
                "title": r.memory.title,
                "content": r.memory.content,
                "memory_type": r.memory.memory_type,
                "score": r.score,
                "is_current": r.memory.valid_to is None,
                "created_at": r.memory.created_at.isoformat() if r.memory.created_at else None,
            }
            for r in result.memories
        ],
    }


