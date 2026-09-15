import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine
from contexta.config.settings import get_settings
from contexta.models.base import Base

# Import all models to ensure metadata is populated
from contexta.models import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clean_database():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    
    logger.info("Connecting to database to clean data...")
    try:
        async with engine.begin() as conn:
            # Drop all tables and recreate them cleanly
            logger.info("Dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
            
            logger.info("Recreating tables...")
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Database cleaned successfully. Ready for OSS deployment!")
    except Exception as e:
        logger.error(f"Error cleaning database: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clean_database())
