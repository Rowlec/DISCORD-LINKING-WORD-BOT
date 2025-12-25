"""
Database connection and session management for Word Chain Bot.
"""
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import SETTINGS, LOGGER_NAME_DB
from models.db_models import Base

logger = logging.getLogger(LOGGER_NAME_DB)

# Create async engine
engine = create_async_engine(
    SETTINGS.database_url,
    echo=SETTINGS.dev_mode,  # Log SQL queries in dev mode
    pool_pre_ping=True,  # Enable connection health checks
)

# Create session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_database() -> None:
    """Initialize the database by creating all tables."""
    logger.info("Initializing database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully.")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_database() -> None:
    """Close database connections."""
    logger.info("Closing database connections...")
    await engine.dispose()
    logger.info("Database connections closed.")


class DatabaseManager:
    """
    Database manager for handling all database operations.
    Provides a cleaner interface for database operations.
    """
    
    def __init__(self):
        self._session_factory = async_session_factory
    
    async def get_session(self) -> AsyncSession:
        """Get a new database session."""
        return self._session_factory()
    
    async def execute_in_session(self, callback):
        """Execute a callback function within a database session."""
        async with self._session_factory() as session:
            try:
                result = await callback(session)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                logger.error(f"Database error: {e}")
                raise


# Global database manager instance
db_manager = DatabaseManager()
