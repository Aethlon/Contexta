import asyncio
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import json

from contexta.core.retrieval.engine import RetrievalEngine, RetrievalQuery
from contexta.repositories.memory_repo import MemoryRepository
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)
from contexta.services.embedding import EmbeddingService
from contexta.config.settings import get_settings
import httpx

class LocalModelServerEmbedder:
    def __init__(self, server_url: str = "http://localhost:8001") -> None:
        self.server_url = server_url
    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.server_url}/v1/embeddings",
                json={"input": text, "model": "Qwen/Qwen3-Embedding-0.6B"},
            )
            raw_emb = [float(val) for val in resp.json()["data"][0]["embedding"]]
            if len(raw_emb) < 1536:
                raw_emb = raw_emb + [0.0] * (1536 - len(raw_emb))
            return raw_emb[:1536]

async def test():
    db_url = "postgresql+asyncpg://postgres:postgres@localhost:55432/contexta"
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    settings = get_settings()
    embedding_service = EmbeddingService(settings=settings, provider=LocalModelServerEmbedder())
    
    async with session_factory() as s:
        from sqlalchemy import text
        # get the latest user_id from memory_record
        res = await s.execute(text("SELECT user_id, organization_id FROM memory_record LIMIT 1"))
        row = res.fetchone()
        if not row:
            print("No memories found!")
            return
        user_id, org_id = row[0], row[1]
        print(f"User ID: {user_id}, Org ID: {org_id}")
        
        # search for guinea pig memory directly
        mem_res = await s.execute(text("SELECT id, content FROM memory_record WHERE content ILIKE '%guinea%'"))
        gp_mem = mem_res.fetchall()
        print("Direct DB search for 'guinea':", gp_mem)
        
        # Now run engine.retrieve
        memory_repo = MemoryRepository(s, tenant_id=org_id)
        entity_repo = EntityRepository(s, tenant_id=org_id)
        link_repo = MemoryEntityLinkRepository(s, tenant_id=org_id)
        edge_repo = EntityEdgeRepository(s, tenant_id=org_id)
        
        ret_engine = RetrievalEngine(
            memory_repository=memory_repo,
            link_repository=link_repo,
            edge_repository=edge_repo,
            entity_repository=entity_repo,
        )
        
        q_text = "What pet does Caroline have?"
        q_emb = await embedding_service.embed_text(q_text)
        q = RetrievalQuery(
            user_id=user_id,
            organization_id=org_id,
            query_text=q_text,
            limit=15,
        )
        results = await ret_engine.retrieve(q, query_embedding=q_emb)
        print(f"\nRetrieved {len(results)} results for '{q_text}':")
        for idx, r in enumerate(results):
            print(f"[{idx+1}] Score: {r.score:.3f} (sem: {r.semantic_score:.3f}, kw: {r.keyword_score:.3f}, graph: {r.graph_score:.3f}) Content: {r.memory.content[:100]}")

asyncio.run(test())
