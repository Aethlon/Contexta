import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

async def test():
    db_url = 'postgresql+asyncpg://postgres:postgres@localhost:55432/contexta'
    engine = create_async_engine(db_url)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)
    async with session_factory() as s:
        res = await s.execute(text("SELECT id, content FROM memory_record WHERE content ILIKE '%home country%' OR content ILIKE '%sweden%' OR content ILIKE '%4 years%'"))
        for r in res.fetchall():
            print('Record:', r)
asyncio.run(test())
