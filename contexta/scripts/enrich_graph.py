"""Retroactive graph enrichment script.

Upgrades generic co_occurs_with edges into typed semantic relationships
(integrates_with, is_a, used_by, uses, depends_on, etc.) and cleans up
spurious noise entities from the PostgreSQL knowledge graph.
"""

import asyncio
import logging
from sqlalchemy import delete, select, update

from contexta.core.entities.relation_extractor import (
    GENERIC_NOISE_WORDS,
    extract_semantic_relations,
    filter_entity_candidates,
    infer_entity_type,
)
from contexta.mcp.service import DEFAULT_ORG_ID, ContextaMCPService
from contexta.models.entity import Entity, EntityEdge, MemoryEntityLink
from contexta.models.memory import MemoryRecord
from contexta.repositories.entity_repo import (
    EntityEdgeRepository,
    EntityRepository,
    MemoryEntityLinkRepository,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrich_graph")


async def enrich():
    service = ContextaMCPService()
    org_id = DEFAULT_ORG_ID

    async with service.session() as session:
        entity_repo = EntityRepository(session, tenant_id=org_id)
        edge_repo = EntityEdgeRepository(session, tenant_id=org_id)
        link_repo = MemoryEntityLinkRepository(session, tenant_id=org_id)

        # 1. Prune noise entities
        logger.info("Scanning for noise entities to clean up...")
        all_entities = (await session.execute(select(Entity))).scalars().all()
        noise_ids = []
        for e in all_entities:
            name_lower = e.name.strip().lower()
            if name_lower in GENERIC_NOISE_WORDS:
                noise_ids.append(e.id)

        if noise_ids:
            logger.info(f"Removing {len(noise_ids)} noise entities and their links...")
            await session.execute(delete(MemoryEntityLink).where(MemoryEntityLink.entity_id.in_(noise_ids)))
            await session.execute(
                delete(EntityEdge).where(
                    EntityEdge.source_entity_id.in_(noise_ids) | EntityEdge.target_entity_id.in_(noise_ids)
                )
            )
            await session.execute(delete(Entity).where(Entity.id.in_(noise_ids)))
            await session.commit()
            logger.info("Noise entity cleanup completed.")

        # 2. Re-scan memories with connected entities to extract typed semantic edges
        logger.info("Enriching semantic relationships across memories...")
        mem_stmt = select(MemoryRecord).where(MemoryRecord.organization_id == org_id)
        res = await session.execute(mem_stmt)
        memories = res.scalars().all()
        logger.info(f"Found {len(memories)} total memories to inspect.")

        upgraded_edges = 0
        new_edges = 0

        for mem in memories:
            links = await link_repo.get_entities_for_memory(mem.id)
            if len(links) < 2:
                continue

            # Fetch entity records
            linked_entities = []
            for lk in links:
                ent = await entity_repo.get_by_id(lk.entity_id)
                if ent and ent.name.strip().lower() not in GENERIC_NOISE_WORDS:
                    linked_entities.append(ent)

            if len(linked_entities) < 2:
                continue

            full_text = f"{mem.title}\n{mem.content}"
            semantic_rels = extract_semantic_relations(full_text, linked_entities)

            for src_ent, rel_type, tgt_ent in semantic_rels:
                if src_ent.id == tgt_ent.id:
                    continue

                # Check if edge already exists
                existing = await edge_repo.get_neighbors(src_ent.id)
                matched_edge = None
                for ed in existing:
                    if (
                        (ed.source_entity_id == src_ent.id and ed.target_entity_id == tgt_ent.id)
                        or (ed.source_entity_id == tgt_ent.id and ed.target_entity_id == src_ent.id)
                    ):
                        matched_edge = ed
                        break

                if matched_edge:
                    if (
                        matched_edge.relationship_type in {"co_occurs_with", "related_to"}
                        and rel_type not in {"co_occurs_with", "related_to"}
                    ):
                        await edge_repo.update_by_id(
                            matched_edge.id,
                            {
                                "source_entity_id": src_ent.id,
                                "target_entity_id": tgt_ent.id,
                                "relationship_type": rel_type,
                            },
                        )
                        upgraded_edges += 1
                else:
                    new_edge = EntityEdge(
                        source_entity_id=src_ent.id,
                        target_entity_id=tgt_ent.id,
                        relationship_type=rel_type,
                        organization_id=org_id,
                    )
                    await edge_repo.create(new_edge)
                    new_edges += 1

        await session.commit()
        logger.info(f"Enrichment finished: Upgraded {upgraded_edges} edges to semantic relations, created {new_edges} new typed edges.")


if __name__ == "__main__":
    asyncio.run(enrich())
