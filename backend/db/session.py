"""Async engine + session factory + request-scoped unit of work (§9.3).

The request ``get_session`` dependency owns the unit of work: it commits on a
clean request exit and rolls back on any exception. Repositories only ``flush``
— they never commit (§9.3).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine (asyncpg driver)."""
    settings = get_settings()
    engine = create_async_engine(
        settings.async_database_url(),
        pool_pre_ping=True,
        future=True,
    )
    logger.info("Async DB engine created")
    return engine


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session and own the unit of work.

    Commits on clean exit; rolls back on any exception; always closes. This is
    the ONLY place commit/rollback happens for request-scoped work (§9.3).
    """
    session_factory = get_sessionmaker()
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Dispose the engine on shutdown (called from the app lifespan)."""
    engine = get_engine()
    await engine.dispose()
    logger.info("Async DB engine disposed")
