"""Database and Redis connection and session management.

Configures the async SQLAlchemy engine and session factory, and provides
FastAPI dependencies and helper functions for database and Redis health checks.
"""

from collections.abc import AsyncGenerator
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from contexta.config.settings import get_settings

settings = get_settings()

# Create async SQLAlchemy engine
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.database_echo,
)

# Async session factory
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency to retrieve an async database session.

    Yields a session and automatically handles commit on success or rollback on
    exception.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db() -> bool:
    """Execute a simple query to verify database connection health.

    Returns
    -------
    bool
        True if the database is accessible, False otherwise.
    """
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


async def check_redis() -> bool:
    """Ping Redis to verify connection health.

    Returns
    -------
    bool
        True if Redis is accessible, False otherwise.
    """
    try:
        client = aioredis.from_url(settings.redis_url)
        pong = await client.ping()
        await client.close()
        return pong is True
    except Exception:
        return False
