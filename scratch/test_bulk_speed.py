import asyncio
import time
import uuid
from datetime import datetime, UTC
from contexta.mcp.service import ContextaMCPService, DEFAULT_ORG_ID, to_uuid
from contexta.models.memory import MemoryRecord
from contexta.core.types import SourceType

async def main():
    service = ContextaMCPService()
    test_user = to_uuid("bulk-speed-test-user")
    org_id = DEFAULT_ORG_ID

    count = 500
    print(f"Generating {count} sample records...")
    texts = [
        f"Benchmark memory item #{i}: Contexta high-throughput vector and graph indexing benchmark record #{i} with Nori and Loci."
        for i in range(count)
    ]

    t0 = time.time()
    embeddings = await service._embedder.embed_batch(texts)
    t1 = time.time()
    print(f"Embedded {count} records in {t1 - t0:.2f}s ({count / (t1 - t0):.1f} docs/sec)")

    now_dt = datetime.now(UTC).replace(tzinfo=None)
    records = []
    for i in range(count):
        records.append(
            MemoryRecord(
                user_id=test_user,
                organization_id=org_id,
                memory_type="semantic",
                title=f"Benchmark Record #{i}",
                content=texts[i],
                tags=["benchmark", "speed-test"],
                source_type=SourceType.API,
                importance=0.7,
                valid_from=now_dt,
                embedding=embeddings[i],
            )
        )

    t2 = time.time()
    async with service.session() as session:
        session.add_all(records)
        await session.commit()
    t3 = time.time()
    print(f"Committed {count} records in {t3 - t2:.2f}s ({count / (t3 - t2):.1f} rows/sec)")
    print(f"Total time for {count} records: {t3 - t0:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
